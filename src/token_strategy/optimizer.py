"""Token optimization primitives for RAG-heavy LLM applications.

The module is intentionally dependency-free so it can be embedded in services
such as OpenClaw without adding another model-serving dependency.  It focuses on
four practical controls:

1. strict RAG top-k retrieval;
2. per-section token budgets;
3. conversation-history compaction;
4. cost estimation before a commercial model call is made.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from collections import Counter
from typing import Sequence

_WORD_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


@dataclass(frozen=True)
class Document:
    """A retrievable knowledge item."""

    id: str
    text: str
    metadata: dict[str, str] | None = None


@dataclass(frozen=True)
class Message:
    """A single chat message."""

    role: str
    content: str


@dataclass(frozen=True)
class TokenBudget:
    """Budget settings for a single LLM request."""

    max_input_tokens: int = 5_000
    reserved_output_tokens: int = 1_000
    max_system_tokens: int = 800
    max_history_tokens: int = 1_200
    max_rag_tokens: int = 2_400
    max_user_tokens: int = 600
    rag_top_k: int = 3
    input_price_per_million: float = 15.38
    output_price_per_million: float = 0.0


@dataclass(frozen=True)
class BudgetDecision:
    """The optimized request plus telemetry suitable for logs/metrics."""

    system_prompt: str
    messages: list[Message]
    rag_context: list[Document]
    estimated_input_tokens: int
    estimated_max_cost_usd: float
    dropped_history_messages: int
    dropped_rag_documents: int


def estimate_tokens(text: str) -> int:
    """Estimate token count for mixed English/Chinese text.

    This is a conservative heuristic, not a tokenizer replacement.  Chinese
    characters are counted close to one token each, while non-CJK text uses the
    common four-characters-per-token approximation.
    """

    if not text:
        return 0
    cjk_chars = len(_CJK_RE.findall(text))
    non_cjk_chars = len(_CJK_RE.sub("", text))
    return math.ceil(cjk_chars + non_cjk_chars / 4)


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    if estimate_tokens(text) <= max_tokens:
        return text

    # Binary search keeps the function fast even for large strategy documents.
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if estimate_tokens(text[:mid]) <= max_tokens:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + "…"


def _terms(text: str) -> Counter[str]:
    return Counter(token.lower() for token in _WORD_RE.findall(text))


def _cosine_similarity(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    common = set(left) & set(right)
    dot = sum(left[token] * right[token] for token in common)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


class TokenOptimizer:
    """Build lower-cost LLM requests from raw prompts, history, and RAG docs."""

    def __init__(self, budget: TokenBudget | None = None) -> None:
        self.budget = budget or TokenBudget()

    def select_rag_context(self, query: str, documents: Sequence[Document]) -> list[Document]:
        """Return the most relevant documents within the RAG token budget."""

        query_terms = _terms(query)
        ranked = sorted(
            documents,
            key=lambda doc: (_cosine_similarity(query_terms, _terms(doc.text)), doc.id),
            reverse=True,
        )

        selected: list[Document] = []
        used_tokens = 0
        per_doc_limit = max(1, self.budget.max_rag_tokens // max(1, self.budget.rag_top_k))

        for doc in ranked:
            if len(selected) >= self.budget.rag_top_k:
                break
            remaining = self.budget.max_rag_tokens - used_tokens
            if remaining <= 0:
                break

            text = _truncate_to_tokens(doc.text, min(per_doc_limit, remaining))
            selected.append(Document(id=doc.id, text=text, metadata=doc.metadata))
            used_tokens += estimate_tokens(text)

        return selected

    def compact_history(self, history: Sequence[Message]) -> tuple[list[Message], int]:
        """Keep the newest messages that fit the history budget."""

        kept_reversed: list[Message] = []
        used_tokens = 0
        for message in reversed(history):
            message_tokens = estimate_tokens(message.content)
            if used_tokens + message_tokens > self.budget.max_history_tokens:
                continue
            kept_reversed.append(message)
            used_tokens += message_tokens

        kept = list(reversed(kept_reversed))
        return kept, len(history) - len(kept)

    def build_request(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        history: Sequence[Message] | None = None,
        documents: Sequence[Document] | None = None,
    ) -> BudgetDecision:
        """Create an optimized request and fail fast if it exceeds the budget."""

        history = history or []
        documents = documents or []

        optimized_system = _truncate_to_tokens(system_prompt, self.budget.max_system_tokens)
        optimized_user = _truncate_to_tokens(user_prompt, self.budget.max_user_tokens)
        optimized_history, dropped_history = self.compact_history(history)
        optimized_rag = self.select_rag_context(user_prompt, documents)

        messages = [*optimized_history, Message(role="user", content=optimized_user)]
        request_text = "\n".join(
            [optimized_system, optimized_user]
            + [message.content for message in optimized_history]
            + [doc.text for doc in optimized_rag]
        )
        estimated_input = estimate_tokens(request_text)

        if estimated_input > self.budget.max_input_tokens:
            overflow = estimated_input - self.budget.max_input_tokens
            raise ValueError(
                f"optimized request is still {overflow} tokens over budget; "
                "reduce section budgets or summarize source documents first"
            )

        estimated_cost = (
            estimated_input * self.budget.input_price_per_million
            + self.budget.reserved_output_tokens * self.budget.output_price_per_million
        ) / 1_000_000

        return BudgetDecision(
            system_prompt=optimized_system,
            messages=messages,
            rag_context=optimized_rag,
            estimated_input_tokens=estimated_input,
            estimated_max_cost_usd=round(estimated_cost, 6),
            dropped_history_messages=dropped_history,
            dropped_rag_documents=max(0, len(documents) - len(optimized_rag)),
        )
