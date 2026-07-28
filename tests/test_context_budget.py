import json

from strategy.context_budget import MemoryIndex, estimate_tokens


def test_memory_index_loads_hot_and_keyword_matched_warm_slice(tmp_path):
    (tmp_path / "hot").mkdir()
    (tmp_path / "warm").mkdir()
    (tmp_path / "cold").mkdir()
    (tmp_path / "hot" / "recent.md").write_text("recent operational facts", encoding="utf-8")
    (tmp_path / "warm" / "stocks.md").write_text("stock routing summary", encoding="utf-8")
    (tmp_path / "cold" / "archive.md").write_text("old unrelated archive", encoding="utf-8")
    (tmp_path / "index.json").write_text(
        json.dumps(
            {
                "slices": [
                    {"path": "hot/recent.md", "tier": "hot", "keywords": ["recent"], "estimated_tokens": 3},
                    {"path": "warm/stocks.md", "tier": "warm", "keywords": ["stock"], "estimated_tokens": 3},
                    {"path": "cold/archive.md", "tier": "cold", "keywords": ["legacy"], "estimated_tokens": 3},
                ]
            }
        ),
        encoding="utf-8",
    )

    context = MemoryIndex(tmp_path).load_context("stock analysis", max_tokens=6)

    assert context.loaded_paths == ("hot/recent.md", "warm/stocks.md")
    assert "old unrelated archive" not in context.text


def test_memory_index_respects_max_token_budget(tmp_path):
    (tmp_path / "hot").mkdir()
    (tmp_path / "hot" / "large.md").write_text("too much context", encoding="utf-8")
    (tmp_path / "index.json").write_text(
        json.dumps({"slices": [{"path": "hot/large.md", "tier": "hot", "estimated_tokens": 99}]}),
        encoding="utf-8",
    )

    context = MemoryIndex(tmp_path).load_context("anything", max_tokens=1)

    assert context.loaded_paths == ()
    assert context.skipped_paths == ("hot/large.md",)


def test_estimate_tokens_is_deterministic():
    assert estimate_tokens("hello, world!") == estimate_tokens("hello, world!")
