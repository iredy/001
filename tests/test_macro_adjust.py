from datetime import datetime, timezone

from strategy.macro_adjust import adjust_macro_weight


def test_keep_baseline_early_month():
    decision = adjust_macro_weight(
        0.25,
        {"cn10y_yield_chg_bps": 20},
        now=datetime(2026, 5, 3, tzinfo=timezone.utc),
    )
    assert decision.adjusted_weight == 0.25
    assert decision.adjustment_reason == "PMI_fresh_keep_baseline"


def test_reduce_macro_when_mid_month_rate_drops():
    decision = adjust_macro_weight(
        0.25,
        {"cn10y_yield_chg_bps": -12},
        now=datetime(2026, 5, 15, tzinfo=timezone.utc),
    )
    assert round(decision.adjusted_weight, 2) == 0.22


def test_increase_macro_when_mid_month_rate_rises():
    decision = adjust_macro_weight(
        0.25,
        {"cn10y_yield_chg_bps": 14},
        now=datetime(2026, 5, 15, tzinfo=timezone.utc),
    )
    assert round(decision.adjusted_weight, 2) == 0.28
