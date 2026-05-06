import unittest

from macro_adjust import (
    BASE_WEIGHTS,
    SectorDeviationConfig,
    apply_sector_deviation_adjustment,
    score_with_macro_adjustment,
    sector_deviation_penalty,
    weighted_score,
)


class MacroAdjustTest(unittest.TestCase):
    def test_weighted_score_uses_base_formula(self):
        factors = {
            "macro": 1.0,
            "density": 0.5,
            "technical": 0.25,
            "sentiment": 0.0,
            "swing": -0.5,
            "volume_price": 1.0,
        }

        expected = sum(factors[name] * weight for name, weight in BASE_WEIGHTS.items())

        self.assertAlmostEqual(weighted_score(factors), expected)

    def test_no_penalty_below_warning_threshold(self):
        self.assertEqual(sector_deviation_penalty(0.08), 0.0)

    def test_extreme_deviation_penalty_is_bounded(self):
        config = SectorDeviationConfig(max_penalty=0.18, divergence_multiplier=1.25)

        self.assertAlmostEqual(
            sector_deviation_penalty(0.18, divergenceflag=True, config=config),
            0.225,
        )
        self.assertLessEqual(sector_deviation_penalty(0.50, divergenceflag=True), 1.0)

    def test_adjustment_reduces_but_does_not_override_by_default(self):
        adjusted = apply_sector_deviation_adjustment(0.42, 0.18, divergenceflag=True)

        self.assertAlmostEqual(adjusted, 0.195)

    def test_score_with_macro_adjustment_returns_telemetry(self):
        result = score_with_macro_adjustment(
            {
                "macro": 0.2,
                "density": 0.4,
                "technical": 0.6,
                "sentiment": 0.1,
                "swing": 0.3,
                "volume_price": 1.0,
            },
            ma5_deviation=0.18,
            divergenceflag=True,
        )

        self.assertEqual(result["divergenceflag"], True)
        self.assertAlmostEqual(result["sector_deviation_penalty"], 0.225)
        self.assertLess(result["adjusted_score"], result["raw_score"])


if __name__ == "__main__":
    unittest.main()
