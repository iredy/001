"""Lightweight strategy RAG retrieval and sector analysis.

The module is intentionally dependency-free so it can run in research notebooks,
cron jobs, or CI before a production vector database / LLM is connected.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

SECTOR_STOCKS = {
    "high_tech": {
        "label": "高位科技",
        "stocks": ["中际旭创", "新易盛", "工业富联", "寒武纪", "北方华创", "中微公司"],
        "risk": "估值、交易拥挤度和业绩兑现压力较高，避免在放量加速后追涨。",
        "action": "以龙头留仓和回撤再配置为主，弱化纯主题弹性标的。",
        "keywords": ["科技", "高位", "AI", "算力", "半导体", "光模块", "机器人"],
    },
    "low_consumption": {
        "label": "低位消费",
        "stocks": ["贵州茅台", "五粮液", "美的集团", "海尔智家", "伊利股份", "珀莱雅"],
        "risk": "需求修复可能偏慢，需跟踪收入预期、库存和促消费政策落地。",
        "action": "用分批配置承接估值修复，优先现金流、分红和品牌壁垒。",
        "keywords": ["消费", "低位", "白酒", "食品", "家电", "医美", "零售"],
    },
}


@dataclass(frozen=True)
class Chunk:
    """A retrievable strategy text chunk."""

    title: str
    text: str


@dataclass(frozen=True)
class SearchHit:
    """A retrieved chunk and its score."""

    chunk: Chunk
    score: int


def tokenize(text: str) -> list[str]:
    """Tokenize Chinese/English strategy text into searchable terms."""

    return re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]{2,}", text.lower())


def load_chunks(path: Path) -> list[Chunk]:
    """Load a markdown strategy note and split it into heading-aware chunks."""

    content = path.read_text(encoding="utf-8")
    chunks: list[Chunk] = []
    current_title = path.stem
    current_lines: list[str] = []

    for line in content.splitlines():
        if line.startswith("## "):
            if current_lines:
                chunks.append(Chunk(current_title, "\n".join(current_lines).strip()))
            current_title = line.removeprefix("## ").strip()
            current_lines = []
        elif line.strip() and not line.startswith("# "):
            current_lines.append(line.strip())

    if current_lines:
        chunks.append(Chunk(current_title, "\n".join(current_lines).strip()))

    return chunks


class KeywordRetriever:
    """Simple keyword retriever that can be replaced by vector search later."""

    def __init__(self, chunks: Iterable[Chunk]) -> None:
        self.chunks = list(chunks)

    def search(self, query: str, top_k: int = 4) -> list[SearchHit]:
        query_terms = set(tokenize(query))
        hits: list[SearchHit] = []
        for chunk in self.chunks:
            haystack = f"{chunk.title} {chunk.text}".lower()
            chunk_terms = tokenize(haystack)
            score = sum(1 for term in chunk_terms if term in query_terms)
            # Chinese strategy queries often contain concatenated phrases such as
            # “高位科技和低位消费”. Add substring matches so sector titles and
            # configured domain keywords are still recalled without a segmenter.
            if chunk.title and chunk.title in query:
                score += 3
            for sector in SECTOR_STOCKS.values():
                score += sum(1 for keyword in sector["keywords"] if keyword.lower() in query.lower() and keyword.lower() in haystack)
            if score:
                hits.append(SearchHit(chunk=chunk, score=score))
        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:top_k]


def render_analysis(query: str, hits: list[SearchHit]) -> str:
    """Render retrieved context plus high-tech / low-consumption actions."""

    lines = [f"# RAG 策略分析", "", f"查询：{query}", "", "## 检索片段"]
    if not hits:
        lines.append("- 未检索到相关策略片段，请补充策略文件或扩大检索范围。")
    for hit in hits:
        lines.append(f"- {hit.chunk.title}（score={hit.score}）：{hit.chunk.text}")

    lines.extend(["", "## 板块落地"])
    for sector in SECTOR_STOCKS.values():
        lines.extend(
            [
                f"### {sector['label']}",
                f"- 股票池：{', '.join(sector['stocks'])}",
                f"- 风险判断：{sector['risk']}",
                f"- 操作建议：{sector['action']}",
            ]
        )
    return "\n".join(lines)


def analyze(query: str, corpus: Path, top_k: int = 4) -> str:
    """Run the end-to-end local RAG analysis."""

    retriever = KeywordRetriever(load_chunks(corpus))
    return render_analysis(query, retriever.search(query, top_k=top_k))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local strategy RAG analysis.")
    parser.add_argument("--query", required=True, help="Strategy question to retrieve and analyze.")
    parser.add_argument("--corpus", type=Path, required=True, help="Markdown strategy note path.")
    parser.add_argument("--top-k", type=int, default=4, help="Number of chunks to retrieve.")
    args = parser.parse_args()
    print(analyze(args.query, args.corpus, top_k=args.top_k))


if __name__ == "__main__":
    main()
