import json
from pathlib import Path

from strategy.runner import run_strategy


def test_run_strategy_writes_report_and_review(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def fake_retrieve(_market_data, top_k=2):
        return [{"case_id": "c1", "market_phase": "震荡", "signal_type": "spring", "input": "i", "output": "o", "result": "r"}][:top_k]

    def fake_llm(_prompt: str, max_tokens: int = 300) -> str:
        return "1) 结论：测试\n2) 盘面结构：测试\n3) 资金行为：测试\n4) 风险：测试\n5) 动作建议：测试"

    result = run_strategy("premarket_scan", {"market": "kcb200", "cn10y_yield_chg_bps": -11, "stock_return_pct": 3.2, "kcb50_return_pct": 1.1}, rag_retrieve=fake_retrieve, llm_call=fake_llm)

    report_dir = Path("outputs/reports")
    files = list(report_dir.glob("*.json"))
    assert files

    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["task_type"] == "premarket_scan"
    assert "macro_weight" in payload["market_data"]
    assert "macro_weight_reason" in payload["market_data"]
    assert payload["market_data"]["relative_strength_phase"] == "outperform"
    assert result.run_id == payload["run_id"]

    review_file = Path("knowledge/cases_json/review_samples.jsonl")
    assert review_file.exists()
