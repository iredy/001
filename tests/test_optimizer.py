from token_strategy import Document, Message, TokenBudget, TokenOptimizer, estimate_tokens


def test_estimate_tokens_counts_chinese_more_conservatively():
    assert estimate_tokens("科创50回调") >= 5
    assert estimate_tokens("abcd") == 1


def test_rag_context_respects_top_k_and_budget():
    optimizer = TokenOptimizer(TokenBudget(max_rag_tokens=40, rag_top_k=2))
    docs = [
        Document(id="a", text="白酒 消费 防御" * 50),
        Document(id="b", text="科创50 半导体 回调 支撑" * 50),
        Document(id="c", text="科创50 成交量 放大" * 50),
    ]

    selected = optimizer.select_rag_context("科创50 回调 成交量", docs)

    assert len(selected) == 2
    assert sum(estimate_tokens(doc.text) for doc in selected) <= 40
    assert {doc.id for doc in selected} <= {"b", "c"}


def test_build_request_drops_old_history_and_estimates_cost():
    optimizer = TokenOptimizer(
        TokenBudget(
            max_input_tokens=500,
            max_history_tokens=20,
            max_rag_tokens=60,
            rag_top_k=1,
            input_price_per_million=15.38,
        )
    )
    history = [
        Message(role="user", content="很早以前的长消息" * 30),
        Message(role="assistant", content="最近结论：关注缩量企稳"),
    ]
    docs = [Document(id="strategy-1", text="科创50 回调 缩量 支撑位" * 20)]

    decision = optimizer.build_request(
        system_prompt="短系统提示",
        user_prompt="科创50 回调后怎么做？",
        history=history,
        documents=docs,
    )

    assert decision.dropped_history_messages == 1
    assert decision.dropped_rag_documents == 0
    assert decision.estimated_input_tokens <= 500
    assert decision.estimated_max_cost_usd > 0
