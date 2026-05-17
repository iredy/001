#!/usr/bin/env bash
set -euo pipefail

# Thin environment-variable launcher for runsectoranalysis.py.
# It deliberately avoids changing cwd, PYTHONPATH, virtualenv, or repo layout.

usage() {
  cat <<'USAGE'
Usage:
  OPENCLAW_MODEL_PROFILE=budget ./scripts/run_sector_analysis_env.sh -- [runsectoranalysis args]

Environment:
  SILICONFLOW_API_KEY       Required API key.
  OPENCLAW_MODEL_PROFILE    budget | balanced | premium. Default: budget.
  OPENCLAW_BUDGET_MODEL     Model ID for budget runs. Required unless SILICONFLOW_MODEL is set.
  OPENCLAW_BALANCED_MODEL   Model ID for balanced runs. Required unless SILICONFLOW_MODEL is set.
  OPENCLAW_PREMIUM_MODEL    Model ID for premium runs. Required unless SILICONFLOW_MODEL is set.
  SILICONFLOW_MODEL         Explicit model override. If set, profile variables are ignored.
  SILICONFLOW_BASE_URL      Optional provider endpoint passed through unchanged.
  RUNSECTORANALYSIS_PATH    Optional explicit path to runsectoranalysis.py.
  PYTHON                    Python executable. Default: python3.

Arguments after -- are passed directly to runsectoranalysis.py.
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "${1:-}" == "--" ]]; then
  shift
fi

: "${SILICONFLOW_API_KEY:?SILICONFLOW_API_KEY is required}"

profile="${OPENCLAW_MODEL_PROFILE:-budget}"
case "$profile" in
  budget)
    profile_model_var="OPENCLAW_BUDGET_MODEL"
    ;;
  balanced)
    profile_model_var="OPENCLAW_BALANCED_MODEL"
    ;;
  premium)
    profile_model_var="OPENCLAW_PREMIUM_MODEL"
    ;;
  *)
    echo "Unsupported OPENCLAW_MODEL_PROFILE: $profile" >&2
    echo "Expected: budget, balanced, or premium" >&2
    exit 2
    ;;
esac

if [[ -z "${SILICONFLOW_MODEL:-}" ]]; then
  profile_model="${!profile_model_var:-}"
  if [[ -z "$profile_model" ]]; then
    echo "SILICONFLOW_MODEL is not set and $profile_model_var is empty." >&2
    echo "Set an explicit model ID in the environment instead of relying on code routing." >&2
    exit 2
  fi
  export SILICONFLOW_MODEL="$profile_model"
fi

script_path="${RUNSECTORANALYSIS_PATH:-runsectoranalysis.py}"
if [[ ! -f "$script_path" ]]; then
  echo "Cannot find runsectoranalysis.py at: $script_path" >&2
  echo "Run this launcher from the directory that already works, or set RUNSECTORANALYSIS_PATH." >&2
  exit 3
fi

python_bin="${PYTHON:-python3}"

echo "OpenClaw model profile: $profile" >&2
echo "SiliconFlow model: $SILICONFLOW_MODEL" >&2
echo "Entrypoint: $script_path" >&2

exec "$python_bin" "$script_path" "$@"
