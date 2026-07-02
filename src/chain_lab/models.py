from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class Segment(str, Enum):
    """Position in the AI-memory-consumer-electronics value chain."""

    UPSTREAM = "upstream_materials_equipment"
    MIDSTREAM = "midstream_chip_foundry_memory"
    DOWNSTREAM = "downstream_consumer_terminal"
    APPLICATION = "ai_application"


ValuationModel = Literal["PS_EV_EBITDA", "DCF_DDM", "PEG_PE"]


@dataclass(frozen=True)
class ScenarioAssumption:
    """Macro and industry assumptions for a scenario run.

    Values are expressed as intuitive multipliers or percentages so analysts can
    tune them without changing the scoring engine.
    """

    name: str = "2026_mid_memory_chipflation"
    dram_yoy_price_change: float = 5.0
    hbm_margin: float = 0.80
    consumer_price_pass_through: float = 0.20
    local_memory_priority: float = 0.75
    supply_release_year: int = 2027
    bull_market_liquidity: float = 0.65
    geopolitical_risk: float = 0.55


@dataclass(frozen=True)
class Company:
    """Research target with normalized factor inputs from 0.0 to 1.0."""

    ticker: str
    name: str
    segment: Segment
    moat: float
    growth: float
    margin_power: float
    capex_intensity: float
    local_supply_access: float
    ai_edge_exposure: float
    balance_sheet_strength: float
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for field_name in (
            "moat",
            "growth",
            "margin_power",
            "capex_intensity",
            "local_supply_access",
            "ai_edge_exposure",
            "balance_sheet_strength",
        ):
            value = getattr(self, field_name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field_name} must be between 0.0 and 1.0")


@dataclass(frozen=True)
class WyckoffObservation:
    """Minimal Wyckoff spring checklist for execution discipline."""

    broke_support: bool
    break_volume_ratio: float
    test_spread_narrowed: bool
    test_volume_ratio: float
    demand_candle_volume_ratio: float
    demand_candle_close_strength: float
