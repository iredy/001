"""Reusable metrics for evaluating investment strategy effectiveness.

The functions in this module deliberately avoid framework-specific data loaders so
that they can be called from batch jobs, notebooks, or CI checks. Inputs are plain
Python sequences and outputs are dataclasses that can be serialized by callers.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import mean, pstdev
from typing import Iterable, Mapping, Sequence

BUY_SIGNALS = {"buy", "strong_buy", "overweight"}
SELL_SIGNALS = {"sell", "strong_sell", "underweight", "avoid"}
NEUTRAL_SIGNALS = {"hold", "neutral", "watch"}


@dataclass(frozen=True)
class BacktestMetrics:
    """Risk/return metrics for a completed backtest."""

    observations: int
    cumulative_return: float
    annualized_return: float
    annualized_volatility: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float


@dataclass(frozen=True)
class AccuracyMetrics:
    """Directional signal accuracy against future realized returns."""

    observations: int
    covered_signals: int
    coverage: float
    hit_rate: float
    precision_buy: float
    precision_sell: float
    average_forward_return: float
    average_buy_forward_return: float
    average_sell_forward_return: float


@dataclass(frozen=True)
class AvailabilityReport:
    """Operational readiness checks for strategy output rows."""

    total_rows: int
    usable_rows: int
    availability: float
    missing_required_fields: Mapping[str, int]
    invalid_signal_rows: int


def evaluate_backtest(
    returns: Sequence[float],
    *,
    periods_per_year: int = 252,
    risk_free_rate: float = 0.0,
) -> BacktestMetrics:
    """Calculate headline risk/return metrics from periodic strategy returns.

    Args:
        returns: Periodic decimal returns, for example ``0.01`` for +1%.
        periods_per_year: Number of periods per year. Use 252 for daily bars and
            12 for monthly bars.
        risk_free_rate: Annual decimal risk-free rate used in Sharpe ratio.

    Raises:
        ValueError: If returns is empty or periods_per_year is not positive.
    """

    if not returns:
        raise ValueError("returns must contain at least one observation")
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive")

    equity = 1.0
    equity_curve = []
    wins = 0
    for value in returns:
        equity *= 1.0 + value
        equity_curve.append(equity)
        if value > 0:
            wins += 1

    cumulative_return = equity - 1.0
    annualized_return = equity ** (periods_per_year / len(returns)) - 1.0
    volatility = pstdev(returns) * sqrt(periods_per_year) if len(returns) > 1 else 0.0
    excess_return = annualized_return - risk_free_rate
    sharpe = excess_return / volatility if volatility else 0.0

    peak = equity_curve[0]
    max_drawdown = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        drawdown = value / peak - 1.0
        max_drawdown = min(max_drawdown, drawdown)

    return BacktestMetrics(
        observations=len(returns),
        cumulative_return=cumulative_return,
        annualized_return=annualized_return,
        annualized_volatility=volatility,
        sharpe_ratio=sharpe,
        max_drawdown=max_drawdown,
        win_rate=wins / len(returns),
    )


def evaluate_signal_accuracy(
    signals: Sequence[str],
    forward_returns: Sequence[float],
    *,
    positive_threshold: float = 0.0,
    negative_threshold: float = 0.0,
) -> AccuracyMetrics:
    """Evaluate whether directional signals matched future realized returns.

    Buy-like signals are hits when forward return is above ``positive_threshold``;
    sell-like signals are hits when forward return is below ``negative_threshold``.
    Neutral signals are counted as covered but not as directional hits.
    """

    if len(signals) != len(forward_returns):
        raise ValueError("signals and forward_returns must have the same length")
    if not signals:
        raise ValueError("signals must contain at least one observation")

    covered = 0
    hits = 0
    buy_total = buy_hits = 0
    sell_total = sell_hits = 0
    buy_returns = []
    sell_returns = []

    for raw_signal, forward_return in zip(signals, forward_returns):
        signal = raw_signal.lower()
        if signal in BUY_SIGNALS:
            covered += 1
            buy_total += 1
            buy_returns.append(forward_return)
            if forward_return > positive_threshold:
                hits += 1
                buy_hits += 1
        elif signal in SELL_SIGNALS:
            covered += 1
            sell_total += 1
            sell_returns.append(forward_return)
            if forward_return < negative_threshold:
                hits += 1
                sell_hits += 1
        elif signal in NEUTRAL_SIGNALS:
            covered += 1

    directional_total = buy_total + sell_total
    return AccuracyMetrics(
        observations=len(signals),
        covered_signals=covered,
        coverage=covered / len(signals),
        hit_rate=hits / directional_total if directional_total else 0.0,
        precision_buy=buy_hits / buy_total if buy_total else 0.0,
        precision_sell=sell_hits / sell_total if sell_total else 0.0,
        average_forward_return=mean(forward_returns),
        average_buy_forward_return=mean(buy_returns) if buy_returns else 0.0,
        average_sell_forward_return=mean(sell_returns) if sell_returns else 0.0,
    )


def evaluate_availability(
    rows: Iterable[Mapping[str, object]],
    *,
    required_fields: Sequence[str] = ("date", "symbol", "signal", "score"),
    allowed_signals: set[str] | None = None,
) -> AvailabilityReport:
    """Check whether strategy outputs are complete enough for production use."""

    allowed = allowed_signals or BUY_SIGNALS | SELL_SIGNALS | NEUTRAL_SIGNALS
    total = usable = invalid_signal_rows = 0
    missing = {field: 0 for field in required_fields}

    for row in rows:
        total += 1
        row_missing = False
        for field in required_fields:
            if row.get(field) in (None, ""):
                missing[field] += 1
                row_missing = True
        signal = str(row.get("signal", "")).lower()
        invalid_signal = signal not in allowed
        if invalid_signal:
            invalid_signal_rows += 1
        if not row_missing and not invalid_signal:
            usable += 1

    return AvailabilityReport(
        total_rows=total,
        usable_rows=usable,
        availability=usable / total if total else 0.0,
        missing_required_fields=missing,
        invalid_signal_rows=invalid_signal_rows,
    )
