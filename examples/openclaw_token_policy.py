"""Example OpenClaw-style token policy wiring.

Replace `raw_documents` with the strategy records loaded from your local
strategymasterdb.json.  The important rule is to pass only `decision.rag_context`
to the expensive model, never the full database.
"""

from token_strategy import Document, Message, TokenBudget, TokenOptimizer

SYSTEM_PROMPT = """你是量化策略助手。只基于给定 RAG 片段和用户问题输出结论。
不要复述全部历史策略；优先给出风险、触发条件和操作建议。"""


def build_payload(user_prompt: str, raw_documents: list[dict[str, str]]) -> dict[str, object]:
    optimizer = TokenOptimizer(
        TokenBudget(
            max_input_tokens=5_000,
            max_system_tokens=500,
            max_history_tokens=800,
            max_rag_tokens=2_700,
            max_user_tokens=600,
            rag_top_k=3,
            input_price_per_million=15.38,
        )
    )

    documents = [
        Document(id=row["id"], text=row["content"], metadata={"date": row.get("date", "")})
        for row in raw_documents
    ]
    history = [
        Message(role="user", content="上一轮请分析科创 50 回调。"),
        Message(role="assistant", content="已记录：重点关注成交量、支撑位和政策催化。"),
    ]

    decision = optimizer.build_request(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        history=history,
        documents=documents,
    )

    return {
        "system": decision.system_prompt,
        "messages": [message.__dict__ for message in decision.messages],
        "rag_context": [doc.__dict__ for doc in decision.rag_context],
        "telemetry": {
            "estimated_input_tokens": decision.estimated_input_tokens,
            "estimated_max_cost_usd": decision.estimated_max_cost_usd,
            "dropped_history_messages": decision.dropped_history_messages,
            "dropped_rag_documents": decision.dropped_rag_documents,
        },
    }
