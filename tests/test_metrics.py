from math import isclose

import pytest

from strategy_evaluation import (
    evaluate_availability,
    evaluate_backtest,
    evaluate_signal_accuracy,
)


def test_evaluate_backtest_returns_core_metrics():
    metrics = evaluate_backtest([0.1, -0.05, 0.02], periods_per_year=3)

    assert metrics.observations == 3
    assert metrics.cumulative_return > 0
    assert metrics.annualized_volatility > 0
    assert metrics.max_drawdown < 0
    assert isclose(metrics.win_rate, 2 / 3)


def test_evaluate_signal_accuracy_counts_directional_hits():
    metrics = evaluate_signal_accuracy(
        ["strong_buy", "buy", "hold", "avoid", "sell"],
        [0.04, -0.01, 0.00, -0.03, 0.02],
    )

    assert metrics.observations == 5
    assert metrics.covered_signals == 5
    assert isclose(metrics.hit_rate, 0.5)
    assert isclose(metrics.precision_buy, 0.5)
    assert isclose(metrics.precision_sell, 0.5)


def test_evaluate_availability_reports_missing_and_invalid_rows():
    report = evaluate_availability(
        [
            {"date": "2026-06-20", "symbol": "A", "signal": "buy", "score": 90},
            {"date": "", "symbol": "B", "signal": "buy", "score": 80},
            {"date": "2026-06-20", "symbol": "C", "signal": "unknown", "score": 70},
        ]
    )

    assert report.total_rows == 3
    assert report.usable_rows == 1
    assert isclose(report.availability, 1 / 3)
    assert report.missing_required_fields["date"] == 1
    assert report.invalid_signal_rows == 1


def test_rejects_mismatched_accuracy_inputs():
    with pytest.raises(ValueError):
        evaluate_signal_accuracy(["buy"], [])
