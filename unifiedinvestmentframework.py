#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List

from openclaw_7m import MacroInput, MacroStrategy, score_to_signal
from tools.strategyragindexer import StrategyRAGIndexer


@dataclass
class StrategyOutput:
    action: str
    confidence: float
    score: float
    regime: str = ""


class BaseStrategy:
    name = "BaseStrategy"

    def analyze(self, current_data: Dict) -> StrategyOutput:
        raise NotImplementedError


class MacroStrategyAdapter(BaseStrategy):
    name = "MacroStrategy"

    def __init__(self) -> None:
        self.engine = MacroStrategy(high_savings_threshold=35.0)

    def analyze(self, current_data: Dict) -> StrategyOutput:
        m = MacroInput(**current_data["macro"])
        out = self.engine.analyze(m)
        return StrategyOutput(action=out.signal, confidence=out.confidence, score=out.score, regime=out.regime)


class DummyPriceStrategy(BaseStrategy):
    def __init__(self, name: str, fallback_score: float):
        self.name = name
        self.fallback_score = fallback_score

    def analyze(self, current_data: Dict) -> StrategyOutput:
        score = float(current_data.get("structured_scores", {}).get(self.name, self.fallback_score))
        action = score_to_signal(score)
        return StrategyOutput(action=action, confidence=abs(score), score=score)


class UnifiedInvestmentFramework:
    WEIGHTS = {
        "MacroStrategy": 0.25,
        "DensityStrategy": 0.15,
        "SwingStrategy": 0.15,
        "VolumePriceStrategy": 0.15,
        "TechnicalStrategy": 0.20,
        "SmartTrigger": 0.10,
    }

    def __init__(self, use_rag: bool = True, rag_db: str = "strategy_rag.sqlite3"):
        self.strategies: List[BaseStrategy] = [
            MacroStrategyAdapter(),
            DummyPriceStrategy("DensityStrategy", 0.05),
            DummyPriceStrategy("SwingStrategy", 0.10),
            DummyPriceStrategy("VolumePriceStrategy", 0.15),
            DummyPriceStrategy("TechnicalStrategy", 0.10),
            DummyPriceStrategy("SmartTrigger", 0.00),
        ]
        self.use_rag = use_rag
        self.rag_engine = StrategyRAGIndexer(rag_db) if use_rag else None

    def evaluate_all(self, current_data: Dict) -> Dict:
        base_signals: Dict[str, StrategyOutput] = {}
        for s in self.strategies:
            base_signals[s.name] = s.analyze(current_data)

        if self.use_rag and "MacroStrategy" in base_signals:
            macro_signal = base_signals["MacroStrategy"]
            query_text = self._build_macro_query(macro_signal, current_data)
            docs = self.rag_engine.search(query_text, top_k=3)
            llm_response = self.query_local_llm(macro_signal, docs)
            corrected = self._parse_confidence(llm_response, macro_signal.confidence)
            macro_signal.confidence = corrected
            macro_signal.score = corrected if macro_signal.action == "BUY" else (-corrected if macro_signal.action == "SELL" else 0.0)

        final_score = self._calculate_weighted_score(base_signals)
        return {
            "final_score": round(final_score, 4),
            "final_signal": score_to_signal(final_score),
            "signals": {
                k: {
                    "action": v.action,
                    "confidence": round(v.confidence, 4),
                    "score": round(v.score, 4),
                    "regime": v.regime,
                }
                for k, v in base_signals.items()
            },
        }

    def _build_macro_query(self, macro_signal: StrategyOutput, current_data: Dict) -> str:
        feat = current_data.get("macro", {})
        return (
            f"regime {macro_signal.regime} action {macro_signal.action} "
            f"confidence {macro_signal.confidence:.2f} "
            f"credit_impulse {feat.get('credit_impulse')} pmi {feat.get('pmi')} "
            f"gdp {feat.get('gdp_yoy')} ppi {feat.get('ppi_yoy')} "
            f"savings_rate {feat.get('savings_rate')} usdcny_yoy {feat.get('usdcny_yoy')} "
            f"lpr_1y {feat.get('lpr_1y')}"
        )

    @staticmethod
    def query_local_llm(macro_signal: StrategyOutput, docs) -> str:
        """本地 LLM 占位逻辑：若检索到“假复苏/通缩/高储蓄”等关键词，则降置信度。"""
        risk_words = ("假复苏", "通缩", "高储蓄", "需求疲软", "陷阱")
        hit = 0
        for d in docs:
            content = f"{d.title} {d.content}"
            if any(w in content for w in risk_words):
                hit += 1
        if hit >= 2 and macro_signal.action == "BUY":
            return "confidence=0.30 reason=historical weak recovery risk"
        if hit == 1 and macro_signal.action == "BUY":
            return "confidence=0.45 reason=partial conflict"
        return f"confidence={macro_signal.confidence:.2f} reason=no strong conflict"

    @staticmethod
    def _parse_confidence(text: str, default: float) -> float:
        m = re.search(r"confidence\s*=\s*([0-9]*\.?[0-9]+)", text)
        if not m:
            return default
        v = float(m.group(1))
        return max(0.0, min(1.0, v))

    def _calculate_weighted_score(self, signals: Dict[str, StrategyOutput]) -> float:
        total = 0.0
        for name, out in signals.items():
            total += self.WEIGHTS.get(name, 0.0) * out.score
        return total


def demo() -> None:
    fw = UnifiedInvestmentFramework(use_rag=True)

    # 演示插入几条RAG文档
    fw.rag_engine.upsert_documents(
        [
            {
                "source": "tradejournal",
                "title": "2024-08 假复苏样本",
                "content": "信用脉冲上行但PPI通缩+高储蓄，做多回撤显著。",
                "metadata_json": "{}",
            },
            {
                "source": "broker_report",
                "title": "流动性陷阱阶段研报摘要",
                "content": "需求疲软导致盈利兑现慢，建议下调进攻仓位。",
                "metadata_json": "{}",
            },
        ]
    )

    current_data = {
        "macro": {
            "credit_impulse": 5.2,
            "m2_yoy": 8.5,
            "savings_rate": 45.0,
            "cpi_yoy": 0.8,
            "ppi_yoy": -2.1,
            "hh_credit_yoy": 3.5,
            "retail_sales_yoy": 4.2,
            "pmi": 49.8,
            "gdp_yoy": 4.8,
            "usdcny_yoy": 2.6,
            "lpr_1y": 3.45,
        },
        "structured_scores": {
            "DensityStrategy": 0.05,
            "SwingStrategy": 0.10,
            "VolumePriceStrategy": 0.15,
            "TechnicalStrategy": 0.10,
            "SmartTrigger": 0.0,
        },
    }

    print(fw.evaluate_all(current_data))


if __name__ == "__main__":
    demo()
