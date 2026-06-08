# Agent transport & A2A architecture

This document describes the orchestrator adapter layer (Sprints 1–5): how AML
workflow stages run **in-process** or on **remote A2A hosts**, how tools write
back through the **tool gateway**, and how **ADK web** can mirror production.

## Architecture

```text
Frontend / ADK web
       │
       ▼
Orchestrator (control plane)
  • load_investigation_state
  • gates, audit, agent_runs
  • build_user_prompt
  • mint tool_gateway (A2A only)
       │
       ├── InProcessAdapter ──► LlmDrivenAgent.run(ctx)
       │
       └── A2aAdapter ──► remote to_a2a host
                ▲
                │ HTTP tool-gateway (Bearer JWT)
                └──────────────────────────────┘
```

The orchestrator never delegates DB credentials to remote agents. Remote stages
call `POST /internal/tool-gateway/runs/{run_id}/invoke` with a run-scoped token.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `AML_AGENT_TRANSPORT_DEFAULT` | `in_process` | Global transport |
| `AML_AGENT_TRANSPORT_<STAGE>` | — | Per-stage override (`INITIAL_ASSESSMENT`, …) |
| `AML_A2A_<STAGE>_URL` | — | Agent card URL when transport is `a2a` |
| `AML_A2A_TIMEOUT_SECONDS` | `600` | Remote call timeout |
| `AML_A2A_CIRCUIT_FAILURE_THRESHOLD` | `5` | Failures before circuit opens |
| `AML_A2A_CIRCUIT_RECOVERY_SECONDS` | `60` | Cooldown before half-open probe |
| `AML_TOOL_GATEWAY_SECRET` | dev default | HMAC secret for gateway tokens |
| `AML_TOOL_GATEWAY_BASE_URL` | `http://localhost:8000` | URL remote agents call |
| `AML_ADK_MODE` | `hybrid` | ADK web: `hybrid` or `orchestrator` |

## Running modes

### In-process (default)

All four stages execute inside `aml-backend`. No extra services.

### Remote A2A (per stage or all)

```bash
docker compose -f docker/docker-compose.yml \
  --env-file docker/.env --env-file docker/.env.a2a \
  --profile a2a up --build
```

Open the **React frontend** at http://localhost:8080 — **Run** / **Approve** on a
case triggers the orchestrator, which delegates to remote hosts. See README
§ Option A2 for the full walkthrough.

Set in `docker/.env` (or use the `docker/.env.a2a` overlay):

```bash
AML_AGENT_TRANSPORT_DUE_DILIGENCE=a2a
AML_A2A_DUE_DILIGENCE_URL=http://dd-agent:8103/.well-known/agent-card.json
AML_TOOL_GATEWAY_BASE_URL=http://backend:8000
```

### ADK web

| Mode | Env | Behaviour |
|------|-----|-----------|
| Hybrid | `AML_ADK_MODE=hybrid` (default) | ADK LLM in-process; callbacks persist runs |
| Orchestrator | `AML_ADK_MODE=orchestrator` | Callbacks call `Orchestrator.trigger_agent` (uses transport + A2A) |

See `agents/ADK_WEB.txt` for commands and examples.

## Testing

| Suite | Command |
|-------|---------|
| Unit + integration | `pytest tests/aml/ -q` |
| Parity harness | `pytest tests/aml/test_parity_harness.py -q` |
| ADK eval (LLM) | `./scripts/run_aml_evals.sh` |

Parity checks live in `backend/aml/agents/runtime/parity.py` — they assert each
stage’s `output_payload` includes contract keys after a trigger.

## Sprint map

| Sprint | Deliverable |
|--------|-------------|
| S1 | `AgentExecutionPort`, `InProcessAdapter`, transport config |
| S2 | Tool gateway (JWT + HTTP invoke) |
| S3 | `A2aAdapter`, per-stage A2A hosts, compose profile `a2a` |
| S4 | `AML_ADK_MODE=orchestrator` for ADK web |
| S5 | Circuit breaker, parity harness, eval runner, this doc |

## Production hardening notes

- **Retries:** Orchestrator Phase 2 uses `call_with_retry` for transient LLM/provider errors.
- **Circuit breaker:** A2A adapter opens after `AML_A2A_CIRCUIT_FAILURE_THRESHOLD` consecutive failures; fast-fails until recovery window elapses.
- **Stale runs:** API startup resets `RUNNING` rows older than `AML_STALE_RUNNING_MINUTES`.
- **Timeouts:** Align `AML_A2A_TIMEOUT_SECONDS` with your slowest stage (Due Diligence).
