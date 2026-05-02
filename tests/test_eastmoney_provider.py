import json

from data.eastmoney_provider import EastmoneyMacroProvider


class _Resp:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_eastmoney_provider_parses_and_triggers(monkeypatch):
    payload = {
        "result": {
            "data": [
                {"VALUE": 2.70, "REPORT_DATE": "2026-05-02"},
                {"VALUE": 2.65, "REPORT_DATE": "2026-05-01"},
                {"VALUE": 2.60, "REPORT_DATE": "2026-04-30"},
                {"VALUE": 2.55, "REPORT_DATE": "2026-04-29"},
                {"VALUE": 2.50, "REPORT_DATE": "2026-04-28"},
            ]
        }
    }

    monkeypatch.setattr("data.eastmoney_provider.urlopen", lambda *args, **kwargs: _Resp(payload))
    provider = EastmoneyMacroProvider(threshold_bps=10.0, update_interval_sec=900)
    provider._fetch_live_data()

    snapshot = provider.get_market_data("current")
    assert snapshot["cn10y_yield_current"] == 2.7
    assert snapshot["cn10y_yield_baseline"] == 2.5
    assert snapshot["cn10y_yield_chg_bps"] == 20.0
    assert provider.check_macro_event_flags() is True
