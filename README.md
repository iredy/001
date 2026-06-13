# 001

科创50模型优化示例代码。

## 功能

- 对原始 `buy/hold/sell` 信号进行 PR11/PR12 冲突校验。
- 对高位退潮、基本面过弱、量化分数与信号不一致的样本执行降级规则。
- 根据冲突数量自动下调置信度。
- 将候选股分为 `A_core`、`B_watch`、`C_reversal_high_risk`、`D_avoid_or_reduce` 四档。
- 提供成分股数量、重复标的、异常置信度和异常分数的数据质量校验。

## 运行测试

```bash
python -m unittest discover -s tests
```
