"""Relative-strength helpers for separating stock alpha from index drift."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class RelativeStrengthDecision:
    """Relative strength result in percentage-point space."""

    relative_strength_pct: float
    stock_return_pct: float
    benchmark_return_pct: float
    relative_strength_phase: str


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _first_available_float(market_data: Mapping[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _optional_float(market_data.get(key))
        if value is not None:
            return value
    return None


def calculate_relative_strength(
    stock_return_pct: float,
    benchmark_return_pct: float,
    threshold_pct: float = 1.0,
) -> RelativeStrengthDecision:
    """Calculate stock return minus benchmark return and classify the result.

    Inputs are expected in percentage points, e.g. ``3.2`` means +3.2%.
    """
    rs = round(stock_return_pct - benchmark_return_pct, 4)
    if rs >= threshold_pct:
        phase = "outperform"
    elif rs <= -threshold_pct:
        phase = "underperform"
    else:
        phase = "neutral"
    return RelativeStrengthDecision(
        relative_strength_pct=rs,
        stock_return_pct=stock_return_pct,
        benchmark_return_pct=benchmark_return_pct,
        relative_strength_phase=phase,
    )


def enrich_relative_strength(market_data: Mapping[str, Any]) -> dict[str, Any]:
    """Add relative-strength fields when stock and benchmark returns are present."""
    enriched = dict(market_data)
    stock_return = _first_available_float(
        enriched,
        ("stock_return_pct", "individual_return_pct", "symbol_return_pct"),
    )
    benchmark_return = _first_available_float(
        enriched,
        ("benchmark_return_pct", "sector_return_pct", "index_return_pct", "kcb50_return_pct"),
    )
    if stock_return is None or benchmark_return is None:
        return enriched

    threshold = float(enriched.get("relative_strength_threshold_pct", 1.0))
    decision = calculate_relative_strength(stock_return, benchmark_return, threshold)
    enriched["relative_strength_pct"] = decision.relative_strength_pct
    enriched["relative_strength_phase"] = decision.relative_strength_phase
    enriched["relative_strength_benchmark_return_pct"] = decision.benchmark_return_pct
    enriched["relative_strength_stock_return_pct"] = decision.stock_return_pct
    return enriched
