"""Macro score adjustment utilities for RAG-assisted quant signals.

This module keeps the base signal weights stable while allowing a temporary
risk-control haircut when RAG/LLM flags show a sector is materially extended.
The adjustment is intentionally bounded: it should reduce exposure for crowded
or over-extended sectors, not override the hard directional signal by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


BASE_WEIGHTS: dict[str, float] = {
    "macro": 0.25,
    "density": 0.20,
    "technical": 0.20,
    "sentiment": 0.15,
    "swing": 0.10,
    "volume_price": 0.10,
}


@dataclass(frozen=True)
class SectorDeviationConfig:
    """Configuration for the sector over-extension temporary correction.

    Attributes:
        ma5_warning_threshold: MA5 deviation above which a sector begins to
            receive a risk haircut. A value of 0.10 means +10%.
        ma5_extreme_threshold: MA5 deviation that receives the maximum
            configured haircut. A value of 0.18 means +18%.
        max_penalty: Maximum score haircut applied for an over-extended sector.
        divergence_multiplier: Extra penalty multiplier when RAG has already
            raised ``divergenceflag=true``.
        min_adjusted_score: Lower bound for adjusted scores to avoid turning a
            long signal into an outright short solely because of this guardrail.
    """

    ma5_warning_threshold: float = 0.10
    ma5_extreme_threshold: float = 0.18
    max_penalty: float = 0.18
    divergence_multiplier: float = 1.25
    min_adjusted_score: float = -1.0

    def __post_init__(self) -> None:
        if self.ma5_warning_threshold < 0:
            raise ValueError("ma5_warning_threshold must be non-negative")
        if self.ma5_extreme_threshold <= self.ma5_warning_threshold:
            raise ValueError("ma5_extreme_threshold must exceed ma5_warning_threshold")
        if not 0 <= self.max_penalty <= 1:
            raise ValueError("max_penalty must be between 0 and 1")
        if self.divergence_multiplier < 1:
            raise ValueError("divergence_multiplier must be at least 1")


def weighted_score(factors: Mapping[str, float], weights: Mapping[str, float] | None = None) -> float:
    """Return the weighted score for a normalized factor dictionary.

    Missing factors are treated as neutral ``0`` so callers can compute partial
    scores during intraday refreshes without branching.
    """

    active_weights = weights or BASE_WEIGHTS
    return sum(float(factors.get(name, 0.0)) * weight for name, weight in active_weights.items())


def sector_deviation_penalty(
    ma5_deviation: float,
    *,
    divergenceflag: bool = False,
    config: SectorDeviationConfig | None = None,
) -> float:
    """Calculate the temporary haircut for an over-extended sector.

    ``ma5_deviation`` is expected as a decimal ratio: ``0.18`` means price is
    18% above MA5. Values below the warning threshold produce no penalty. Values
    at or above the extreme threshold receive the configured maximum penalty.
    """

    cfg = config or SectorDeviationConfig()
    deviation = max(0.0, float(ma5_deviation))

    if deviation <= cfg.ma5_warning_threshold:
        return 0.0

    span = cfg.ma5_extreme_threshold - cfg.ma5_warning_threshold
    severity = min(1.0, (deviation - cfg.ma5_warning_threshold) / span)
    penalty = severity * cfg.max_penalty

    if divergenceflag:
        penalty *= cfg.divergence_multiplier

    return min(1.0, penalty)


def apply_sector_deviation_adjustment(
    score: float,
    ma5_deviation: float,
    *,
    divergenceflag: bool = False,
    config: SectorDeviationConfig | None = None,
) -> float:
    """Apply a bounded over-extension haircut to a final signal score."""

    cfg = config or SectorDeviationConfig()
    adjusted = float(score) - sector_deviation_penalty(
        ma5_deviation,
        divergenceflag=divergenceflag,
        config=cfg,
    )
    return max(cfg.min_adjusted_score, adjusted)


def score_with_macro_adjustment(
    factors: Mapping[str, float],
    *,
    ma5_deviation: float,
    divergenceflag: bool = False,
    weights: Mapping[str, float] | None = None,
    config: SectorDeviationConfig | None = None,
) -> dict[str, float | bool]:
    """Score factors and expose adjustment telemetry for trading logs.

    The returned dictionary is intentionally explicit so execution code can log
    both the hard model score and the temporary RAG-assisted risk haircut.
    """

    raw_score = weighted_score(factors, weights=weights)
    penalty = sector_deviation_penalty(
        ma5_deviation,
        divergenceflag=divergenceflag,
        config=config,
    )
    adjusted_score = apply_sector_deviation_adjustment(
        raw_score,
        ma5_deviation,
        divergenceflag=divergenceflag,
        config=config,
    )
    return {
        "raw_score": raw_score,
        "sector_deviation_penalty": penalty,
        "adjusted_score": adjusted_score,
        "divergenceflag": divergenceflag,
    }
