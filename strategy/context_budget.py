"""Context slicing helpers for reducing prompt input tokens.

The loader follows the hot/warm/cold memory layout described in the rollout
plan. It loads recent hot memory by default, then selectively loads warm/cold
slices by keyword until the caller's token budget is exhausted.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


@dataclass(frozen=True)
class MemorySlice:
    path: str
    tier: str
    summary: str = ""
    keywords: tuple[str, ...] = ()
    estimated_tokens: int = 0


@dataclass(frozen=True)
class LoadedContext:
    text: str
    loaded_paths: tuple[str, ...]
    estimated_tokens: int
    skipped_paths: tuple[str, ...]


def estimate_tokens(text: str) -> int:
    """Return a deterministic token estimate without calling a tokenizer."""

    if not text:
        return 0
    return max(1, len(_TOKEN_RE.findall(text)))


class MemoryIndex:
    """Read and select memory slices from a hot/warm/cold index file."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.index_path = self.root / "index.json"

    def load_slices(self) -> tuple[MemorySlice, ...]:
        if not self.index_path.exists():
            return ()
        data = json.loads(self.index_path.read_text(encoding="utf-8"))
        slices: list[MemorySlice] = []
        for item in data.get("slices", []):
            keywords = tuple(str(keyword).lower() for keyword in item.get("keywords", []))
            slices.append(
                MemorySlice(
                    path=str(item["path"]),
                    tier=str(item.get("tier", "cold")),
                    summary=str(item.get("summary", "")),
                    keywords=keywords,
                    estimated_tokens=int(item.get("estimated_tokens", 0)),
                )
            )
        return tuple(slices)

    def load_context(self, query: str, *, max_tokens: int, include_hot: bool = True) -> LoadedContext:
        query_terms = {term.lower() for term in _TOKEN_RE.findall(query) if term.strip()}
        selected: list[MemorySlice] = []
        skipped: list[str] = []

        for item in self.load_slices():
            should_load = include_hot and item.tier == "hot"
            should_load = should_load or bool(query_terms.intersection(item.keywords))
            if should_load:
                selected.append(item)
            else:
                skipped.append(item.path)

        chunks: list[str] = []
        loaded_paths: list[str] = []
        used_tokens = 0
        for item in sorted(selected, key=_slice_priority):
            path = self.root / item.path
            if not path.exists():
                skipped.append(item.path)
                continue
            text = path.read_text(encoding="utf-8")
            token_count = item.estimated_tokens or estimate_tokens(text)
            if used_tokens + token_count > max_tokens:
                skipped.append(item.path)
                continue
            chunks.append(text)
            loaded_paths.append(item.path)
            used_tokens += token_count

        return LoadedContext(
            text="\n\n".join(chunks),
            loaded_paths=tuple(loaded_paths),
            estimated_tokens=used_tokens,
            skipped_paths=tuple(skipped),
        )


def _slice_priority(item: MemorySlice) -> tuple[int, str]:
    tier_order = {"hot": 0, "warm": 1, "cold": 2}
    return (tier_order.get(item.tier, 3), item.path)
