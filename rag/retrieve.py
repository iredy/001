"""Retriever with source loading, market filtering, and semantic-ready scoring."""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping


def _safe_read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _iter_source_records() -> Iterable[dict[str, Any]]:
    report_payload = _safe_read_json(Path("reports/report.json"))
    if isinstance(report_payload, list):
        for item in report_payload:
            if isinstance(item, dict):
                yield item
    elif isinstance(report_payload, dict):
        yield report_payload

    for path in sorted(Path(".").glob("csi300backtest*.json")):
        payload = _safe_read_json(path)
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    yield item
        elif isinstance(payload, dict):
            yield payload

    for path in sorted(Path("outputs/reports").glob("*.json")):
        payload = _safe_read_json(path)
        if isinstance(payload, dict):
            yield payload


def _market_tag(record: Mapping[str, Any]) -> str:
    for key in ("market", "index", "universe", "benchmark"):
        value = record.get(key)
        if value:
            return str(value).lower()
    return "unknown"


def _record_to_case(record: Mapping[str, Any], idx: int) -> dict[str, Any]:
    market_data = record.get("market_data", {}) if isinstance(record.get("market_data"), dict) else {}
    text_parts = [
        str(record.get("task_type", "")),
        str(record.get("summary", "")),
        str(record.get("conclusion", "")),
        str(record.get("signal_type", "")),
        " ".join(f"{k}:{v}" for k, v in market_data.items()),
    ]
    text = " ".join(p for p in text_parts if p).strip()
    return {
        "case_id": str(record.get("case_id") or f"auto_case_{idx}"),
        "market_phase": str(record.get("market_phase", "unknown")),
        "signal_type": str(record.get("signal_type", "unknown")),
        "input": text,
        "output": str(record.get("output") or record.get("parsed", "")),
        "result": str(record.get("result", "unknown")),
        "market": _market_tag(record),
        "_text": text,
    }


def _tokenize(text: str) -> list[str]:
    raw = text.lower()
    for s in ("，", ",", ";", "：", ":", "。", "\n", "\t"):
        raw = raw.replace(s, " ")
    return [tok for tok in raw.split() if tok]


def _bm25_scores(query_tokens: list[str], docs: list[list[str]]) -> list[float]:
    if not docs:
        return []
    k1, b = 1.5, 0.75
    n_docs = len(docs)
    avgdl = sum(len(d) for d in docs) / n_docs if n_docs else 1.0

    df = Counter()
    for doc in docs:
        for t in set(doc):
            df[t] += 1

    scores: list[float] = []
    for doc in docs:
        tf = Counter(doc)
        dl = len(doc) or 1
        score = 0.0
        for t in query_tokens:
            freq = tf[t]
            if freq == 0:
                continue
            idf = math.log(1 + (n_docs - df[t] + 0.5) / (df[t] + 0.5))
            denom = freq + k1 * (1 - b + b * dl / (avgdl or 1.0))
            score += idf * ((freq * (k1 + 1)) / denom)
        scores.append(score)
    return scores


def retrieve_similar_cases(market_data: Mapping[str, Any], top_k: int = 2) -> list[dict[str, Any]]:
    query = " ".join(f"{k}:{v}" for k, v in market_data.items())
    query_tokens = _tokenize(query)
    target_market = str(market_data.get("market", "unknown")).lower()

    records = list(_iter_source_records())
    if not records:
        return []

    cases = [_record_to_case(record, idx) for idx, record in enumerate(records, start=1)]

    if target_market != "unknown":
        filtered = [c for c in cases if c.get("market") == target_market]
        if filtered:
            cases = filtered

    docs = [_tokenize(case.get("_text", "")) for case in cases]
    bm25 = _bm25_scores(query_tokens, docs)

    scored: list[tuple[float, dict[str, Any]]] = []
    for case, score in zip(cases, bm25):
        final_score = score
        if case.get("market_phase") != "unknown":
            final_score += 0.2
        if case.get("signal_type") != "unknown":
            final_score += 0.15
        scored.append((final_score, case))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [item for _, item in scored[:top_k]]
    for item in top:
        item.pop("_text", None)
    return top
