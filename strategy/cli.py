from __future__ import annotations

import argparse
import json

from .data_source import FetchConfig
from .engine import evaluate_csv, evaluate_csv_url


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the high-confidence strategy ensemble on OHLCV CSV data.")
    parser.add_argument("source", help="Local CSV path or http(s) CSV URL with date,open,high,low,close,volume columns")
    parser.add_argument("--timeout", type=float, default=5.0, help="Remote fetch timeout in seconds")
    parser.add_argument("--retries", type=int, default=3, help="Remote fetch retry attempts")
    parser.add_argument("--no-stale-cache", action="store_true", help="Disable stale-cache fallback for remote data")
    args = parser.parse_args()
    if args.source.startswith(("http://", "https://")):
        config = FetchConfig(timeout_seconds=args.timeout, retries=args.retries, allow_stale_cache=not args.no_stale_cache)
        decision = evaluate_csv_url(args.source, config=config)
    else:
        decision = evaluate_csv(args.source)
    payload = {
        "action": decision.action.value,
        "confidence": round(decision.confidence, 4),
        "risk_score": round(decision.risk_score, 4),
        "position_size": round(decision.position_size, 4),
        "reason": decision.reason,
        "signals": [
            {
                "module": signal.module,
                "action": signal.action.value,
                "confidence": round(signal.confidence, 4),
                "reason": signal.reason,
                "metadata": signal.metadata,
            }
            for signal in decision.signals
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
