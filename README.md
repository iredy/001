# 001

Quant signal adjustment utilities for RAG-assisted trading workflows.

## Sector deviation guardrail

`macro_adjust.py` implements the base weighted score:

```text
Final Score = Macro(25%) + Density(20%) + Technical(20%) + Sentiment(15%) + Swing(10%) + Volume-Price(10%)
```

It also adds a temporary **sector over-extension correction** for cases where RAG surfaces `divergenceflag=true` and a sector or leader is materially above MA5. The guardrail starts reducing score after a +10% MA5 deviation and reaches its default maximum haircut at +18% deviation. When `divergenceflag=true`, the haircut is multiplied by `1.25` so crowded blow-off moves are de-risked without replacing the hard directional signal.

```python
from macro_adjust import score_with_macro_adjustment

result = score_with_macro_adjustment(
    {
        "macro": 0.2,
        "density": 0.4,
        "technical": 0.6,
        "sentiment": 0.1,
        "swing": 0.3,
        "volume_price": 1.0,
    },
    ma5_deviation=0.18,
    divergenceflag=True,
)

print(result["adjusted_score"])
```

The result includes `raw_score`, `sector_deviation_penalty`, `adjusted_score`, and `divergenceflag` so execution logs can show why an otherwise strong signal was moved from hold/add toward hold/reduce.
