import pytest

from strategy.data_source import FetchConfig, MemoryCache, fetch_with_cache


def test_fetch_with_cache_returns_cached_value(tmp_path):
    cache = MemoryCache(tmp_path / "cache.json")
    cache.set("quotes:AAPL", {"price": 1})

    value = fetch_with_cache(
        "quotes:AAPL",
        cache,
        lambda: pytest.fail("fetcher should not be called on fresh hit"),
        FetchConfig(ttl_seconds=60),
    )

    assert value == {"price": 1}


def test_fetch_with_cache_uses_stale_value_after_failures(tmp_path):
    cache = MemoryCache(tmp_path / "cache.json")
    cache.set("macro:cpi", {"value": 2.1})

    def failing_fetcher():
        raise RuntimeError("network down")

    value = fetch_with_cache(
        "macro:cpi",
        cache,
        failing_fetcher,
        FetchConfig(ttl_seconds=0, retries=1, allow_stale_cache=True, stale_ttl_seconds=60),
    )

    assert value == {"value": 2.1}
