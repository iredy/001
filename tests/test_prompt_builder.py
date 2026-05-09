from rag.prompt_builder import build_prompt


def test_build_prompt_contains_required_sections():
    prompt = build_prompt(
        "premarket_scan",
        {"market": "kcb200", "trend": "up"},
        [
            {
                "case_id": "c1",
                "market_phase": "震荡",
                "signal_type": "spring",
                "input": "x",
                "output": "y",
                "result": "z",
            }
        ],
    )

    assert "## 任务类型" in prompt
    assert "## 当前市场快照" in prompt
    assert "## 历史相似案例（Few-shot）" in prompt
    assert "## 输出风格约束" in prompt
    assert "1) 结论" in prompt
    assert "5) 动作建议" in prompt
