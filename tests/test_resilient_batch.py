import json
import time

from stock_analysis.resilient_batch import BatchAnalyzer, BatchConfig, RetryConfig


def test_retry_then_success_and_checkpoint(tmp_path):
    calls = {"688047": 0}

    def analyze(stock):
        calls[stock["code"]] += 1
        if calls[stock["code"]] == 1:
            raise ConnectionError("network jitter")
        return {"ok": stock["name"]}

    checkpoint = tmp_path / "checkpoint.json"
    runner = BatchAnalyzer(
        [{"code": "688047", "name": "龙芯中科"}],
        analyze,
        BatchConfig(
            checkpoint_path=checkpoint,
            retry=RetryConfig(max_attempts=2, initial_delay_seconds=0, jitter_seconds=0),
        ),
        progress=lambda _message: None,
    )

    results = runner.run()

    assert results["688047"].status == "success"
    assert results["688047"].attempts == 2
    assert json.loads(checkpoint.read_text(encoding="utf-8"))["results"]["688047"]["status"] == "success"


def test_failed_stock_does_not_interrupt_remaining_batch(tmp_path):
    def analyze(stock):
        if stock["code"] == "688469":
            raise TimeoutError("llm timeout")
        return {"ok": True}

    runner = BatchAnalyzer(
        [
            {"code": "688469", "name": "芯联集成"},
            {"code": "688981", "name": "中芯国际"},
        ],
        analyze,
        BatchConfig(
            checkpoint_path=tmp_path / "checkpoint.json",
            retry=RetryConfig(max_attempts=1, initial_delay_seconds=0, jitter_seconds=0),
        ),
        progress=lambda _message: None,
    )

    results = runner.run()

    assert results["688469"].status == "failed"
    assert results["688981"].status == "success"


def test_resume_skips_successful_items(tmp_path):
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "saved_at": time.time(),
                "results": {
                    "688469": {
                        "code": "688469",
                        "name": "芯联集成",
                        "status": "success",
                        "attempts": 1,
                        "output": {"ok": True},
                        "error": None,
                        "updated_at": time.time(),
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    called = []

    def analyze(stock):
        called.append(stock["code"])
        return {"ok": True}

    runner = BatchAnalyzer(
        [
            {"code": "688469", "name": "芯联集成"},
            {"code": "688981", "name": "中芯国际"},
        ],
        analyze,
        BatchConfig(checkpoint_path=checkpoint),
        progress=lambda _message: None,
    )

    runner.run()

    assert called == ["688981"]
