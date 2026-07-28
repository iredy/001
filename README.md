# 001

## 高置信度综合策略算法

本仓库提供一个可落地执行的 Python 策略引擎，综合以下模块信号：

- Wyckoff + Gann
- Band 波段状态机
- VolumePrice 量价策略
- Technical 技术指标策略
- Macro 宏观策略
- Sentiment 情绪策略
- Dense / Truth 代理确认信号

### 输入数据

CLI 接收 CSV，必须包含以下列：

```csv
date,open,high,low,close,volume
```

### 运行示例

```bash
python3 -m strategy.cli examples/sample_ohlcv.csv
```

输出为 JSON，包含最终动作、置信度、风险分、建议仓位和各模块明细信号。

### 远程 API 超时处理

如果行情数据来自远程 API，CLI 支持超时、重试和本地陈旧缓存兜底：

```bash
python3 -m strategy.cli "https://example.com/ohlcv.csv" --timeout 5 --retries 3
```

处理策略：

- 每次请求设置显式超时时间，避免 API 长时间挂起。
- 失败后按指数退避重试，降低瞬时网络抖动导致的中断。
- 成功响应会写入 `.cache/strategy-data/`；远程 API 全部失败时，默认使用上一次成功数据作为兜底，保证策略流程不中断。
- 如需禁止陈旧缓存，可增加 `--no-stale-cache`。

### 测试

```bash
python3 -m unittest discover -s tests
```
