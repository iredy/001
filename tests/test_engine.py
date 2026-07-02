from chain_lab.engine import evaluate_company, valuation_model_for, wyckoff_spring_signal
from chain_lab.models import Company, ScenarioAssumption, Segment, WyckoffObservation


def test_capex_heavy_midstream_uses_sales_based_model() -> None:
    assert valuation_model_for(Segment.MIDSTREAM, 0.9) == "PS_EV_EBITDA"


def test_local_supply_access_improves_actionability() -> None:
    scenario = ScenarioAssumption()
    protected = Company("A", "Protected", Segment.DOWNSTREAM, 0.7, 0.8, 0.7, 0.3, 0.9, 0.8, 0.8)
    exposed = Company("B", "Exposed", Segment.DOWNSTREAM, 0.7, 0.8, 0.7, 0.3, 0.1, 0.8, 0.8)

    assert evaluate_company(protected, scenario).strategic_score > evaluate_company(exposed, scenario).strategic_score


def test_wyckoff_spring_requires_low_supply_and_demand_confirmation() -> None:
    observation = WyckoffObservation(True, 0.4, True, 0.35, 1.5, 0.8)
    assert wyckoff_spring_signal(observation) == "right_side_entry_confirmed"


def test_high_volume_breakdown_fails_spring() -> None:
    observation = WyckoffObservation(True, 1.4, True, 0.35, 1.5, 0.8)
    assert wyckoff_spring_signal(observation) == "failed_spring_supply_too_large"
