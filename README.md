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


## 不改运行环境的低成本启动方案

如果 `runsectoranalysis.py` 已经在内部调用 `siliconflowllmcall`，不要再增加动态模型路由；最稳妥的方式是在启动时注入环境变量。仓库根目录提供了 [`run_lowcost_analysis.bat`](run_lowcost_analysis.bat)：

1. 使用 `%~dp0` + `cd /d` 锁定脚本所在目录，避免双击或云电脑重启后找不到 `runsectoranalysis.py`。
2. 使用 `PYTHONPATH=%PROJECT_ROOT%;%PYTHONPATH%` 固定导入根路径，不改 OpenClaw 代码结构。
3. 只通过 `SILICON_API_KEY` 和可选的 `SILICON_MODEL` 注入低成本通道；真实 API Key 不提交到仓库。
4. 默认模型提示为 `Qwen/Qwen2.5-14B-Instruct`，如果框架已支持读取 `SILICON_MODEL`，可在不改路由的情况下切换到更便宜的模型。

Windows 使用方式：

```bat
setx SILICON_API_KEY "sk-你的真实key"
cd /d C:\Users\Administrator\clawd
run_lowcost_analysis.bat
```

如果你的框架没有读取 `SILICON_MODEL`，也不需要强行改路由；先保持原来的 `siliconflowllmcall` 入口，只把 Key、路径和 `PYTHONPATH` 固定住，再在原有配置文件里调整默认模型。

## 开发检查

```bash
python -m pytest
```
