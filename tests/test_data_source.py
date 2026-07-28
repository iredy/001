from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from urllib.error import URLError

from strategy.data_source import DataFetchError, FetchConfig, fetch_text


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body.encode("utf-8")


class DataSourceTest(unittest.TestCase):
    def test_retries_after_timeout_and_succeeds(self):
        calls = {"count": 0}

        def opener(_request, timeout):
            calls["count"] += 1
            if calls["count"] == 1:
                raise TimeoutError("timed out")
            return FakeResponse("ok")

        text = fetch_text("https://example.test/data.csv", config=FetchConfig(retries=2, backoff_seconds=0), opener=opener, sleeper=lambda _: None)
        self.assertEqual(text, "ok")
        self.assertEqual(calls["count"], 2)

    def test_uses_stale_cache_when_api_is_down(self):
        with TemporaryDirectory() as tmp:
            config = FetchConfig(retries=1, cache_dir=Path(tmp), allow_stale_cache=True)
            fetch_text("https://example.test/data.csv", config=config, opener=lambda *_args, **_kwargs: FakeResponse("cached"))
            text = fetch_text("https://example.test/data.csv", config=config, opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("down")))
            self.assertEqual(text, "cached")

    def test_raises_when_no_cache_is_available(self):
        with TemporaryDirectory() as tmp:
            config = FetchConfig(retries=1, cache_dir=Path(tmp), allow_stale_cache=False)
            with self.assertRaises(DataFetchError):
                fetch_text("https://example.test/missing.csv", config=config, opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("down")))


if __name__ == "__main__":
    unittest.main()
