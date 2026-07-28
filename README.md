# 001

This repository contains a concrete implementation and rollout guidance for reducing token consumption while safely restoring multi-model routing in OpenClaw/Tianyi Cloud deployments.

## Contents

- `TOKEN_OPTIMIZATION_PLAN.md` — Chinese rollout and architecture plan for token reduction, cache strategy, gray release, and rollback rules.
- `strategy/model_router.py` — executable routing primitives with provider isolation, token-budget checks, semaphores, timeouts, and circuit breakers.
- `strategy/data_source.py` — cache-first data-source helpers with stale-cache fallback for PR summaries, market data, macro data, and heartbeat snapshots.
- `tests/` — unit tests covering routing, circuit breaking, and stale-cache behavior.

## Quick checks

```bash
python -m pytest
```
