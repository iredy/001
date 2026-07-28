# Strategy RAG Analyzer

一个面向 A 股策略文件的轻量级 RAG 检索与分析落地示例，覆盖“高位科技”和“低位消费”两类板块观点。

## 功能

- 从策略文本中检索相关片段。
- 内置板块股票池：高位科技、低位消费。
- 输出可直接交给 LLM 的结构化分析上下文。
- 在没有外部向量库和大模型依赖时，可用本地关键词检索跑通流程。

## 快速开始

```bash
python -m strategy_rag --query "高位科技和低位消费怎么配置" --corpus data/strategy_notes/20260605_rag_strategy.md
```

## 设计说明

`strategy_rag.py` 提供了最小可运行实现：

1. 将策略文件按标题和段落切块。
2. 使用中文关键词重叠度进行召回。
3. 针对高位科技和低位消费分别补充股票池、风险点和动作建议。
4. 生成便于 LLM 二次总结的 Markdown 输出。

生产环境可以把 `KeywordRetriever` 替换为向量检索器，把 `render_analysis` 的结果作为 LLM prompt 的检索上下文。
