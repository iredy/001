from datetime import date
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest

from rag_index_matcher import (
    BEARISH,
    BULLISH,
    CsvIndexDataProvider,
    IndexBar,
    StrategyRecord,
    TimeSeriesRAGIndexMatcher,
    align_to_trading_day,
    extract_first_date,
    infer_signal,
    rank_and_filter_strategies,
)


class FakeIndexProvider:
    def __init__(self):
        self.requests = []

    def get_index_bars(self, symbol, start_date, end_date):
        self.requests.append((symbol, start_date, end_date))
        if symbol == "000688.SH":
            closes = [100, 103, 106, 105, 108, 110]
        else:
            closes = [3000, 3010, 3030, 3040, 3050, 3060]
        return [
            IndexBar(date(2024, 11, 18 + idx), close, close, close, close)
            for idx, close in enumerate(closes)
        ]


class RagIndexMatcherTests(unittest.TestCase):
    def test_extracts_date_and_bullish_signal_from_rag_text(self):
        self.assertEqual(extract_first_date("2024-11-19 企稳反弹"), date(2024, 11, 19))
        self.assertEqual(infer_signal("2024-11-19 科创50 企稳反弹，建议加仓"), BULLISH)

    def test_signal_inference_penalizes_false_bullish_phrases(self):
        self.assertEqual(infer_signal("2024-11-19 反弹乏力，尚未企稳，建议减仓"), BEARISH)

    def test_aligns_weekend_or_missing_day_to_previous_bar_within_lookback(self):
        dates = [date(2024, 11, 18), date(2024, 11, 19), date(2024, 11, 22)]
        self.assertEqual(align_to_trading_day(dates, date(2024, 11, 20), lookback_days=2), 1)

    def test_retrieve_match_evaluate_and_build_llm_samples(self):
        provider = FakeIndexProvider()
        matcher = TimeSeriesRAGIndexMatcher(provider)

        def rag_retriever(query):
            self.assertIn("企稳反弹", query)
            return ["2024-11-19 科创50 企稳反弹，建议加仓"]

        matches, summary = matcher.retrieve_match_and_evaluate(
            "2024-11-19 企稳反弹",
            rag_retriever,
            horizon_days=3,
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].index_symbol, "000688.SH")
        self.assertTrue(matches[0].direction_correct)
        self.assertGreater(matches[0].forward_return, 0)
        self.assertEqual(summary.accuracy, 1.0)
        self.assertEqual(summary.weighted_accuracy, 1.0)

        samples = matcher.build_llm_learning_samples(matches)
        self.assertEqual(samples[0]["label"], "correct")
        self.assertEqual(samples[0]["strategy_signal"], "bullish")

    def test_rag_relevance_filter_removes_unrelated_hits(self):
        provider = FakeIndexProvider()
        matcher = TimeSeriesRAGIndexMatcher(provider)

        def rag_retriever(_query):
            return [
                "2024-11-19 科创50 企稳反弹，建议加仓",
                "2023-01-01 白酒板块看空风险，建议减仓",
            ]

        matches, summary = matcher.retrieve_match_and_evaluate(
            "2024-11-19 科创50 企稳反弹",
            rag_retriever,
            horizon_days=3,
            min_relevance_score=0.40,
        )
        self.assertEqual(len(matches), 1)
        self.assertIn("科创50", matches[0].strategy.text)
        self.assertEqual(summary.evaluated, 1)

    def test_rank_and_filter_deduplicates_and_keeps_best_hit(self):
        strategies = [
            StrategyRecord(date(2024, 11, 19), BULLISH, "2024-11-19 科创50 企稳反弹", confidence=0.3),
            StrategyRecord(date(2024, 11, 19), BULLISH, "2024-11-19 科创50 企稳反弹", confidence=0.9),
        ]
        ranked = rank_and_filter_strategies(strategies, "2024-11-19 科创50 企稳反弹")
        self.assertEqual(len(ranked), 1)
        self.assertGreater(ranked[0].confidence, 0.3)

    def test_csv_provider_filters_rows_for_symbol_and_date_range(self):
        with TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "sse.csv"
            csv_path.write_text(
                "trade_date,open,high,low,close,volume\n"
                "2024-11-18,3000,3010,2990,3005,100\n"
                "2024-11-19,3005,3030,3000,3025,120\n",
                encoding="utf-8",
            )
            provider = CsvIndexDataProvider({"000001.SH": csv_path})
            bars = provider.get_index_bars("000001.SH", date(2024, 11, 19), date(2024, 11, 19))
            self.assertEqual(len(bars), 1)
            self.assertEqual(bars[0]["close"], "3025")

    def test_explicit_strategy_record_uses_default_index(self):
        provider = FakeIndexProvider()
        matcher = TimeSeriesRAGIndexMatcher(provider)
        matches = matcher.match_strategies(
            [StrategyRecord(date(2024, 11, 19), BULLISH, "上证指数企稳反弹")],
            horizon_days=2,
        )
        self.assertEqual(matches[0].index_symbol, "000001.SH")


if __name__ == "__main__":
    unittest.main()
