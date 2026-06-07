"""Data models for mid-cycle high/low rotation monitoring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PoolName = Literal["high", "low", "neutral"]
SignalDirection = Literal["high_to_low", "low_to_high", "sector_rotation", "no_rotation"]


@dataclass(frozen=True)
class SecuritySnapshot:
    """One security's medium-cycle state on an observation date.

    Values are intentionally expressed as normalized, comparable features so the
    monitor is not tied to a specific data vendor. Percent fields use decimal
    notation: ``-0.0781`` means -7.81%.
    """

    symbol: str
    name: str
    sector: str
    board: str
    close: float
    pct_change: float
    relative_strength: float
    position_60d: float
    position_120d: float
    ma20_slope: float
    ma60_slope: float
    drawdown_60d: float
    turnover_ratio: float = 0.0
    volume_ratio: float = 1.0


@dataclass(frozen=True)
class MonitorConfig:
    """Thresholds used to classify medium-cycle high/low pools."""

    high_position_threshold: float = 0.72
    low_position_threshold: float = 0.32
    high_rs_threshold: float = 0.4
    low_rs_threshold: float = -0.8
    weak_rs_threshold: float = -2.0
    strong_rs_threshold: float = 0.6
    steep_drawdown_threshold: float = -0.18
    rebound_pct_threshold: float = 0.006
    high_breakdown_score: float = 3.0
    low_repair_score: float = 3.0
    rotation_gap_threshold: float = 1.2


@dataclass(frozen=True)
class PoolMember:
    """A security classified into one monitoring pool with explanation."""

    snapshot: SecuritySnapshot
    pool: PoolName
    score: float
    risk_score: float
    repair_score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RotationSignal:
    """Cross-pool or cross-sector rotation signal."""

    direction: SignalDirection
    source: str
    target: str
    strength: float
    summary: str
