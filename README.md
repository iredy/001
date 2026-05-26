# 001

科创板/成长股排序模型补丁示例。

新增 `ranking_model.py`：
- 保留基础综合分公式：`0.70*策略 + 0.15*真相 + 0.15*估值`
- 增加 `GrowthCompensationConfig`（成长补偿系数）
- 增加 `sector_adaptive_weights`（按行情切换权重）

## 运行示例

```bash
python3 ranking_model.py
```
