# Token 消耗优化与多模型路由冲突治理方案

## 背景与目标

近期会话的主要问题是 Input Tokens 远高于 Output Tokens，且上下文、PR diff、股票/宏观数据重复加载导致成本和延迟放大。目标不是简单恢复旧版多模型路由，而是在 OpenClaw + 天翼云部署环境中引入“安全、可回退、可观测”的路由与缓存体系，避免历史上多模型并发调用冲突导致服务瘫痪的问题。

核心目标：

- 将单会话 token 消耗从约 762K 降至约 150K。
- 将单会话成本从约 $11.67 降至约 $2.3。
- 在恢复模型路由的同时，保证 OpenClaw 调用链不再因并发、配置串扰、上下文污染或 provider 限流而全局不可用。
- 将优化能力做成渐进式开关，先灰度验证，再全量启用。

## 根因分析

### 1. 路由冲突的常见触发点

在 OpenClaw 接入多模型时，历史瘫痪通常不是“模型路由”这个概念本身造成的，而是以下工程问题叠加：

1. **全局客户端状态被共享**：多个 provider 的 base URL、API key、超时、重试参数写在全局对象中，并发请求相互覆盖。
2. **路由选择与执行耦合**：路由逻辑直接创建请求并调用模型，失败后无法精确定位是分类、鉴权、网络还是模型响应问题。
3. **无熔断与降级**：某个模型超时、限流或响应格式异常时，请求继续堆积，最终拖垮 worker。
4. **上下文复用不隔离**：不同模型的 prompt 模板、工具描述、历史摘要混用，导致调用参数不兼容或 token 爆炸。
5. **并发控制缺失**：多个低价模型并行抢占连接池、线程池或天翼云网关配额，使关键路径模型也不可用。
6. **缺少幂等缓存**：失败重试与心跳任务重复拉取同一批数据，造成级联放大。

### 2. Token 膨胀的直接来源

| 来源 | 风险 | 治理方向 |
|:---|:---|:---|
| MEMORY.md 全量加载 | 每次请求固定 25K+ token | 时间切片 + 摘要索引 |
| 技能文件全量加载 | 简单任务也加载复杂说明 | 懒加载 + 任务触发 |
| PR diff 重复读取 | 同一 diff 在多轮中反复进入上下文 | diff 摘要缓存 |
| 股票/宏观数据逐项请求 | 网络和 token 双重放大 | 批量数据接口 + stale cache |
| 心跳全量扫描 | 空转消耗 | next_check_at + 增量状态 |

## 推荐总体架构

建议把“模型路由”拆成四层，避免再次出现 OpenClaw 调用冲突：

```text
请求入口
  ↓
任务分类层 Task Classifier：只输出 task_type、risk_level、context_budget
  ↓
预算与上下文层 Context Budgeter：决定加载哪些记忆、diff、技能和数据摘要
  ↓
模型路由层 Model Router：只选择 provider/model，不直接拼接全局状态
  ↓
隔离执行层 Provider Executor：每个 provider 独立客户端、连接池、限流器、熔断器
```

关键原则：

- **分类与执行分离**：路由只产出决策，不直接调用模型。
- **provider 实例隔离**：每个模型供应商使用独立 client、timeout、retry、semaphore、circuit breaker。
- **强制 fallback**：任何非关键模型失败都必须可降级到主模型或缓存结果。
- **先预算，后加载上下文**：先判断任务复杂度，再加载最小必要上下文。
- **可观测优先**：所有路由决策、fallback、cache hit/miss、token 预算都记录结构化日志。

## 多模型路由冲突解决方案

### 方案 A：保守恢复，单入口串行路由

适用于先止血、验证稳定性。

- 保留 OpenClaw 现有主模型作为唯一默认执行器。
- 只对低风险任务启用便宜模型，例如格式化、摘要、简单分类。
- 同一用户请求最多触发一次模型调用，不做多模型并行竞选。
- 任一便宜模型失败，立即回退主模型。
- 全局增加 `MODEL_ROUTER_ENABLED=false` 默认关闭，灰度时按用户或任务开启。

优点：上线风险最低。缺点：节省幅度低于完整路由。

### 方案 B：隔离执行器 + 熔断器

适用于稳定灰度后的主方案。

每个 provider 都应有自己的执行器：

```python
@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str
    api_key_env: str
    model: str
    timeout_seconds: float
    max_concurrency: int
    rpm_limit: int
    failure_threshold: int
    cooldown_seconds: int

class ProviderExecutor:
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.client = build_client(config)
        self.semaphore = asyncio.Semaphore(config.max_concurrency)
        self.breaker = CircuitBreaker(
            failure_threshold=config.failure_threshold,
            cooldown_seconds=config.cooldown_seconds,
        )

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if not self.breaker.allow_request():
            raise ProviderUnavailable(self.config.name)
        async with self.semaphore:
            try:
                response = await self.client.chat.completions.create(
                    model=self.config.model,
                    messages=request.messages,
                    timeout=self.config.timeout_seconds,
                )
                self.breaker.record_success()
                return normalize_response(response)
            except Exception as exc:
                self.breaker.record_failure(exc)
                raise
```

重点是禁止以下写法：

```python
# 禁止：多个 provider 共享可变全局配置
openai_client.base_url = selected_base_url
openai_client.api_key = selected_api_key
```

应改为：

```python
# 推荐：启动时创建独立 client，运行期只查表
executors = {
    "qwen_7b": ProviderExecutor(qwen_7b_config),
    "qwen_14b": ProviderExecutor(qwen_14b_config),
    "deepseek_v3": ProviderExecutor(deepseek_config),
    "ctyun_primary": ProviderExecutor(ctyun_config),
}
```

### 方案 C：队列隔离 + 关键路径保护

适用于股票批量分析、RAG 重建、心跳任务等高吞吐场景。

- 将在线问答、定时心跳、批量股票任务拆成不同队列。
- 每个队列设置独立并发上限。
- 天翼云关键模型保留独立并发配额，不被低价模型重试耗尽。
- 批处理任务采用 backpressure，超过阈值进入延迟队列，不阻塞在线请求。

推荐配额示例：

| 队列 | 并发 | 超时 | 失败策略 |
|:---|:---:|:---:|:---|
| online_critical | 2-4 | 30s | 回退主模型 |
| online_simple | 4-8 | 10s | 回退主模型 |
| batch_stock | 1-2 | 60s | 使用 stale cache |
| heartbeat | 1 | 10s | 跳过并记录下次检查 |

## 推荐路由策略

### 任务类型与模型映射

| 任务类型 | 默认模型 | 失败回退 | 上下文预算 |
|:---|:---|:---|:---:|
| simple_tasks | Qwen2.5-7B | Qwen2.5-14B 或天翼云 | 2K-4K |
| daily_tasks | Qwen2.5-14B | DeepSeek-V3 或天翼云 | 8K-16K |
| complex_analysis | DeepSeek-V3 | 天翼云 | 24K-48K |
| critical_decisions | 天翼云 | 人工确认/延迟重试 | 48K+ |

### 路由伪代码

```python
def route(task: TaskMeta, health: HealthState) -> RouteDecision:
    if not feature_flags.model_router_enabled:
        return RouteDecision("ctyun_primary", reason="router_disabled")

    if task.risk_level == "critical":
        return RouteDecision("ctyun_primary", reason="critical_task")

    candidates = ROUTE_TABLE[task.task_type]
    for candidate in candidates:
        if health.is_available(candidate) and budget.allows(candidate, task):
            return RouteDecision(candidate, reason="matched_task_type")

    return RouteDecision("ctyun_primary", reason="fallback_no_candidate")
```

### 防冲突硬性规则

1. 不允许运行期修改共享 OpenAI SDK client 的 base URL 或 API key。
2. 不允许便宜模型与天翼云主模型共用同一个连接池、semaphore 或 retry budget。
3. 不允许路由层读取完整 MEMORY.md、完整 PR diff 或完整股票明细。
4. 不允许后台心跳任务触发高优先级模型调用。
5. 不允许失败重试跨 provider 无限递归；最多一次 fallback。
6. 不允许无缓存的批量数据任务在在线请求链路内同步执行。

## 上下文压缩方案

### MEMORY.md 时间切片

将记忆拆为三层：

| 层级 | 内容 | 加载策略 |
|:---|:---|:---|
| hot | 最近 7 天高频事实 | 默认加载 |
| warm | 最近 30-90 天摘要 | 关键词命中加载 |
| cold | 历史归档 | 明确需要时加载 |

建议文件结构：

```text
memory/
  hot/2026-W31.md
  warm/2026-07-summary.md
  cold/2026-Q2.md
  index.json
```

`index.json` 维护关键词、时间范围、摘要和路径。请求开始时只读取 index 与 hot summary，不读取全部原文。

### PR diff 摘要缓存

缓存键建议：

```text
pr:{repo}:{pr_number}:{head_sha}:diff_summary
```

缓存内容包括：

- 变更文件列表。
- 每个文件 3-5 条摘要。
- 测试影响面。
- 风险点。
- 是否需要重新拉取完整 diff。

只有当 `head_sha` 变化时才刷新。

## 数据缓存与批量处理

### 统一 FetchConfig

所有宏观数据、行情数据、新闻数据和财报数据请求都应走统一数据源层：

```python
config = FetchConfig(
    timeout_seconds=5.0,
    retries=3,
    allow_stale_cache=True,
)
```

缓存 TTL 建议：

| 数据类型 | TTL | stale 可用时长 |
|:---|:---:|:---:|
| 实时行情 | 30-120 秒 | 15 分钟 |
| 日线/财务指标 | 6-24 小时 | 7 天 |
| 宏观指标 | 1-7 天 | 30 天 |
| PR diff 摘要 | 按 head_sha | 永久 |
| RAG 索引 | 按文档 hash | 永久 |

### 股票批量分析

把逐只股票调用改为：

```python
symbols = ["AAPL", "MSFT", "NVDA", ...]
quotes = market_data.fetch_quotes_batch(symbols, config=config)
fundamentals = fundamentals.fetch_batch(symbols, config=config)
result = analyzer.rank_batch(symbols, quotes, fundamentals)
```

要求：

- 数据获取批量化。
- 模型分析只输入结构化摘要，不输入原始长表。
- 排名、过滤和异常值检测优先用本地代码完成，模型只解释结果。

## 心跳任务优化

`memory/heartbeat-state.json` 应增加以下字段：

```json
{
  "last_check_at": "2026-07-28T00:00:00Z",
  "next_check_at": "2026-07-28T06:00:00Z",
  "last_success_at": "2026-07-28T00:00:00Z",
  "last_digest_hash": "sha256:...",
  "consecutive_failures": 0
}
```

执行规则：

- 当前时间早于 `next_check_at` 时直接跳过。
- 输入数据 hash 未变化时不重新总结。
- 连续失败超过阈值后延长下一次检查间隔。
- 心跳只写状态与摘要，不触发完整 RAG 或全量记忆加载。

## 灰度上线计划

### 第 0 阶段：观测基线

- 记录每次请求的 input_tokens、output_tokens、cache_hit、route_decision、provider_latency。
- 不改变模型调用路径。
- 输出一周基线报表。

### 第 1 阶段：上下文预算先行

- 实施 MEMORY hot/warm/cold 切片。
- PR diff 改为按 `head_sha` 缓存摘要。
- 技能文件按任务触发懒加载。
- 目标：不启用多模型也先降低 30%-50% input tokens。

### 第 2 阶段：只读路由影子模式

- 路由器只计算推荐模型，不真正切换。
- 对比推荐模型与实际主模型成本、延迟和错误率。
- 验证任务分类准确率。

### 第 3 阶段：低风险任务灰度

- 仅 simple_tasks 启用 Qwen2.5-7B。
- 灰度比例 5% → 25% → 50%。
- 错误率、超时率、fallback 率任一超过阈值则自动关闭。

### 第 4 阶段：批量任务与日常任务迁移

- daily_tasks 迁移到 Qwen2.5-14B。
- batch_stock 独立队列与缓存兜底。
- RAG 索引持久化。

### 第 5 阶段：复杂任务可控分流

- complex_analysis 迁移到 DeepSeek-V3，但保留天翼云最终复核或 fallback。
- critical_decisions 始终默认天翼云。

## 回滚与熔断标准

任一条件满足时立即回滚到天翼云主模型：

- 某 provider 5 分钟内连续失败超过 5 次。
- P95 延迟超过基线 2 倍并持续 10 分钟。
- fallback 率超过 20%。
- 响应格式错误率超过 2%。
- OpenClaw worker 队列积压超过阈值。
- 关键任务误路由到非关键模型。

回滚必须是配置级操作，不依赖重新部署：

```text
MODEL_ROUTER_ENABLED=false
SIMPLE_TASK_ROUTING_ENABLED=false
BATCH_MODEL_ROUTING_ENABLED=false
```

## 验收指标

| 指标 | 目标 |
|:---|:---:|
| Input tokens | 降低 70%-80% |
| 单会话成本 | 降低 70%+ |
| cache hit rate | 60%+ |
| fallback rate | < 5% |
| provider error rate | < 1% |
| OpenClaw 全局不可用事件 | 0 |
| P95 延迟 | 提升 3-5 倍或不劣于基线 |

## 最小可执行落地顺序

1. 先做上下文预算与缓存，不立即打开多模型路由。
2. 把 provider client 改成完全隔离实例，移除共享可变全局配置。
3. 增加 provider 级 semaphore、timeout、retry budget、circuit breaker。
4. 开启影子路由，只记录不执行。
5. 对 simple_tasks 小流量启用 Qwen2.5-7B。
6. 稳定后再迁移 daily_tasks 和 batch_stock。
7. critical_decisions 永远保持天翼云优先。

## 结论

不建议直接恢复旧版智能路由。正确做法是先把上下文、缓存和执行器隔离做好，再以影子模式和灰度开关恢复多模型路由。这样既能获得 75%-90% 的成本节省潜力，又能避免 OpenClaw 在天翼云环境中因共享客户端、并发失控、provider 限流或 fallback 递归而再次瘫痪。
