#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OpenClaw 7模块投资框架（可落地示例）
- 7个模块加权打分
- 模块7（宏观）支持“非典型复苏”识别
- 宏观模块输出下游约束（估值模块因子权重微调）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


# ========== 数据结构 ==========

@dataclass
class ModuleSignal:
    name: str
    weight: float
    signal: str           # BUY / HOLD / SELL
    confidence: float     # 0~1
    score: float          # -1~1
    note: str


@dataclass
class MacroInput:
    credit_impulse: float
    m2_yoy: float
    savings_rate: float
    cpi_yoy: float
    ppi_yoy: float
    hh_credit_yoy: float
    retail_sales_yoy: float
    pmi: float = 50.0
    gdp_yoy: float = 5.0
    usdcny_yoy: float = 0.0  # 正数代表人民币相对美元贬值压力
    lpr_1y: float = 3.45


@dataclass
class MacroOutput:
    regime: str
    signal: str
    confidence: float
    score: float
    note: str
    component_scores: Dict[str, float]
    downstream_adjustments: Dict[str, Dict[str, float]]


# ========== 工具函数 ==========

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def signal_to_score(signal: str, confidence: float) -> float:
    if signal == "BUY":
        return confidence
    if signal == "SELL":
        return -confidence
    return 0.0


def score_to_signal(score: float) -> str:
    if score >= 0.25:
        return "BUY"
    if score <= -0.25:
        return "SELL"
    return "HOLD"


# ========== 模块7：宏观策略（重点） ==========

class MacroStrategy:
    """
    支持“非典型复苏”识别：
    - credit_impulse > 0
    - ppi_yoy < 0
    - savings_rate > 阈值（默认 35%）
    """

    def __init__(self, high_savings_threshold: float = 35.0):
        self.high_savings_threshold = high_savings_threshold

    def analyze(self, x: MacroInput) -> MacroOutput:
        """将宏观指标拆为 5 组信号，再组合成模块7分数。

        使用方式：
        - PMI/GDP/社零：经济增长与景气方向
        - 社融代理(credit_impulse)/M2/LPR：流动性与货币政策
        - CPI/PPI：通胀/通缩风险
        - 美元兑人民币同比：外汇压力
        - 居民信贷/储蓄率：资产负债表修复程度
        """
        growth_score = clamp(
            0.40 * ((x.pmi - 50.0) / 2.0)
            + 0.35 * ((x.gdp_yoy - 5.0) / 2.0)
            + 0.25 * ((x.retail_sales_yoy - 3.0) / 3.0),
            -1.0,
            1.0,
        )
        liquidity_score = clamp(
            0.45 * (x.credit_impulse / 5.0)
            + 0.30 * ((x.m2_yoy - 7.0) / 3.0)
            + 0.25 * ((3.45 - x.lpr_1y) / 0.50),
            -1.0,
            1.0,
        )
        inflation_score = clamp(
            0.60 * (1.0 - abs(x.cpi_yoy - 2.0) / 2.0)
            + 0.40 * (1.0 - abs(x.ppi_yoy - 1.0) / 4.0),
            -1.0,
            1.0,
        )
        fx_score = clamp(-x.usdcny_yoy / 5.0, -1.0, 1.0)
        balance_sheet_score = clamp(
            0.55 * ((x.hh_credit_yoy - 2.0) / 4.0)
            - 0.45 * ((x.savings_rate - self.high_savings_threshold) / 15.0),
            -1.0,
            1.0,
        )

        component_scores = {
            "growth": round(growth_score, 4),
            "liquidity": round(liquidity_score, 4),
            "inflation": round(inflation_score, 4),
            "fx": round(fx_score, 4),
            "balance_sheet": round(balance_sheet_score, 4),
        }
        base_score = clamp(
            0.30 * growth_score
            + 0.25 * liquidity_score
            + 0.20 * inflation_score
            + 0.10 * fx_score
            + 0.15 * balance_sheet_score,
            -1.0,
            1.0,
        )

        non_typical_recovery = (
            x.credit_impulse > 0
            and x.ppi_yoy < 0
            and x.savings_rate > self.high_savings_threshold
        )
        overheating = x.cpi_yoy > 3.0 or x.ppi_yoy > 5.0
        fx_stress = x.usdcny_yoy > 4.0
        contraction = x.pmi < 49.0 and x.gdp_yoy < 4.5 and x.ppi_yoy < 0

        if non_typical_recovery:
            regime = "非典型复苏（流动性充裕但需求疲软）"
            confidence = clamp(0.40 + max(0.0, base_score) * 0.35, 0.30, 0.65)
            signal = "BUY" if base_score > 0.15 and not fx_stress else "HOLD"
            note = "信用/M2/LPR偏宽，但PPI通缩与高储蓄显示需求传导不足；偏结构市而非全面复苏。"
            downstream = {
                "valuation_module": {
                    "fcf_weight_multiplier": 1.35,
                    "earnings_growth_multiplier": 0.70,
                    "pe_pb_weight_multiplier": 0.90,
                },
                "risk_control": {
                    "max_growth_exposure": 0.45,
                    "cash_buffer_multiplier": 1.20,
                },
            }
        else:
            if contraction:
                regime = "衰退/通缩压力"
                signal = "SELL" if base_score <= -0.25 else "HOLD"
            elif overheating or fx_stress:
                regime = "过热/外汇压力"
                signal = "HOLD" if base_score > -0.20 else "SELL"
            elif base_score >= 0.30:
                regime = "复苏"
                signal = "BUY"
            elif base_score <= -0.30:
                regime = "衰退"
                signal = "SELL"
            else:
                regime = "过渡"
                signal = "HOLD"

            confidence = clamp(0.35 + abs(base_score) * 0.55, 0.35, 0.90)
            note = "宏观分数由增长、流动性、通胀、汇率与居民资产负债表五组指标加权生成。"
            downstream = {
                "valuation_module": {
                    "fcf_weight_multiplier": 1.00,
                    "earnings_growth_multiplier": 1.00,
                    "pe_pb_weight_multiplier": 1.00,
                },
                "risk_control": {
                    "max_growth_exposure": 0.60 if signal == "BUY" else 0.40,
                    "cash_buffer_multiplier": 1.00 if signal == "BUY" else 1.15,
                },
            }

        score = signal_to_score(signal, confidence)
        return MacroOutput(
            regime=regime,
            signal=signal,
            confidence=confidence,
            score=score,
            note=note,
            component_scores=component_scores,
            downstream_adjustments=downstream,
        )


# ========== 其余模块（简化可替换） ==========


def simple_module(name: str, weight: float, raw_score: float, note: str) -> ModuleSignal:
    s = clamp(raw_score, -1.0, 1.0)
    signal = score_to_signal(s)
    confidence = abs(s)
    return ModuleSignal(name=name, weight=weight, signal=signal, confidence=confidence, score=s, note=note)


# ========== 7模块引擎 ==========

class OpenClaw7M:
    MODULE_WEIGHTS = {
        "module1_rotation": 0.10,
        "module2_valuation": 0.10,
        "module3_technical": 0.20,
        "module4_density": 0.15,
        "module5_smart_trigger": 0.05,
        "module6_volume_price": 0.15,
        "module7_macro": 0.25,
    }

    def __init__(self) -> None:
        self.macro = MacroStrategy(high_savings_threshold=35.0)

    def evaluate(self, raw_inputs: Dict[str, float], macro_input: MacroInput) -> Dict:
        # 1) 先跑宏观模块，拿到下游约束
        macro_out = self.macro.analyze(macro_input)

        # 2) 应用宏观对估值模块的约束（演示）
        valuation_raw = raw_inputs.get("module2_valuation", 0.0)
        adj = macro_out.downstream_adjustments["valuation_module"]
        valuation_adjusted = valuation_raw * (
            0.5 * adj["fcf_weight_multiplier"] +
            0.3 * adj["earnings_growth_multiplier"] +
            0.2 * adj["pe_pb_weight_multiplier"]
        )
        valuation_adjusted = clamp(valuation_adjusted, -1.0, 1.0)

        modules: List[ModuleSignal] = [
            simple_module("模块1-轮动", self.MODULE_WEIGHTS["module1_rotation"], raw_inputs.get("module1_rotation", 0.0), "行业/风格轮动"),
            simple_module("模块2-估值", self.MODULE_WEIGHTS["module2_valuation"], valuation_adjusted, "估值+现金流（受宏观约束后）"),
            simple_module("模块3-技术", self.MODULE_WEIGHTS["module3_technical"], raw_inputs.get("module3_technical", 0.0), "MACD+RSI"),
            simple_module("模块4-密集区", self.MODULE_WEIGHTS["module4_density"], raw_inputs.get("module4_density", 0.0), "价格密集区"),
            simple_module("模块5-SmartTrigger", self.MODULE_WEIGHTS["module5_smart_trigger"], raw_inputs.get("module5_smart_trigger", 0.0), "关键点位触发"),
            simple_module("模块6-量价", self.MODULE_WEIGHTS["module6_volume_price"], raw_inputs.get("module6_volume_price", 0.0), "量价共振"),
            ModuleSignal(
                name="模块7-宏观",
                weight=self.MODULE_WEIGHTS["module7_macro"],
                signal=macro_out.signal,
                confidence=macro_out.confidence,
                score=macro_out.score,
                note=macro_out.note,
            ),
        ]

        weighted_score = sum(m.weight * m.score for m in modules)
        final_signal = score_to_signal(weighted_score)

        return {
            "final_signal": final_signal,
            "final_score": round(weighted_score, 4),
            "macro_regime": macro_out.regime,
            "modules": [m.__dict__ for m in modules],
            "macro_component_scores": macro_out.component_scores,
            "downstream_adjustments": macro_out.downstream_adjustments,
        }


def demo() -> None:
    # 你给出的“冲突型宏观数据”示例
    macro = MacroInput(
        credit_impulse=5.2,
        m2_yoy=8.5,
        savings_rate=45.0,
        cpi_yoy=0.8,
        ppi_yoy=-2.1,
        hh_credit_yoy=3.5,
        retail_sales_yoy=4.2,
        pmi=49.8,
        gdp_yoy=4.8,
        usdcny_yoy=2.6,
        lpr_1y=3.45,
    )

    # 其他6个模块原始分（-1~1，可替换为真实模型输出）
    raw = {
        "module1_rotation": 0.20,
        "module2_valuation": 0.35,
        "module3_technical": 0.10,
        "module4_density": 0.05,
        "module5_smart_trigger": 0.00,
        "module6_volume_price": 0.15,
    }

    engine = OpenClaw7M()
    result = engine.evaluate(raw, macro)

    print("=== OpenClaw 7模块结果 ===")
    print(f"Macro Regime : {result['macro_regime']}")
    print(f"Final Signal : {result['final_signal']}")
    print(f"Final Score  : {result['final_score']}")
    print("\n模块明细:")
    for m in result["modules"]:
        print(f"- {m['name']} | weight={m['weight']:.2f} | signal={m['signal']} | score={m['score']:.3f}")

    print("\n宏观分项:")
    print(result["macro_component_scores"])
    print("\n宏观下游约束:")
    print(result["downstream_adjustments"])


if __name__ == "__main__":
    demo()
