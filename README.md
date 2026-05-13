# Token Strategy Toolkit

这个仓库提供一套可直接嵌入 OpenClaw / RAG 服务的 Token 成本控制代码，目标是把“65k input tokens / 次”的粗放调用压到约 5k tokens / 次。

## 落地策略

1. **RAG Top-K 限流**：默认每次只取最相关的 3 条文档，避免把整份 `strategymasterdb.json` 塞进提示词。
2. **分区预算**：分别限制 system prompt、历史消息、RAG 片段和用户问题的 token 上限。
3. **历史压缩**：只保留能放进预算内的最新对话，旧消息应在业务层先摘要后入库。
4. **调用前估算成本**：在请求商业模型前输出 `estimated_input_tokens` 和 `estimated_max_cost_usd`，方便日志告警。

## 快速使用

```python
from token_strategy import Document, TokenBudget, TokenOptimizer

optimizer = TokenOptimizer(TokenBudget(max_input_tokens=5_000, rag_top_k=3))
decision = optimizer.build_request(
    system_prompt="你是策略助手，只根据 RAG 片段回答。",
    user_prompt="科创50回调后怎么做？",
    documents=[Document(id="2026-05-13", text="科创50 缩量回调，关注支撑位...")],
)

print(decision.estimated_input_tokens)
print(decision.estimated_max_cost_usd)
```

完整接入示例见 [`examples/openclaw_token_policy.py`](examples/openclaw_token_policy.py)。

## 建议参数

| 场景 | 建议值 |
| --- | --- |
| `max_input_tokens` | `5_000` |
| `rag_top_k` | `2-3` |
| `max_rag_tokens` | `2_000-3_000` |
| `max_history_tokens` | `800-1_200` |
| 昂贵模型调用阈值 | 仅在清洗、摘要和检索后调用 |

## 开发检查

```bash
python -m pytest
```
