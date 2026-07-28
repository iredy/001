"""Utilities for token-aware model routing and cached data access."""

from .context_budget import LoadedContext, MemoryIndex, MemorySlice, estimate_tokens
from .data_source import FetchConfig, MemoryCache, fetch_with_cache
from .pr_diff_cache import DiffFileSummary, DiffSummary, PRDiffSummaryCache, summarize_unified_diff
from .model_router import (
    CircuitBreaker,
    ModelRequest,
    ModelResponse,
    ProviderConfig,
    ProviderExecutor,
    ShadowRouteObservation,
    RouteDecision,
    TaskMeta,
    observe_shadow_route,
    route,
)

__all__ = [
    "CircuitBreaker",
    "DiffFileSummary",
    "DiffSummary",
    "FetchConfig",
    "LoadedContext",
    "MemoryCache",
    "MemoryIndex",
    "MemorySlice",
    "ModelRequest",
    "ModelResponse",
    "PRDiffSummaryCache",
    "ProviderConfig",
    "ProviderExecutor",
    "ShadowRouteObservation",
    "RouteDecision",
    "TaskMeta",
    "estimate_tokens",
    "fetch_with_cache",
    "observe_shadow_route",
    "route",
    "summarize_unified_diff",
]
