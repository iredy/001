from data.macro_monitor import MacroDataProvider


class _FakeDF:
    def __init__(self, values):
        self._values = values

    @property
    def empty(self):
        return len(self._values) == 0

    def __len__(self):
        return len(self._values)

    @property
    def iloc(self):
        class _ILoc:
            def __init__(self, values):
                self.values = values

            def __getitem__(self, idx):
                return {"中国国债收益率10年": self.values[idx]}

        return _ILoc(self._values)


class _FakeAk:
    def bond_zh_us_rate(self):
        return _FakeDF([2.40, 2.45, 2.50, 2.55, 2.60, 2.65])


def test_macro_provider_snapshot_and_threshold(monkeypatch):
    monkeypatch.setattr("importlib.import_module", lambda _name: _FakeAk())
    provider = MacroDataProvider(threshold_bps=10.0, update_interval_sec=999)

    provider._fetch_live_data()
    snapshot = provider.get_market_data("09:20")

    assert "cn10y_yield_chg_bps" in snapshot
    assert snapshot["time_tag"] == "09:20"
    assert provider.check_macro_event_flags() is True
