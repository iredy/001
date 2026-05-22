from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Tuple


class MarketRegime(str, Enum):
    DEPRESSION = "depression"
    RECOVERY = "recovery"
    BOOM = "boom"
    SLOWDOWN = "slowdown"


class Decision(str, Enum):
    BUY = "buy"
    HOLD = "hold"
    REDUCE = "reduce"
    EXIT = "exit"
    WATCHLIST = "watchlist"


@dataclass
class MacroInput:
    pmi: float
    credit_impulse: float
    inventory_cycle: float
    risk_free_rate_trend: float


@dataclass
class CompanyInput:
    ticker: str
    physical_truth: float
    economic_truth: float
    behavioral_truth: float
    semi_revenue_yoy: float
    semi_gross_margin: float
    pv_loss_narrowing: bool
    operating_cashflow_improving: bool
    valuation_discount: float
    debt_ratio: float


@dataclass
class WyckoffInput:
    in_long_term_support_zone: bool
    spring_detected: bool
    lps_detected: bool
    sos_detected: bool
    rebound_volume_ratio: float
    failed_effort: bool


@dataclass
class RiskConfig:
    max_position: float = 0.30
    satellite_cap: float = 0.10
    probe_position: float = 0.05
    per_trade_risk: float = 0.01


@dataclass
class StrategyOutput:
    ticker: str
    regime: MarketRegime
    truth_score: float
    signal_score: float
    valuation_score: float
    decision: Decision
    target_position: float
    reasons: List[str] = field(default_factory=list)


class IntegratedFramework:
    """Macro + truth framework + valuation + wyckoff + risk unified engine."""

    def __init__(self, risk: RiskConfig | None = None) -> None:
        self.risk = risk or RiskConfig()

    def detect_regime(self, macro: MacroInput) -> Tuple[MarketRegime, float]:
        score = 0.0
        score += 0.35 if macro.pmi >= 50 else 0.15
        score += 0.25 if macro.credit_impulse > 0 else 0.10
        score += 0.20 if macro.inventory_cycle > 0 else 0.10
        score += 0.20 if macro.risk_free_rate_trend < 0 else 0.10

        if score >= 0.75:
            return MarketRegime.RECOVERY, score
        if score >= 0.60:
            return MarketRegime.SLOWDOWN, score
        if score >= 0.45:
            return MarketRegime.DEPRESSION, score
        return MarketRegime.BOOM, score

    @staticmethod
    def score_truth(company: CompanyInput) -> float:
        return round((company.physical_truth + company.economic_truth + company.behavioral_truth) / 3, 2)

    @staticmethod
    def score_valuation(company: CompanyInput) -> float:
        base = company.valuation_discount
        penalty = 0.15 if company.debt_ratio > 0.70 else 0
        return round(max(0.0, min(1.0, base - penalty)), 2)

    @staticmethod
    def score_wyckoff(signal: WyckoffInput) -> float:
        score = 0.0
        if signal.in_long_term_support_zone:
            score += 0.20
        if signal.spring_detected:
            score += 0.20
        if signal.lps_detected:
            score += 0.20
        if signal.sos_detected:
            score += 0.25
        if signal.rebound_volume_ratio >= 1.2:
            score += 0.15
        if signal.failed_effort:
            score -= 0.40
        return round(max(0.0, min(1.0, score)), 2)

    def evaluate(self, macro: MacroInput, company: CompanyInput, signal: WyckoffInput) -> StrategyOutput:
        regime, _ = self.detect_regime(macro)
        truth = self.score_truth(company)
        valuation = self.score_valuation(company)
        signal_score = self.score_wyckoff(signal)

        reasons: List[str] = []
        hard_flags = 0
        if company.semi_revenue_yoy > 0.20:
            hard_flags += 1
            reasons.append("半导体材料收入增长达标")
        if company.semi_gross_margin >= 0.18:
            hard_flags += 1
            reasons.append("半导体材料毛利率达标")
        if company.pv_loss_narrowing:
            hard_flags += 1
            reasons.append("光伏亏损收窄")
        if company.operating_cashflow_improving:
            hard_flags += 1
            reasons.append("经营现金流改善")

        if signal.failed_effort:
            return StrategyOutput(company.ticker, regime, truth, signal_score, valuation, Decision.EXIT, 0.0, ["努力无结果，熔断退出"])

        if truth >= 0.70 and signal_score >= 0.65 and valuation >= 0.50 and hard_flags >= 3:
            target = self.risk.max_position if regime in (MarketRegime.RECOVERY, MarketRegime.BOOM) else 0.20
            return StrategyOutput(company.ticker, regime, truth, signal_score, valuation, Decision.BUY, target, reasons)

        if truth >= 0.60 and signal_score >= 0.45 and hard_flags >= 2:
            return StrategyOutput(company.ticker, regime, truth, signal_score, valuation, Decision.HOLD, self.risk.probe_position, reasons)

        if hard_flags <= 1 and valuation < 0.4:
            return StrategyOutput(company.ticker, regime, truth, signal_score, valuation, Decision.REDUCE, 0.0, ["基本面触发项不足，估值缓冲不足"])

        return StrategyOutput(company.ticker, regime, truth, signal_score, valuation, Decision.WATCHLIST, 0.0, ["等待LPS/SOS确认"])


def demo() -> Dict[str, str]:
    framework = IntegratedFramework()
    macro = MacroInput(pmi=50.8, credit_impulse=0.4, inventory_cycle=0.2, risk_free_rate_trend=-0.1)
    company = CompanyInput(
        ticker="002129.SZ",
        physical_truth=0.76,
        economic_truth=0.62,
        behavioral_truth=0.71,
        semi_revenue_yoy=0.24,
        semi_gross_margin=0.19,
        pv_loss_narrowing=True,
        operating_cashflow_improving=False,
        valuation_discount=0.58,
        debt_ratio=0.66,
    )
    signal = WyckoffInput(
        in_long_term_support_zone=True,
        spring_detected=True,
        lps_detected=True,
        sos_detected=False,
        rebound_volume_ratio=1.25,
        failed_effort=False,
    )
    result = framework.evaluate(macro, company, signal)
    return {
        "ticker": result.ticker,
        "decision": result.decision.value,
        "target_position": f"{result.target_position:.0%}",
        "truth_score": str(result.truth_score),
        "signal_score": str(result.signal_score),
        "reasons": "; ".join(result.reasons),
    }


if __name__ == "__main__":
    print(demo())
