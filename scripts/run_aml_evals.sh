#!/usr/bin/env bash
# Run ADK eval for all four AML investigation stages (Sprint 5 harness).
#
# Requires GOOGLE_API_KEY and the repo virtualenv with google-adk installed.
#
# Usage (from repo root):
#   export GOOGLE_API_KEY=...
#   ./scripts/run_aml_evals.sh
#   ./scripts/run_aml_evals.sh initial_assessment   # one stage only

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CONFIG="tests/eval/eval_config.json"
STAGES=(
  initial_assessment
  transaction_enrichment
  due_diligence
  case_analysis
)

run_stage() {
  local stage="$1"
  echo "==> adk eval ${stage}"
  adk eval "backend/aml/agents/stages/${stage}" \
    "tests/eval/evalsets/${stage}.evalset.json" \
    --config_file_path "$CONFIG"
}

if [[ $# -gt 0 ]]; then
  run_stage "$1"
else
  for stage in "${STAGES[@]}"; do
    run_stage "$stage"
  done
fi

echo "All requested evals finished."
