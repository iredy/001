import json
from pathlib import Path

from rag.retrieve import retrieve_similar_cases


def test_retrieve_prefers_same_market(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    reports = tmp_path / "outputs" / "reports"
    reports.mkdir(parents=True)

    data = {
        "case_id": "a",
        "market": "kcb200",
        "market_phase": "强",
        "signal_type": "breakout",
        "summary": "科技强势",
    }
    (reports / "a.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    data2 = {
        "case_id": "b",
        "market": "csi300",
        "market_phase": "弱",
        "signal_type": "value",
        "summary": "银行防守",
    }
    (reports / "b.json").write_text(json.dumps(data2, ensure_ascii=False), encoding="utf-8")

    result = retrieve_similar_cases({"market": "kcb200", "theme": "科技"}, top_k=1)
    assert result
    assert result[0]["case_id"] == "a"


def test_retrieve_returns_empty_when_no_sources(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = retrieve_similar_cases({"market": "kcb200"}, top_k=2)
    assert result == []
