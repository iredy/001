# Stable low-cost model selection for `runsectoranalysis.py`

## Goal

Use cheaper models for large framework/sector-analysis jobs without reintroducing dynamic model-routing code or changing the Python runtime environment that `runsectoranalysis.py` depends on.

## Design principle

Keep model choice outside the application process tree and inject it only through environment variables before the existing entrypoint starts.

This avoids the failure mode where a model-switch route changes the working directory, import path, process environment, or execution context and then `runsectoranalysis.py` can no longer locate its files.

## Recommended execution flow

1. Keep `runsectoranalysis.py` and the OpenClaw code path unchanged.
2. Start analysis from the same working directory that already works today.
3. Use a thin launcher script to export provider/model environment variables.
4. Let the existing hardcoded `siliconflowllmcall` read those variables at runtime.
5. Choose the model profile by setting a single shell variable such as `OPENCLAW_MODEL_PROFILE=budget`.

## Model profiles

| Profile | Intended use | Token-cost posture |
| --- | --- | --- |
| `budget` | Daily 65k-token sector/framework analysis, drafts, broad scans | Lowest cost |
| `balanced` | Routine production strategy runs that need better reasoning | Moderate cost |
| `premium` | Final investment memo, difficult synthesis, high-stakes review | Highest quality/cost |

The exact model IDs are intentionally environment-level configuration, not application routing logic. Set currently valid SiliconFlow model IDs in the shell, CI secret store, or local untracked `.env` file used by the launcher. The repository should not hardcode model IDs that may become unavailable or unexpectedly expensive.

## Environment contract

The launcher exports only provider/model variables and does not mutate Python path, virtualenv, or repository location.

Required variables:

- `SILICONFLOW_API_KEY`: API key for SiliconFlow.
- `SILICONFLOW_MODEL`: model ID consumed by `siliconflowllmcall`; alternatively set the profile-specific variable below.

Optional variables:

- `SILICONFLOW_BASE_URL`: provider endpoint, if the existing caller supports it.
- `OPENCLAW_MODEL_PROFILE`: `budget`, `balanced`, or `premium`.
- `OPENCLAW_BUDGET_MODEL`, `OPENCLAW_BALANCED_MODEL`, `OPENCLAW_PREMIUM_MODEL`: profile-to-model mapping kept outside application code.
- `RUNSECTORANALYSIS_PATH`: explicit path to `runsectoranalysis.py` when it is not in the current directory.

## Example commands

Run a daily low-cost analysis:

```bash
export SILICONFLOW_API_KEY='***'
export OPENCLAW_BUDGET_MODEL='provider/current-low-cost-model'
OPENCLAW_MODEL_PROFILE=budget ./scripts/run_sector_analysis_env.sh -- --sector technology
```

Run a higher-quality final pass without changing code:

```bash
export SILICONFLOW_API_KEY='***'
export OPENCLAW_PREMIUM_MODEL='provider/current-premium-model'
OPENCLAW_MODEL_PROFILE=premium ./scripts/run_sector_analysis_env.sh -- --sector technology
```

If `runsectoranalysis.py` lives elsewhere:

```bash
RUNSECTORANALYSIS_PATH=/absolute/path/to/runsectoranalysis.py \
OPENCLAW_MODEL_PROFILE=budget \
./scripts/run_sector_analysis_env.sh -- --sector technology
```

Arguments after `--` are passed directly to `runsectoranalysis.py`.

## Why this is safer than dynamic routing

- No application route changes the current working directory.
- No application route rewrites import paths.
- No runtime branch selects a model inside OpenClaw.
- The same Python entrypoint is always used.
- Model choice is observable with `env`/logs and reversible by changing one variable.

## Operational guardrails

- Keep `budget` as the default profile for large daily jobs.
- Use `premium` only for final or high-risk synthesis runs.
- Record the active `SILICONFLOW_MODEL` with each run output so results are auditable.
- Do not store API keys in git-tracked files.
