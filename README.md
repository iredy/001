# 001 - Integrated Investment Framework

将“宏观周期 + 三重真相 + 估值匹配 + 威科夫信号 + 风控”直接代码化的最小框架。

## Run demo

```bash
python src/trading_framework/framework.py
```

输出示例为单票决策对象：
- decision: buy / hold / reduce / exit / watchlist
- target_position: 建议目标仓位
- reasons: 触发原因

## Core design

- `detect_regime`: 周期识别（萧条/复苏/繁荣/放缓）
- `score_truth`: 物理/经济/人性三真相评分
- `score_valuation`: 估值折价与杠杆惩罚
- `score_wyckoff`: Spring/LPS/SOS 与量价验证
- `evaluate`: 汇总后输出交易动作

你可以把数据源替换为：
- 宏观数据库（PMI、信用脉冲等）
- 财报与行业数据库
- K线与成交量特征工程
