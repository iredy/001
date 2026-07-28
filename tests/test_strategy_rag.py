from pathlib import Path

from strategy_rag import KeywordRetriever, analyze, load_chunks


def test_load_chunks_reads_sector_sections() -> None:
    chunks = load_chunks(Path("data/strategy_notes/20260605_rag_strategy.md"))

    assert [chunk.title for chunk in chunks] == ["高位科技", "低位消费", "组合建议"]


def test_retriever_finds_consumption_context() -> None:
    chunks = load_chunks(Path("data/strategy_notes/20260605_rag_strategy.md"))
    hits = KeywordRetriever(chunks).search("低位消费 配置")

    assert hits
    assert hits[0].chunk.title == "低位消费"


def test_analyze_outputs_both_sector_playbooks() -> None:
    output = analyze("高位科技和低位消费怎么配置", Path("data/strategy_notes/20260605_rag_strategy.md"))

    assert "高位科技" in output
    assert "低位消费" in output
    assert "股票池" in output
