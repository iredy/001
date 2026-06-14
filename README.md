# 001

## RAG 策略与指数时间序列匹配

本仓库新增 `rag_index_matcher.py`，用于把历史 RAG 策略文本与上证指数、科创 50 等指数走势进行时间序列匹配，并输出策略方向准确率、持有期收益率、最大回撤/最大上行等验证指标。

### 核心流程

```text
RAG 策略检索 -> 日期/信号提取 -> 指数数据获取 -> 交易日对齐 -> 策略效果验证 -> LLM 学习样本
```

### 快速接入

```python
from rag_index_matcher import CsvIndexDataProvider, TimeSeriesRAGIndexMatcher

# 也可替换为 AkShare/Tushare/数据库适配器，只需实现 get_index_bars()。
provider = CsvIndexDataProvider({"000001.SH": "data/sse.csv", "000688.SH": "data/star50.csv"})
matcher = TimeSeriesRAGIndexMatcher(provider)

matches, summary = matcher.retrieve_match_and_evaluate(
    query="2024-11-19 企稳反弹",
    rag_retriever=lambda q: ["2024-11-19 科创50 企稳反弹，建议加仓"],
    horizon_days=5,
    min_relevance_score=0.40,  # 过滤低相关 RAG 命中，降低噪声样本对准确率的影响
    top_k=20,
)

learning_samples = matcher.build_llm_learning_samples(matches)
```

### 功能说明

- 自动识别 `YYYY-MM-DD`、`YYYY/MM/DD`、`YYYY年M月D日`、`YYYYMMDD` 格式的策略日期。
- 通过中文关键词识别 `bullish`、`bearish`、`neutral` 三类策略信号。
- 默认使用 `000001.SH` 作为上证指数；文本包含“科创”或“科创50”时自动切换为 `000688.SH`。
- 支持通过 `sector_index_map` 扩展板块关键词与指数代码映射。
- 支持将验证结果转换为 LLM 可学习的结构化样本，帮助模型复盘“研判文本 -> 市场路径 -> 结果标签”。


### RAG 准确率提升策略

- 在回测前对 RAG 命中进行相关性重排与过滤，综合查询词重合度、日期距离、信号方向一致性和向量检索分数，避免无关历史策略进入准确率统计。
- 对相同日期、方向和策略文本的重复命中做去重，仅保留相关性和置信度最高的记录。
- 信号识别增加反向语义惩罚，例如“反弹乏力”“尚未企稳”“反弹受阻”不会被简单识别为看多信号。
- 回测汇总同时输出普通准确率和按 RAG 相关性/策略置信度加权的准确率，更适合评估检索增强研判链路。
