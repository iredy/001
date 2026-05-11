#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence


@dataclass
class RetrievedDoc:
    doc_id: int
    source: str
    title: str
    content: str
    score: float
    metadata: Dict[str, str]


class StrategyRAGIndexer:
    """轻量 RAG 索引器：
    - 使用 SQLite 保存文档
    - 使用 BM25-like 的词频匹配（纯本地，无外部依赖）
    """

    def __init__(self, db_path: str = "strategy_rag.sqlite3"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        self.con.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts
            USING fts5(title, content, content='documents', content_rowid='id');

            CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
                INSERT INTO documents_fts(rowid, title, content)
                VALUES (new.id, new.title, new.content);
            END;
            CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, title, content)
                VALUES ('delete', old.id, old.title, old.content);
            END;
            CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, title, content)
                VALUES ('delete', old.id, old.title, old.content);
                INSERT INTO documents_fts(rowid, title, content)
                VALUES (new.id, new.title, new.content);
            END;
            """
        )
        self.con.commit()

    def upsert_documents(self, docs: Sequence[Dict[str, str]]) -> int:
        n = 0
        for d in docs:
            self.con.execute(
                "INSERT INTO documents(source, title, content, metadata_json) VALUES (?, ?, ?, ?)",
                (
                    d.get("source", "unknown"),
                    d.get("title", "untitled"),
                    d.get("content", ""),
                    d.get("metadata_json", "{}"),
                ),
            )
            n += 1
        self.con.commit()
        return n

    def search(self, query: str, top_k: int = 3) -> List[RetrievedDoc]:
        q = self._normalize_query(query)
        rows = self.con.execute(
            """
            SELECT d.id, d.source, d.title, d.content, d.metadata_json,
                   bm25(documents_fts) AS bm
            FROM documents_fts
            JOIN documents d ON d.id = documents_fts.rowid
            WHERE documents_fts MATCH ?
            ORDER BY bm ASC
            LIMIT ?
            """,
            (q, top_k),
        ).fetchall()

        out: List[RetrievedDoc] = []
        for r in rows:
            out.append(
                RetrievedDoc(
                    doc_id=r[0],
                    source=r[1],
                    title=r[2],
                    content=r[3],
                    score=float(-r[5]),
                    metadata={"raw": r[4]},
                )
            )
        return out

    @staticmethod
    def _normalize_query(query: str) -> str:
        parts = re.findall(r"[\w\u4e00-\u9fff]+", query)
        return " ".join(parts) if parts else query
