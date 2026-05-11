#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""将 tradejournal.db 灌入 StrategyRAGIndexer 的首选脚本。

默认假设 trade_journal 表结构：
- id INTEGER
- trade_date TEXT
- symbol TEXT
- strategy TEXT
- thesis TEXT
- post_mortem TEXT

如果你的字段不同，改 SQL 即可。
"""

from __future__ import annotations

import argparse
import sqlite3
from tools.strategyragindexer import StrategyRAGIndexer


def ingest_tradejournal(source_db: str, rag_db: str, limit: int = 5000) -> int:
    src = sqlite3.connect(source_db)
    rag = StrategyRAGIndexer(db_path=rag_db)

    rows = src.execute(
        """
        SELECT id, trade_date, symbol, strategy, thesis, post_mortem
        FROM trade_journal
        ORDER BY trade_date DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    docs = []
    for rid, d, sym, st, thesis, pm in rows:
        docs.append(
            {
                "source": "tradejournal",
                "title": f"{d} {sym} {st}",
                "content": f"thesis: {thesis or ''}\npost_mortem: {pm or ''}",
                "metadata_json": f'{{"journal_id": "{rid}", "symbol": "{sym}"}}',
            }
        )

    return rag.upsert_documents(docs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-db", default="tradejournal.db")
    parser.add_argument("--rag-db", default="strategy_rag.sqlite3")
    parser.add_argument("--limit", type=int, default=5000)
    args = parser.parse_args()

    n = ingest_tradejournal(args.source_db, args.rag_db, args.limit)
    print(f"[OK] indexed {n} trade-journal docs into {args.rag_db}")


if __name__ == "__main__":
    main()
