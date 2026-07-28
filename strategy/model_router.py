"""Safe multi-model routing primitives.

The module intentionally keeps routing decisions separate from provider execution.
Each provider receives its own executor instance so API keys, base URLs, retry
budgets and concurrency controls cannot bleed across models.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

CRITICAL_TASK_TYPE = "critical_decisions"
PRIMARY_PROVIDER = "ctyun_primary"

DEFAULT_ROUTE_TABLE: Mapping[str, tuple[str, ...]] = {
    "simple_tasks": ("qwen_7b", "qwen_14b", PRIMARY_PROVIDER),
    "daily_tasks": ("qwen_14b", "deepseek_v3", PRIMARY_PROVIDER),
    "complex_analysis": ("deepseek_v3", PRIMARY_PROVIDER),
    CRITICAL_TASK_TYPE: (PRIMARY_PROVIDER,),
}


@dataclass(frozen=True)
class TaskMeta:
    """Metadata used to choose a model without loading full task context."""

    task_type: str
    risk_level: str = "normal"
    estimated_input_tokens: int = 0


@dataclass(frozen=True)
class RouteDecision:
    """A deterministic model routing result."""

    provider: str
    reason: str


@dataclass(frozen=True)
class ProviderConfig:
    """Immutable provider configuration for an isolated executor."""

    name: str
    base_url: str
    api_key_env: str
    model: str
    timeout_seconds: float = 30.0
    max_concurrency: int = 2
    failure_threshold: int = 5
    cooldown_seconds: int = 60


@dataclass(frozen=True)
class ModelRequest:
    """Provider-independent request payload."""

    messages: Sequence[Mapping[str, str]]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelResponse:
    """Normalized provider-independent response payload."""

    content: str
    provider: str
    model: str
    raw: Any | None = None


class ProviderUnavailable(RuntimeError):
    """Raised when a provider is temporarily blocked by its circuit breaker."""


class CircuitBreaker:
    """Small circuit breaker for provider-level failure isolation."""

    def __init__(self, failure_threshold: int = 5, cooldown_seconds: int = 60) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must be >= 0")
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def failures(self) -> int:
        return self._failures

    def allow_request(self, now: float | None = None) -> bool:
        if self._opened_at is None:
            return True
        current_time = time.monotonic() if now is None else now
        if current_time - self._opened_at >= self.cooldown_seconds:
            self._opened_at = None
            self._failures = 0
            return True
        return False

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self, exc: BaseException | None = None, now: float | None = None) -> None:
        del exc
        self._failures += 1
        if self._failures >= self.failure_threshold and self._opened_at is None:
            self._opened_at = time.monotonic() if now is None else now


HealthState = Mapping[str, bool]
TokenBudget = Mapping[str, int]
ProviderCall = Callable[[ProviderConfig, ModelRequest], Awaitable[ModelResponse]]


def route(
    task: TaskMeta,
    health: HealthState,
    *,
    route_table: Mapping[str, Sequence[str]] = DEFAULT_ROUTE_TABLE,
    token_budget: TokenBudget | None = None,
    router_enabled: bool = True,
    primary_provider: str = PRIMARY_PROVIDER,
) -> RouteDecision:
    """Choose a provider without mutating clients or loading large context.

    Critical tasks and disabled routers always return the primary Tianyi Cloud
    provider. Other tasks scan their candidate list and pick the first healthy
    provider that can fit the estimated context budget.
    """

    if not router_enabled:
        return RouteDecision(primary_provider, "router_disabled")
    if task.risk_level == "critical" or task.task_type == CRITICAL_TASK_TYPE:
        return RouteDecision(primary_provider, "critical_task")

    candidates = route_table.get(task.task_type, (primary_provider,))
    for candidate in candidates:
        if not health.get(candidate, False):
            continue
        if token_budget is not None and task.estimated_input_tokens > token_budget.get(candidate, 0):
            continue
        return RouteDecision(candidate, "matched_task_type")

    return RouteDecision(primary_provider, "fallback_no_candidate")


class ProviderExecutor:
    """Execute calls through a provider-local semaphore and circuit breaker."""

    def __init__(self, config: ProviderConfig, call_provider: ProviderCall) -> None:
        if config.max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        self.config = config
        self._call_provider = call_provider
        self._semaphore = asyncio.Semaphore(config.max_concurrency)
        self.breaker = CircuitBreaker(config.failure_threshold, config.cooldown_seconds)

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if not self.breaker.allow_request():
            raise ProviderUnavailable(self.config.name)

        async with self._semaphore:
            try:
                response = await asyncio.wait_for(
                    self._call_provider(self.config, request),
                    timeout=self.config.timeout_seconds,
                )
            except Exception as exc:
                self.breaker.record_failure(exc)
                raise

        self.breaker.record_success()
        return response
