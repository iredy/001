"""Conflict-aware optimizer for STAR 50 style stock-analysis model output.

The module turns raw factor rows into safer, explainable decisions by enforcing
risk gates, lowering confidence when signals conflict, and assigning a compact
watch-list tier.  It intentionally uses only the Python standard library so it
can run in lightweight research pipelines.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import IntEnum
from typing import Iterable, Sequence


class Signal(IntEnum):
    """Ordered trading signal used for deterministic min/max operations."""

    STRONG_SELL = -2
    SELL = -1
    HOLD = 0
    BUY = 1
    STRONG_BUY = 2

    @classmethod
    def parse(cls, value: str | "Signal") -> "Signal":
        if isinstance(value, Signal):
            return value
        normalized = value.strip().lower().replace("-", "_")
        aliases = {
            "strongsell": "strong_sell",
            "strong_sell": "strong_sell",
            "sell": "sell",
            "hold": "hold",
            "buy": "buy",
            "strongbuy": "strong_buy",
            "strong_buy": "strong_buy",
        }
        try:
            return cls[aliases[normalized].upper()]
        except KeyError as exc:
            raise ValueError(f"unknown signal: {value!r}") from exc

    def label(self) -> str:
        return self.name.lower()


@dataclass(frozen=True)
class RawStockSignal:
    """Input row produced by the original quantitative/LLM model."""

    rank: int
    symbol: str
    close: float
    change_pct: float
    signal: Signal | str
    score: float
    confidence: float
    pr11_position: str
    pr11_timing: str
    pr12_validation: str
    technical_score: float
    fundamental_score: float

    def normalized(self) -> "RawStockSignal":
        return replace(
            self,
            signal=Signal.parse(self.signal),
            pr11_position=self.pr11_position.strip().lower(),
            pr11_timing=self.pr11_timing.strip().lower(),
            pr12_validation=self.pr12_validation.strip().lower(),
        )


@dataclass(frozen=True)
class OptimizedStockSignal:
    """Output row with conflict-aware signal, confidence, tier, and reasons."""

    raw: RawStockSignal
    final_signal: Signal
    adjusted_confidence: float
    conflict_count: int
    tier: str
    reasons: tuple[str, ...]


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _risk_gate(signal: Signal, row: RawStockSignal, reasons: list[str]) -> Signal:
    final = signal
    if row.pr11_position == "high" and row.pr11_timing == "avoid" and row.pr12_validation == "bearish":
        final = min(final, Signal.HOLD)
        reasons.append("高位/避免且PR12 bearish，信号上限降为 hold")
    elif row.pr11_position == "high" and row.pr12_validation == "bearish":
        final = min(final, Signal.HOLD)
        reasons.append("高位且PR12 bearish，禁止追涨买入")

    if row.fundamental_score < 0.20 and final > Signal.SELL:
        final = Signal.SELL
        reasons.append("基本面评分低于0.20，信号降为 sell")
    elif row.fundamental_score < 0.40 and final > Signal.HOLD:
        final = Signal.HOLD
        reasons.append("基本面评分低于0.40，买入信号降为 hold")

    if row.change_pct >= 6.0 and row.pr11_position == "high" and final > Signal.HOLD:
        final = Signal.HOLD
        reasons.append("高位单日大涨超过6%，降低追高风险")

    return final


def _score_alignment(signal: Signal, row: RawStockSignal, reasons: list[str]) -> Signal:
    final = signal
    if row.score >= 0.25 and final <= Signal.SELL and row.fundamental_score >= 0.50:
        final = Signal.HOLD
        reasons.append("量化分数较高但原信号偏空，先上调为 hold 并等待验证")
    if row.score <= -0.10 and final >= Signal.BUY:
        final = Signal.HOLD
        reasons.append("量化分数为负，买入信号降为 hold")
    return final


def _count_conflicts(original: Signal, final: Signal, row: RawStockSignal) -> int:
    conflicts = 0
    if row.score >= 0.25 and original <= Signal.HOLD:
        conflicts += 1
    if row.score < 0.05 and original >= Signal.BUY:
        conflicts += 1
    if row.pr11_position == "high" and row.pr11_timing in {"avoid", "cautious", "cau"} and original >= Signal.BUY:
        conflicts += 1
    if row.pr12_validation == "bearish" and original >= Signal.BUY:
        conflicts += 1
    if row.pr11_position == "low" and row.pr11_timing in {"fav", "favorable"} and row.pr12_validation == "bullish" and original <= Signal.SELL:
        conflicts += 1
    if row.fundamental_score < 0.40 and original >= Signal.BUY:
        conflicts += 1
    if original != final:
        conflicts += 1
    return conflicts


def _tier(final: Signal, row: RawStockSignal, conflicts: int) -> str:
    if (
        final >= Signal.BUY
        and row.pr11_position == "low"
        and row.pr11_timing in {"fav", "favorable"}
        and row.pr12_validation == "bullish"
        and row.fundamental_score >= 0.80
        and conflicts <= 1
    ):
        return "A_core"
    if final >= Signal.HOLD and conflicts <= 2 and row.fundamental_score >= 0.50:
        return "B_watch"
    if row.pr11_position == "low" and row.pr12_validation == "bullish":
        return "C_reversal_high_risk"
    return "D_avoid_or_reduce"


def optimize_signal(row: RawStockSignal) -> OptimizedStockSignal:
    """Optimize one raw row using deterministic conflict and risk rules."""

    normalized = row.normalized()
    original = Signal.parse(normalized.signal)
    reasons: list[str] = []

    final = _risk_gate(original, normalized, reasons)
    final = _score_alignment(final, normalized, reasons)

    conflicts = _count_conflicts(original, final, normalized)
    confidence = clamp(normalized.confidence - 0.08 * conflicts)
    if not reasons:
        reasons.append("信号、位置、PR12与基本面未触发主要冲突规则")

    return OptimizedStockSignal(
        raw=normalized,
        final_signal=final,
        adjusted_confidence=round(confidence, 4),
        conflict_count=conflicts,
        tier=_tier(final, normalized, conflicts),
        reasons=tuple(reasons),
    )


def optimize_universe(rows: Iterable[RawStockSignal]) -> list[OptimizedStockSignal]:
    """Optimize and rank a universe by tier, final signal, score, and confidence."""

    tier_order = {"A_core": 0, "B_watch": 1, "C_reversal_high_risk": 2, "D_avoid_or_reduce": 3}
    optimized = [optimize_signal(row) for row in rows]
    return sorted(
        optimized,
        key=lambda item: (
            tier_order[item.tier],
            -int(item.final_signal),
            -item.raw.score,
            -item.adjusted_confidence,
            item.raw.rank,
        ),
    )


def validate_universe(rows: Sequence[RawStockSignal], expected_count: int = 50) -> list[str]:
    """Return data-quality warnings before model output is trusted."""

    warnings: list[str] = []
    if len(rows) != expected_count:
        warnings.append(f"成分股数量为{len(rows)}，不是预期的{expected_count}")
    seen: set[str] = set()
    for row in rows:
        if row.symbol in seen:
            warnings.append(f"重复标的: {row.symbol}")
        seen.add(row.symbol)
        if not 0.0 <= row.confidence <= 1.0:
            warnings.append(f"{row.symbol} 置信度超出0-1范围")
        if not -2.0 <= row.score <= 2.0:
            warnings.append(f"{row.symbol} 分数疑似异常: {row.score}")
    return warnings
