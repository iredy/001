import json
from pathlib import Path

from rag.retrieve import retrieve_similar_cases


def test_retrieve_uses_data_root_not_cwd(tmp_path: Path, monkeypatch):
    repo_like = tmp_path / "repo"
    (repo_like / "outputs/reports").mkdir(parents=True)
    (repo_like / "outputs/reports/case.json").write_text(
        json.dumps({"case_id": "r1", "market": "kcb200", "summary": "科技", "signal_type": "breakout"}, ensure_ascii=False),
        encoding="utf-8",
    )

    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)

    result = retrieve_similar_cases({"market": "kcb200", "theme": "科技"}, top_k=1, data_root=repo_like)
    assert result
    assert result[0]["case_id"] == "r1"
