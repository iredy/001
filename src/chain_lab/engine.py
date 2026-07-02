from __future__ import annotations

from dataclasses import dataclass

from .models import Company, ScenarioAssumption, Segment, ValuationModel, WyckoffObservation


@dataclass(frozen=True)
class CompanyScore:
    company: Company
    valuation_model: ValuationModel
    strategic_score: float
    cost_advantage_score: float
    risk_score: float
    action: str
    rationale: tuple[str, ...]


def valuation_model_for(segment: Segment, capex_intensity: float) -> ValuationModel:
    if segment in {Segment.UPSTREAM, Segment.MIDSTREAM} and capex_intensity >= 0.55:
        return "PS_EV_EBITDA"
    if segment == Segment.DOWNSTREAM and capex_intensity < 0.55:
        return "DCF_DDM"
    return "PEG_PE"


def evaluate_company(company: Company, scenario: ScenarioAssumption) -> CompanyScore:
    """Score a company for the AI memory inflation cycle.

    The engine intentionally stays transparent: every factor is a weighted sum
    and the returned rationale exposes which business facts moved the score.
    """

    supply_cost_pressure = min(1.0, scenario.dram_yoy_price_change / 6.0)
    local_cost_shield = company.local_supply_access * scenario.local_memory_priority
    ai_demand_beta = (company.ai_edge_exposure + company.growth) / 2

    cost_advantage = max(0.0, local_cost_shield + company.margin_power * 0.35 - supply_cost_pressure * 0.35)
    strategic = (
        company.moat * 0.24
        + company.growth * 0.20
        + company.margin_power * 0.14
        + company.ai_edge_exposure * 0.18
        + company.balance_sheet_strength * 0.12
        + scenario.bull_market_liquidity * 0.12
    )
    if company.segment == Segment.MIDSTREAM:
        strategic += scenario.hbm_margin * 0.08
    if company.segment == Segment.DOWNSTREAM:
        strategic += scenario.consumer_price_pass_through * company.margin_power * 0.10

    risk = (
        scenario.geopolitical_risk * (1 - company.local_supply_access) * 0.34
        + company.capex_intensity * 0.22
        + supply_cost_pressure * (1 - company.margin_power) * 0.22
        + max(0.0, 0.55 - company.balance_sheet_strength) * 0.22
    )
    final_score = strategic + cost_advantage * 0.35 - risk * 0.40

    if final_score >= 0.78:
        action = "core_overweight"
    elif final_score >= 0.62:
        action = "accumulate_on_wyckoff_spring"
    elif final_score >= 0.48:
        action = "watchlist_wait_for_price_or_data"
    else:
        action = "avoid_until_cycle_risk_resets"

    rationale = [
        f"valuation={valuation_model_for(company.segment, company.capex_intensity)}",
        f"ai_demand_beta={ai_demand_beta:.2f}",
        f"local_cost_shield={local_cost_shield:.2f}",
        f"risk={risk:.2f}",
    ]
    return CompanyScore(
        company=company,
        valuation_model=valuation_model_for(company.segment, company.capex_intensity),
        strategic_score=round(final_score, 3),
        cost_advantage_score=round(cost_advantage, 3),
        risk_score=round(risk, 3),
        action=action,
        rationale=tuple(rationale + list(company.notes)),
    )


def wyckoff_spring_signal(observation: WyckoffObservation) -> str:
    """Classify a Wyckoff spring setup using volume/price discipline."""

    if not observation.broke_support:
        return "no_spring"
    if observation.break_volume_ratio > 0.85:
        return "failed_spring_supply_too_large"
    if not observation.test_spread_narrowed or observation.test_volume_ratio > 0.70:
        return "wait_for_successful_test"
    if observation.demand_candle_volume_ratio >= 1.35 and observation.demand_candle_close_strength >= 0.70:
        return "right_side_entry_confirmed"
    return "dead_cat_bounce_exit_or_wait"


def run_portfolio_screen(companies: list[Company], scenario: ScenarioAssumption) -> list[CompanyScore]:
    return sorted((evaluate_company(company, scenario) for company in companies), key=lambda item: item.strategic_score, reverse=True)


def render_markdown_report(scores: list[CompanyScore], scenario: ScenarioAssumption) -> str:
    lines = [
        f"# {scenario.name} research screen",
        "",
        "| Rank | Ticker | Name | Segment | Model | Score | Cost edge | Risk | Action |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for rank, score in enumerate(scores, start=1):
        company = score.company
        lines.append(
            "| {rank} | {ticker} | {name} | {segment} | {model} | {strategic:.3f} | {cost:.3f} | {risk:.3f} | {action} |".format(
                rank=rank,
                ticker=company.ticker,
                name=company.name,
                segment=company.segment.value,
                model=score.valuation_model,
                strategic=score.strategic_score,
                cost=score.cost_advantage_score,
                risk=score.risk_score,
                action=score.action,
            )
        )
    lines.extend(["", "## Rationale", ""])
    for score in scores:
        lines.append(f"### {score.company.name} ({score.company.ticker})")
        for item in score.rationale:
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"
