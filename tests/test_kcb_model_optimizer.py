import unittest

from src.kcb_model_optimizer import RawStockSignal, Signal, optimize_signal, optimize_universe, validate_universe


class OptimizerTests(unittest.TestCase):
    def row(self, **overrides):
        base = dict(
            rank=1,
            symbol="测试股份",
            close=10.0,
            change_pct=0.0,
            signal="buy",
            score=0.20,
            confidence=0.85,
            pr11_position="low",
            pr11_timing="fav",
            pr12_validation="bullish",
            technical_score=0.54,
            fundamental_score=0.90,
        )
        base.update(overrides)
        return RawStockSignal(**base)

    def test_high_avoid_bearish_buy_is_downgraded(self):
        result = optimize_signal(
            self.row(symbol="沪硅产业", pr11_position="high", pr11_timing="avoid", pr12_validation="bearish")
        )
        self.assertEqual(result.final_signal, Signal.HOLD)
        self.assertGreaterEqual(result.conflict_count, 3)
        self.assertLess(result.adjusted_confidence, 0.85)
        self.assertEqual(result.tier, "D_avoid_or_reduce")

    def test_low_bullish_strong_candidate_gets_core_tier(self):
        result = optimize_signal(self.row(signal="strong_buy", score=0.28, fundamental_score=1.0))
        self.assertEqual(result.final_signal, Signal.STRONG_BUY)
        self.assertEqual(result.tier, "A_core")
        self.assertEqual(result.conflict_count, 0)

    def test_weak_fundamental_buy_is_downgraded_to_sell(self):
        result = optimize_signal(self.row(symbol="弱基本面", fundamental_score=0.05, score=0.28))
        self.assertEqual(result.final_signal, Signal.SELL)
        self.assertEqual(result.tier, "C_reversal_high_risk")

    def test_universe_sort_prioritizes_core_names(self):
        rows = [
            self.row(rank=2, symbol="观察", signal="hold", fundamental_score=0.70),
            self.row(rank=1, symbol="核心", signal="buy", fundamental_score=0.95, score=0.30),
        ]
        self.assertEqual(optimize_universe(rows)[0].raw.symbol, "核心")

    def test_validate_universe_finds_count_duplicate_and_confidence(self):
        warnings = validate_universe([
            self.row(symbol="重复"),
            self.row(rank=2, symbol="重复", confidence=1.2),
        ])
        self.assertTrue(any("不是预期" in warning for warning in warnings))
        self.assertTrue(any("重复标的" in warning for warning in warnings))
        self.assertTrue(any("置信度" in warning for warning in warnings))


if __name__ == "__main__":
    unittest.main()
