# 策略有效性评估与代码落地

策略上线前建议分三层评估：有效性、可用性、准确性。三层都通过后，才允许进入每日批量运行与报告输出。

## 1. 有效性：回测是否创造风险调整收益

核心指标：

- 累计收益和年化收益：确认策略是否有绝对收益。
- 年化波动率、夏普比率：确认收益是否来自可接受风险。
- 最大回撤：确认最坏路径是否可承受。
- 胜率：辅助判断交易体验，不能单独作为上线依据。

落地函数：`strategy_evaluation.metrics.evaluate_backtest`。

## 2. 可用性：每日输出是否能稳定投产

核心指标：

- 可用率 = 字段完整且信号合法的行数 / 总行数。
- 缺失字段分布：定位数据源、策略或模板问题。
- 非法信号行数：拦截无法被下游仓位系统消费的结果。

建议阈值：日常运行可用率不低于 95%，关键批次不低于 99%。

落地函数：`strategy_evaluation.metrics.evaluate_availability`。

## 3. 准确性：信号与未来收益是否匹配

核心指标：

- 覆盖率：策略输出中可评价信号占比。
- 方向命中率：买入信号后未来收益为正、卖出/回避信号后未来收益为负的比例。
- 买入精确率、卖出精确率：分别监控进攻和防守质量。
- 分信号未来平均收益：验证 strong_buy、buy、hold、avoid 是否有单调性。

落地函数：`strategy_evaluation.metrics.evaluate_signal_accuracy`。

## 推荐上线门禁

1. 历史回测：年化收益为正，最大回撤低于业务阈值，夏普比率优于基准。
2. 滚动窗口：最近 3、6、12 个月指标不能同时退化。
3. 样本外验证：训练期、验证期、实盘影子期分开统计。
4. 可用性：每日批次可用率达标，缺失字段必须可追踪。
5. 准确性：买入与卖出方向命中率分别达标，且信号强弱与未来收益排序一致。

## 示例

```python
from strategy_evaluation import (
    evaluate_availability,
    evaluate_backtest,
    evaluate_signal_accuracy,
)

backtest = evaluate_backtest([0.01, -0.02, 0.015], periods_per_year=252)
accuracy = evaluate_signal_accuracy(
    ["strong_buy", "hold", "avoid"],
    [0.03, 0.001, -0.02],
)
availability = evaluate_availability([
    {"date": "2026-06-20", "symbol": "券商ETF", "signal": "buy", "score": 82},
])
```
