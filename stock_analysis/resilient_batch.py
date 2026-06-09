"""Resilient batch execution for stock analysis jobs.

The runner is designed for long-running jobs such as "科创50成分股分析" where a
single stock may fail because of an LLM timeout, an unstable network, or a data
provider error.  It persists progress after every stock, retries transient
errors, and continues with the remaining symbols instead of aborting the whole
batch.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import os
import random
import signal
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, MutableMapping, Sequence

LOGGER = logging.getLogger(__name__)


class RetryableAnalysisError(RuntimeError):
    """Error type for failures that should be retried."""


@dataclass(frozen=True)
class RetryConfig:
    """Retry settings for transient data/LLM failures."""

    max_attempts: int = 3
    initial_delay_seconds: float = 2.0
    backoff_factor: float = 2.0
    jitter_seconds: float = 0.5
    retryable_exceptions: tuple[type[BaseException], ...] = (
        TimeoutError,
        ConnectionError,
        RetryableAnalysisError,
    )


@dataclass(frozen=True)
class BatchConfig:
    """Batch runner settings."""

    checkpoint_path: Path = Path(".analysis_checkpoint.json")
    per_stock_timeout_seconds: float = 180.0
    stop_on_failure: bool = False
    retry: RetryConfig = field(default_factory=RetryConfig)


@dataclass
class AnalysisResult:
    """Persisted status for one stock."""

    code: str
    name: str
    status: str
    attempts: int = 0
    output: Any | None = None
    error: str | None = None
    updated_at: float = field(default_factory=time.time)


class CheckpointStore:
    """JSON checkpoint storage with atomic writes."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, AnalysisResult]:
        if not self.path.exists():
            return {}
        with self.path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        results: dict[str, AnalysisResult] = {}
        for code, item in payload.get("results", {}).items():
            results[code] = AnalysisResult(**item)
        return results

    def save(self, results: Mapping[str, AnalysisResult]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "saved_at": time.time(),
            "results": {code: asdict(result) for code, result in results.items()},
        }
        temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(temp_path, self.path)


Stock = Mapping[str, str]
AnalyzeFn = Callable[[Stock], Any]
ProgressFn = Callable[[str], None]


class BatchAnalyzer:
    """Run stock analysis with retry, timeout, checkpoint, and resume support."""

    def __init__(
        self,
        stocks: Sequence[Stock],
        analyze_one: AnalyzeFn,
        config: BatchConfig | None = None,
        progress: ProgressFn | None = None,
    ) -> None:
        self.stocks = stocks
        self.analyze_one = analyze_one
        self.config = config or BatchConfig()
        self.progress = progress or LOGGER.info
        self.checkpoints = CheckpointStore(self.config.checkpoint_path)
        self._stop_requested = False

    def run(self) -> dict[str, AnalysisResult]:
        """Analyze all pending stocks and return a status map keyed by stock code."""
        results = self.checkpoints.load()
        self._install_signal_handlers()

        total = len(self.stocks)
        for index, stock in enumerate(self.stocks, start=1):
            code = stock["code"]
            name = stock.get("name", code)
            existing = results.get(code)
            if existing and existing.status == "success":
                self.progress(f"[{index}/{total}] {name} 已完成，跳过")
                continue
            if self._stop_requested:
                self.progress("收到停止信号，已保存检查点，后续可继续运行")
                break

            self.progress(f"[{index}/{total}] {name} 开始分析")
            result = self._run_one_with_retry(stock)
            results[code] = result
            self.checkpoints.save(results)

            if result.status == "success":
                self.progress(f"[{index}/{total}] {name} 完成")
            else:
                self.progress(f"[{index}/{total}] {name} 失败：{result.error}")
                if self.config.stop_on_failure:
                    break

        return results

    def _run_one_with_retry(self, stock: Stock) -> AnalysisResult:
        code = stock["code"]
        name = stock.get("name", code)
        delay = self.config.retry.initial_delay_seconds
        last_error: BaseException | None = None

        for attempt in range(1, self.config.retry.max_attempts + 1):
            try:
                output = self._run_with_timeout(stock)
                return AnalysisResult(
                    code=code,
                    name=name,
                    status="success",
                    attempts=attempt,
                    output=output,
                )
            except self.config.retry.retryable_exceptions as exc:
                last_error = exc
                if attempt >= self.config.retry.max_attempts:
                    break
                sleep_seconds = delay + random.uniform(0, self.config.retry.jitter_seconds)
                self.progress(
                    f"{name} 第 {attempt} 次失败（{exc}），{sleep_seconds:.1f}s 后重试"
                )
                time.sleep(sleep_seconds)
                delay *= self.config.retry.backoff_factor
            except BaseException as exc:  # noqa: BLE001 - persist unexpected per-stock failures.
                last_error = exc
                break

        return AnalysisResult(
            code=code,
            name=name,
            status="failed",
            attempts=self.config.retry.max_attempts,
            error=repr(last_error),
        )

    def _run_with_timeout(self, stock: Stock) -> Any:
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self.analyze_one, stock)
        try:
            return future.result(timeout=self.config.per_stock_timeout_seconds)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise TimeoutError(
                f"单股分析超过 {self.config.per_stock_timeout_seconds:.0f}s"
            ) from exc
        finally:
            # Do not use ThreadPoolExecutor as a context manager here: __exit__
            # waits for the worker and would turn a timeout into another hang.
            executor.shutdown(wait=False, cancel_futures=True)

    def _install_signal_handlers(self) -> None:
        def request_stop(signum: int, _frame: Any) -> None:
            self._stop_requested = True
            self.progress(f"收到信号 {signum}，当前股票完成后停止")

        for signum in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(signum, request_stop)
            except ValueError:
                # Signal handlers can only be installed in the main thread.
                LOGGER.debug("skip signal handler installation outside main thread")


def load_stocks(path: str | Path) -> list[dict[str, str]]:
    """Load stocks from a JSON file containing [{"code": "...", "name": "..."}]."""
    with Path(path).open("r", encoding="utf-8") as file:
        stocks = json.load(file)
    if not isinstance(stocks, list):
        raise ValueError("stocks file must contain a JSON list")
    for item in stocks:
        if not isinstance(item, MutableMapping) or "code" not in item:
            raise ValueError("each stock must contain at least a code field")
    return stocks


def demo_analyze_one(stock: Stock) -> dict[str, str]:
    """Placeholder analyzer used by the CLI demo.

    Replace this function with the real workflow that fetches data and calls the
    LLM. Raise TimeoutError/ConnectionError/RetryableAnalysisError for transient
    failures so the runner can retry and continue.
    """
    return {"summary": f"{stock.get('name', stock['code'])} 分析完成"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run resilient stock analysis batches")
    parser.add_argument("stocks", help="JSON file with stock code/name records")
    parser.add_argument("--checkpoint", default=".analysis_checkpoint.json")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--stop-on-failure", action="store_true")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = build_parser().parse_args(argv)
    stocks = load_stocks(args.stocks)
    runner = BatchAnalyzer(
        stocks,
        demo_analyze_one,
        BatchConfig(
            checkpoint_path=Path(args.checkpoint),
            per_stock_timeout_seconds=args.timeout,
            stop_on_failure=args.stop_on_failure,
            retry=RetryConfig(max_attempts=args.max_attempts),
        ),
        progress=print,
    )
    results = runner.run()
    failed = [result for result in results.values() if result.status == "failed"]
    print(f"完成：{len(results) - len(failed)}，失败：{len(failed)}")
    return 1 if failed and args.stop_on_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
