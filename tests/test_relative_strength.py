from strategy.relative_strength import calculate_relative_strength, enrich_relative_strength


def test_calculate_relative_strength_outperform():
    decision = calculate_relative_strength(4.2, 2.7, threshold_pct=1.0)
    assert decision.relative_strength_pct == 1.5
    assert decision.relative_strength_phase == "outperform"


def test_calculate_relative_strength_underperform():
    decision = calculate_relative_strength(-2.5, -0.5, threshold_pct=1.0)
    assert decision.relative_strength_pct == -2.0
    assert decision.relative_strength_phase == "underperform"


def test_enrich_relative_strength_uses_benchmark_alias():
    enriched = enrich_relative_strength(
        {
            "stock_return_pct": 3.0,
            "kcb50_return_pct": 2.4,
            "relative_strength_threshold_pct": 0.5,
        }
    )
    assert enriched["relative_strength_pct"] == 0.6
    assert enriched["relative_strength_phase"] == "outperform"


def test_enrich_relative_strength_is_noop_when_missing_benchmark():
    enriched = enrich_relative_strength({"stock_return_pct": 3.0})
    assert "relative_strength_pct" not in enriched
