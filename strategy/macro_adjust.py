"""High-frequency macro weight adjustment utilities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping


@dataclass(frozen=True)
class MacroWeightDecision:
    adjusted_weight: float
    adjustment_reason: str
    baseline_weight: float


def _month_phase(day: int) -> str:
    if day <= 7:
        return "early"
    if day <= 20:
        return "mid"
    return "late"


def adjust_macro_weight(
    baseline_weight: float,
    market_data: Mapping[str, float | int | str],
    now: datetime | None = None,
) -> MacroWeightDecision:
    """Adjust macro weight using high-frequency rates when PMI is stale.

    Rules:
    - Early month: keep baseline (PMI freshness period).
    - Mid/Late month: tilt by 10Y yield move in bps.
      - <= -10 bps: risk-on, reduce macro defensive weight by 3 pts.
      - >= +10 bps: risk-off, increase macro defensive weight by 3 pts.
      - otherwise: keep baseline.
    """
    ref = now or datetime.now(timezone.utc)
    phase = _month_phase(ref.day)

    y10_chg_bps = float(market_data.get("cn10y_yield_chg_bps", 0.0))

    if phase == "early":
        return MacroWeightDecision(
            adjusted_weight=baseline_weight,
            baseline_weight=baseline_weight,
            adjustment_reason="PMI_fresh_keep_baseline",
        )

    if y10_chg_bps <= -10:
        return MacroWeightDecision(
            adjusted_weight=max(0.0, baseline_weight - 0.03),
            baseline_weight=baseline_weight,
            adjustment_reason="mid_month_rate_drop_reduce_macro",
        )

    if y10_chg_bps >= 10:
        return MacroWeightDecision(
            adjusted_weight=min(1.0, baseline_weight + 0.03),
            baseline_weight=baseline_weight,
            adjustment_reason="mid_month_rate_rise_increase_macro",
        )

    return MacroWeightDecision(
        adjusted_weight=baseline_weight,
        baseline_weight=baseline_weight,
        adjustment_reason="mid_month_rate_flat_keep_baseline",
    )
