"""Cache-first data-source helpers for avoiding repeated fetches."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class FetchConfig:
    timeout_seconds: float = 5.0
    retries: int = 3
    allow_stale_cache: bool = True
    ttl_seconds: int = 300
    stale_ttl_seconds: int = 86_400


class MemoryCache:
    """A tiny JSON-backed cache suitable for PR summaries and market snapshots."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._items: dict[str, dict[str, object]] = {}
        if self.path.exists():
            self._items = json.loads(self.path.read_text(encoding="utf-8"))

    def get(self, key: str, *, max_age_seconds: int) -> object | None:
        item = self._items.get(key)
        if item is None:
            return None
        created_at = float(item["created_at"])
        if time.time() - created_at > max_age_seconds:
            return None
        return item["value"]

    def set(self, key: str, value: object) -> None:
        self._items[key] = {"created_at": time.time(), "value": value}
        self.path.write_text(json.dumps(self._items, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_with_cache(key: str, cache: MemoryCache, fetcher: Callable[[], T], config: FetchConfig) -> T:
    """Fetch fresh data with stale-cache fallback.

    The function first returns a fresh cache hit. If fetching fails and stale
    cache is allowed, it returns data within the stale window instead of
    propagating transient provider/network failures.
    """

    cached = cache.get(key, max_age_seconds=config.ttl_seconds)
    if cached is not None:
        return cached  # type: ignore[return-value]

    last_error: Exception | None = None
    for _ in range(config.retries + 1):
        try:
            value = fetcher()
            cache.set(key, value)
            return value
        except Exception as exc:  # noqa: PERF203 - retries intentionally handle transient failures.
            last_error = exc

    if config.allow_stale_cache:
        stale = cache.get(key, max_age_seconds=config.stale_ttl_seconds)
        if stale is not None:
            return stale  # type: ignore[return-value]

    assert last_error is not None
    raise last_error
