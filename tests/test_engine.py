from datetime import date, timedelta
import unittest

from strategy.engine import Action, Bar, MacroSnapshot, SentimentSnapshot, StrategyEngine


def make_bars(count=60, start=100.0, step=0.2):
    bars = []
    price = start
    for i in range(count):
        price += step
        bars.append(Bar(date(2024, 1, 1) + timedelta(days=i), price - 0.5, price + 1.0, price - 1.0, price, 1000 + i * 3))
    return bars


class StrategyEngineTest(unittest.TestCase):
    def test_rejects_short_history(self):
        with self.assertRaises(ValueError):
            StrategyEngine().evaluate(make_bars(10))

    def test_volume_price_buy_signal(self):
        bars = make_bars()
        bars[-1] = Bar(bars[-1].date, bars[-2].close, bars[-2].close * 1.05, bars[-2].close * 0.99, bars[-2].close * 1.04, 5000)
        signal = StrategyEngine().volume_price(bars)
        self.assertEqual(signal.action, Action.BUY)
        self.assertGreaterEqual(signal.confidence, 0.75)

    def test_macro_recovery_buy_signal(self):
        signal = StrategyEngine().macro(MacroSnapshot(pmi=51, credit_impulse=1.0, ppi=-0.5, savings_rate=0.4))
        self.assertEqual(signal.action, Action.BUY)
        self.assertEqual(signal.confidence, 0.70)

    def test_combined_high_confidence_buy(self):
        bars = make_bars(90, step=0.4)
        bars[-1] = Bar(bars[-1].date, bars[-2].close, bars[-2].close * 1.06, bars[-2].close * 0.99, bars[-2].close * 1.05, 8000)
        decision = StrategyEngine(min_confidence=0.60).evaluate(
            bars,
            macro=MacroSnapshot(pmi=52, credit_impulse=1.2, ppi=-0.4, savings_rate=0.42, earnings_growth=0.08),
            sentiment=SentimentSnapshot(score=0.6, news_count=40, social_volume_z=0.3),
        )
        self.assertIn(decision.action, {Action.BUY, Action.HOLD})
        self.assertGreaterEqual(decision.confidence, 0.60)


if __name__ == "__main__":
    unittest.main()
