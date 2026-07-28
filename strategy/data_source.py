from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.error import URLError
from urllib.request import Request, urlopen


class DataFetchError(RuntimeError):
    """Raised when remote market data cannot be fetched and no cache is usable."""


@dataclass(frozen=True)
class FetchConfig:
    timeout_seconds: float = 5.0
    retries: int = 3
    backoff_seconds: float = 0.5
    cache_dir: Path = Path(".cache/strategy-data")
    allow_stale_cache: bool = True
    user_agent: str = "strategy-engine/1.0"


def _cache_path(url: str, cache_dir: Path) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return cache_dir / f"{digest}.txt"


def fetch_text(
    url: str,
    *,
    config: FetchConfig | None = None,
    opener: Callable[..., object] = urlopen,
    sleeper: Callable[[float], None] = time.sleep,
) -> str:
    """Fetch remote text with timeout, retry/backoff and stale-cache fallback.

    The injected ``opener`` and ``sleeper`` make timeout/retry behavior unit-testable
    without performing real network calls.
    """

    cfg = config or FetchConfig()
    if cfg.retries < 1:
        raise ValueError("retries must be at least 1")
    if cfg.timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    cache_file = _cache_path(url, cfg.cache_dir)
    last_error: BaseException | None = None
    request = Request(url, headers={"User-Agent": cfg.user_agent})

    for attempt in range(cfg.retries):
        try:
            with opener(request, timeout=cfg.timeout_seconds) as response:  # type: ignore[arg-type]
                body = response.read().decode("utf-8")
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(body, encoding="utf-8")
            return body
        except (TimeoutError, URLError, OSError) as exc:
            last_error = exc
            if attempt < cfg.retries - 1:
                sleeper(cfg.backoff_seconds * (2**attempt))

    if cfg.allow_stale_cache and cache_file.exists():
        return cache_file.read_text(encoding="utf-8")

    raise DataFetchError(f"failed to fetch {url!r} after {cfg.retries} attempts: {last_error}")
