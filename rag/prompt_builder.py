"""Utilities for building deterministic few-shot prompts for strategy tasks."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

STYLE_REQUIREMENTS = [
    "1. 先给结论",
    "2. 再给盘面结构",
    "3. 再给资金行为",
    "4. 再给风险",
    "5. 最后给动作建议",
    "6. 不允许空话",
    "7. 不允许过度展开",
    "8. 必须像交易员复盘，不像研究论文",
]


def _render_mapping(title: str, data: Mapping[str, Any]) -> str:
    lines = [f"## {title}"]
    for key, value in data.items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def _render_examples(examples: Iterable[Mapping[str, Any]]) -> str:
    rendered_examples: list[str] = ["## 历史相似案例（Few-shot）"]
    for index, example in enumerate(examples, start=1):
        rendered_examples.append(f"### 案例 {index}")
        rendered_examples.append(f"- case_id: {example.get('case_id', f'case_{index}')}")
        rendered_examples.append(f"- market_phase: {example.get('market_phase', 'unknown')}")
        rendered_examples.append(f"- signal_type: {example.get('signal_type', 'unknown')}")
        rendered_examples.append(f"- input: {example.get('input', '')}")
        rendered_examples.append(f"- output: {example.get('output', '')}")
        rendered_examples.append(f"- result: {example.get('result', 'unknown')}")
    if len(rendered_examples) == 1:
        rendered_examples.append("- 无可用历史案例，使用通用纪律进行判断")
    return "\n".join(rendered_examples)


def build_prompt(
    task_type: str,
    market_data: Mapping[str, Any],
    examples: Iterable[Mapping[str, Any]],
) -> str:
    """Build a stable strategy prompt with explicit style constraints."""
    style_block = "\n".join(f"- {rule}" for rule in STYLE_REQUIREMENTS)

    sections = [
        "你是盘中策略执行引擎。请严格遵守输出结构与风格约束。",
        f"## 任务类型\n- {task_type}",
        _render_mapping("当前市场快照", market_data),
        _render_examples(examples),
        "## 输出风格约束\n" + style_block,
        (
            "## 输出格式（必须严格按顺序）\n"
            "1) 结论\n"
            "2) 盘面结构\n"
            "3) 资金行为\n"
            "4) 风险\n"
            "5) 动作建议\n"
            "\n"
            "每个部分限制 1-3 条要点，总长度控制在 300 token 左右。"
        ),
    ]
    return "\n\n".join(sections)
