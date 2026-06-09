# 001

## 运行中断解决方案

本仓库新增了一个可复用的个股批量分析运行器，用于解决“科创50成分股分析”这类长任务在第 N 只股票处中断的问题。

核心策略：

- **单股失败不终止整批任务**：LLM API 超时、网络抖动、数据获取失败会被记录为单只股票失败，默认继续处理后续股票。
- **自动重试**：对 `TimeoutError`、`ConnectionError` 和 `RetryableAnalysisError` 进行指数退避重试。
- **单股超时隔离**：每只股票有独立超时时间，避免卡死在如 `[15/20] 芯联集成`。
- **检查点续跑**：每完成或失败一只股票都会写入 JSON checkpoint，再次运行会跳过已成功股票。
- **优雅停止**：收到 `SIGINT`/`SIGTERM` 后保存当前进度，后续可以继续运行。

### 示例

准备股票列表：

```json
[
  {"code": "688469", "name": "芯联集成"},
  {"code": "688981", "name": "中芯国际"}
]
```

运行：

```bash
python -m stock_analysis.resilient_batch stocks.json --checkpoint .analysis_checkpoint.json --timeout 180 --max-attempts 3
```

在真实项目中，将 `demo_analyze_one` 替换为你的数据获取和 LLM 分析逻辑即可；如果遇到可恢复错误，请抛出 `TimeoutError`、`ConnectionError` 或 `RetryableAnalysisError`，运行器会自动重试并落盘。
