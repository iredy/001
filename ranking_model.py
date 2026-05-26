"""Ranking model with STAR-market growth compensation.

This module implements a composite score and an optional growth compensation
term for high-growth sectors (e.g., STAR Market / 科创板).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreWeights:
    strategy: float = 0.70
    truth: float = 0.15
    valuation: float = 0.15

    def validate(self) -> None:
        total = self.strategy + self.truth + self.valuation
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"weights must sum to 1.0, got {total}")


@dataclass(frozen=True)
class GrowthCompensationConfig:
    """Compensate high-growth names penalized by truth/valuation.

    growth_factor: normalized growth signal in [0, 1], usually based on
    revenue growth, R&D intensity, and institutional position change.
    max_boost: max additive boost applied to the final score.
    activation: threshold for activation of compensation.
    """

    growth_factor: float
    max_boost: float = 0.12
    activation: float = 0.55

    def compensation(self) -> float:
        gf = min(max(self.growth_factor, 0.0), 1.0)
        if gf <= self.activation:
            return 0.0
        normalized = (gf - self.activation) / (1.0 - self.activation)
        return self.max_boost * normalized


def composite_score(
    strategy_score: float,
    truth_score: float,
    valuation_score: float,
    weights: ScoreWeights | None = None,
    growth_compensation: GrowthCompensationConfig | None = None,
) -> float:
    """Calculate final rank score.

    Base:
        score = 0.70 * strategy + 0.15 * truth + 0.15 * valuation

    With growth compensation:
        final = base + growth_compensation
    """

    w = weights or ScoreWeights()
    w.validate()

    base = (
        w.strategy * strategy_score
        + w.truth * truth_score
        + w.valuation * valuation_score
    )

    if growth_compensation is None:
        return base

    return base + growth_compensation.compensation()


def sector_adaptive_weights(market_regime: str) -> ScoreWeights:
    """Regime-aware weighting.

    - bull_growth: trend dominates (80/10/10)
    - defensive: quality + valuation dominates (60/20/20)
    - default: baseline (70/15/15)
    """

    regime = market_regime.strip().lower()
    if regime == "bull_growth":
        return ScoreWeights(strategy=0.80, truth=0.10, valuation=0.10)
    if regime == "defensive":
        return ScoreWeights(strategy=0.60, truth=0.20, valuation=0.20)
    return ScoreWeights()


if __name__ == "__main__":
    # Example: 澜起科技-like profile
    strategy = 0.66
    truth = 0.42
    valuation = 0.38

    base = composite_score(strategy, truth, valuation)
    improved = composite_score(
        strategy,
        truth,
        valuation,
        growth_compensation=GrowthCompensationConfig(growth_factor=0.82),
    )

    print(f"base_score={base:.4f}")
    print(f"with_growth_compensation={improved:.4f}")
