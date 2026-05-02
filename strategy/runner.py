"""Unified strategy runner: retrieval -> prompt -> model -> persistence -> review."""

from __future__ import annotations

import importlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from rag.prompt_builder import build_prompt
from rag.retrieve import retrieve_similar_cases
from strategy.macro_adjust import adjust_macro_weight


DEFAULT_OUTPUT_DIR = Path("outputs/reports")
DEFAULT_LOG_DIR = Path("outputs/logs")


@dataclass(slots=True)
class StrategyRunResult:
    task_type: str
    run_id: str
    model_output: str
    parsed_output: dict[str, Any]
    examples_used: list[dict[str, Any]]


def _fallback_output() -> str:
    return (
        "1) 结论：今日偏防守，等待确认信号。\n"
        "2) 盘面结构：指数震荡，主线分化，跟风退潮。\n"
        "3) 资金行为：高低切明显，增量资金不足。\n"
        "4) 风险：关键位失守风险，追高回撤风险。\n"
        "5) 动作建议：轻仓观察，事件触发再加仓。"
    )


def default_llm_call(prompt: str, max_tokens: int = 300) -> str:
    """Use real OpenAI client when configured, otherwise fallback to deterministic stub."""
    api_key = os.getenv("OPENAI_API_KEY")
    model_name = os.getenv("RAG_LLM_MODEL", "gpt-4o-mini")
    if not api_key:
        return _fallback_output()

    module = importlib.import_module("openai")
    client = module.OpenAI(api_key=api_key)
    response = client.responses.create(
        model=model_name,
        input=prompt,
        max_output_tokens=max_tokens,
    )
    return response.output_text or _fallback_output()


def parse_result(model_output: str) -> dict[str, Any]:
    sections: dict[str, str] = {}
    for raw_line in model_output.splitlines():
        line = raw_line.strip()
        if not line or "：" not in line:
            continue
        prefix, body = line.split("：", 1)
        sections[prefix.strip()] = body.strip()
    return {"sections": sections, "raw": model_output}


def save_report(
    task_type: str,
    market_data: Mapping[str, Any],
    prompt: str,
    examples: list[dict[str, Any]],
    parsed: dict[str, Any],
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "run_id": run_id,
        "task_type": task_type,
        "market_data": dict(market_data),
        "prompt": prompt,
        "examples": examples,
        "parsed": parsed,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    path = output_dir / f"{run_id}_{task_type}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return run_id


def update_review_sample(
    run_result: StrategyRunResult,
    review_file: Path = Path("knowledge/cases_json/review_samples.jsonl"),
) -> None:
    review_file.parent.mkdir(parents=True, exist_ok=True)
    with review_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(run_result), ensure_ascii=False) + "\n")




def _enrich_market_data(market_data: Mapping[str, Any]) -> dict[str, Any]:
    enriched = dict(market_data)
    baseline_macro = float(enriched.get("macro_weight", 0.25))
    decision = adjust_macro_weight(baseline_macro, enriched)
    enriched["macro_weight"] = round(decision.adjusted_weight, 4)
    enriched["macro_weight_baseline"] = round(decision.baseline_weight, 4)
    enriched["macro_weight_reason"] = decision.adjustment_reason
    return enriched
def run_strategy(
    task_type: str,
    market_data: Mapping[str, Any],
    *,
    rag_retrieve: Callable[[Mapping[str, Any], int], list[dict[str, Any]]] = retrieve_similar_cases,
    llm_call: Callable[[str, int], str] = default_llm_call,
    max_tokens: int = 300,
) -> StrategyRunResult:
    enriched_market_data = _enrich_market_data(market_data)
    examples = rag_retrieve(enriched_market_data, top_k=2)
    prompt = build_prompt(task_type, enriched_market_data, examples)
    model_output = llm_call(prompt, max_tokens=max_tokens)
    parsed = parse_result(model_output)
    run_id = save_report(task_type, enriched_market_data, prompt, examples, parsed)

    run_result = StrategyRunResult(
        task_type=task_type,
        run_id=run_id,
        model_output=model_output,
        parsed_output=parsed,
        examples_used=examples,
    )
    update_review_sample(run_result)
    return run_result


def log_runner_event(message: str, log_dir: Path = DEFAULT_LOG_DIR) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    with (log_dir / "runner.log").open("a", encoding="utf-8") as f:
        f.write(f"{timestamp} | {message}\n")
