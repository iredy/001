import asyncio

import pytest

from strategy.model_router import (
    ModelRequest,
    ModelResponse,
    ProviderConfig,
    ProviderExecutor,
    ProviderUnavailable,
    TaskMeta,
    route,
)


def test_critical_tasks_always_use_primary_provider():
    decision = route(
        TaskMeta("simple_tasks", risk_level="critical", estimated_input_tokens=100),
        {"qwen_7b": True, "ctyun_primary": True},
    )

    assert decision.provider == "ctyun_primary"
    assert decision.reason == "critical_task"


def test_route_skips_unhealthy_or_over_budget_provider():
    decision = route(
        TaskMeta("simple_tasks", estimated_input_tokens=6_000),
        {"qwen_7b": True, "qwen_14b": True, "ctyun_primary": True},
        token_budget={"qwen_7b": 4_000, "qwen_14b": 16_000, "ctyun_primary": 64_000},
    )

    assert decision.provider == "qwen_14b"


def test_executor_opens_circuit_after_failures():
    async def failing_call(config, request):
        raise RuntimeError(config.name)

    async def run_test():
        executor = ProviderExecutor(
            ProviderConfig(
                name="qwen_7b",
                base_url="https://example.invalid",
                api_key_env="QWEN_API_KEY",
                model="qwen",
                failure_threshold=1,
                cooldown_seconds=60,
            ),
            failing_call,
        )

        with pytest.raises(RuntimeError):
            await executor.complete(ModelRequest(messages=[]))

        with pytest.raises(ProviderUnavailable):
            await executor.complete(ModelRequest(messages=[]))

    asyncio.run(run_test())


def test_executor_returns_normalized_response_on_success():
    async def successful_call(config, request):
        await asyncio.sleep(0)
        return ModelResponse(content="ok", provider=config.name, model=config.model)

    async def run_test():
        executor = ProviderExecutor(
            ProviderConfig(
                name="ctyun_primary",
                base_url="https://example.invalid",
                api_key_env="CTYUN_API_KEY",
                model="primary",
            ),
            successful_call,
        )

        response = await executor.complete(ModelRequest(messages=[]))

        assert response.content == "ok"
        assert response.provider == "ctyun_primary"

    asyncio.run(run_test())
