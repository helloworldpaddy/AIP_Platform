# AML agent evaluation (ADK)

Starter evalsets for the four AML investigation stage agents. Each `.evalset.json`
follows the ADK evaluation format; `eval_config.json` scores responses with the
`rubric_based_final_response_quality_v1` judge (grounding + task/schema), which
does not require reference answers and tolerates the non-deterministic JSON the
agents produce.

During eval the agents run **standalone** (no orchestrator DB context), so the
context-aware tools return safe stubs — scoring focuses on the agent's reasoning,
tool usage, and output schema rather than real data.

## Multi-agent note

This repo is a multi-agent project: `agents-cli`'s `agent_directory`
(`backend/aml/agents/stages`) is the parent that `adk web` discovers. Because
`agents-cli eval run` / `adk eval` target a *single* agent module, run eval per
stage by pointing `adk eval` at the specific stage package:

```bash
# from the repo root, with GOOGLE_API_KEY exported
adk eval backend/aml/agents/stages/initial_assessment \
    tests/eval/evalsets/initial_assessment.evalset.json \
    --config_file_path tests/eval/eval_config.json

adk eval backend/aml/agents/stages/transaction_enrichment \
    tests/eval/evalsets/transaction_enrichment.evalset.json \
    --config_file_path tests/eval/eval_config.json

adk eval backend/aml/agents/stages/due_diligence \
    tests/eval/evalsets/due_diligence.evalset.json \
    --config_file_path tests/eval/eval_config.json

adk eval backend/aml/agents/stages/case_analysis \
    tests/eval/evalsets/case_analysis.evalset.json \
    --config_file_path tests/eval/eval_config.json
```

`agents-cli eval run --evalset <path> --config tests/eval/eval_config.json` also
works if you temporarily point `[tool.agents-cli].agent_directory` at a single
stage (it wraps `adk eval ./{agent_directory} <evalset>`).

## Run all stages (Sprint 5 harness)

```bash
export GOOGLE_API_KEY=...
chmod +x scripts/run_aml_evals.sh
./scripts/run_aml_evals.sh
./scripts/run_aml_evals.sh due_diligence   # single stage
```

## Parity vs orchestrator

Stub-based parity (no LLM) lives in `tests/aml/test_parity_harness.py`.
Transport architecture: `docs/AGENT_TRANSPORT.md`.

## Iterating (eval-fix loop)

1. Start with these 1-2 cases per stage.
2. Run a stage's eval, read the scores.
3. If below threshold, refine the agent instruction in
   `backend/aml/agents/prompts.py` (shared by both surfaces) — do not lower the
   threshold to pass.
4. Re-run. Expand coverage once the core cases pass.

## Enabling tool-trajectory scoring

The evalsets include expected `intermediate_data.tool_uses` as documentation.
To score them, add to `eval_config.json`:

```json
"tool_trajectory_avg_score": { "threshold": 1.0, "match_type": "ANY_ORDER" }
```

Note: trajectory matching also compares tool *args*; tighten the evalset `args`
or prefer `rubric_based_tool_use_quality_v1` if the agent's arguments vary.
