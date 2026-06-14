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
| `AML_A2UI_ENABLED` | `false` | Enable A2UI on A2A stage hosts (Sprint 6+) |
| `AML_A2UI_STAGES` | `INITIAL_ASSESSMENT` | Comma-separated stages that emit A2UI |
| `AML_A2UI_VERSION` | `0.9` | A2UI extension / schema version |

## A2UI (Sprint 6–9)

When `AML_A2UI_ENABLED=true`, configured stage A2A hosts (`ia-agent`, `te-agent`,
`dd-agent`, `ca-agent`) advertise the [A2UI A2A extension](https://a2ui.org) on
their agent cards and may call `send_a2ui_json_to_client` to emit
`application/json+a2ui` DataParts. Set `AML_A2UI_STAGES` to enable all four
workflow stages (see [A2UI.md](A2UI.md)). The orchestrator path is unchanged:
`A2aAdapter` still parses the ```json block from `final_text` for `output_payload`.

Enable in compose (all stage agents + aml-host):

```bash
AML_A2UI_ENABLED=true docker compose -f docker/docker-compose.yml \
  --env-file docker/.env --env-file docker/.env.a2a \
  --profile a2a up --build ia-agent te-agent dd-agent ca-agent aml-host frontend
```

Verify the agent card:

```bash
curl -s http://localhost:8101/.well-known/agent-card.json | jq '.capabilities.extensions'
```

A React A2UI panel (Sprint 8) will consume these parts; for manual smoke tests use
the Lit renderer from the A2UI project against `:8101`.

## AML host agent (Sprint 7)

The **AML host agent** (`aml-host:8100`) is the A2A front door for conversational
clients (React Agent Assistant in Sprint 8). It exposes deterministic tools that
call the production orchestrator — never stage agents directly:

| Tool | Orchestrator / DB action |
|------|--------------------------|
| `get_case_state` | Read-only investigation summary |
| `trigger_workflow_stage` | `Orchestrator.trigger_agent` |
| `approve_agent_run` / `reject_agent_run` | HITL on agent runs |
| `resolve_human_gate` | Gate resolution |
| `verify_case_party` | Party verification + audit |

**Analyst identity** is required on every tool call. Browsers send it in A2A
message metadata:

```json
{"aml": {"analyst_id": "analyst.jane"}}
```

Helper: `build_host_client_metadata(analyst_id=...)` in `backend/aml/agents/a2a/metadata.py`.

With compose profile `a2a`, the host starts alongside stage agents:

```bash
curl -s http://localhost:8100/.well-known/agent-card.json | jq '.name, .url'
```

When `AML_A2UI_ENABLED=true`, the host agent card aggregates `supportedCatalogIds`
from all configured stage catalogs (orchestrator-aggregation pattern for Sprint 8).

## React Agent Assistant (Sprint 8)

The case detail page includes an **Agent Assistant** panel that talks to
`aml-host` via nginx (`/a2a/` → `:8100`). It streams A2A responses and renders
basic A2UI v0.9 surfaces (Card, Text, Button, Column, Row).

| Env (frontend build) | Default | Purpose |
|----------------------|---------|---------|
| `VITE_A2A_BASE_URL` | `/a2a` | A2A proxy path (same origin) |
| `VITE_AML_AGENT_CHAT_ENABLED` | `true` | Hide panel when `false` |

Analyst identity is forwarded as `X-Analyst-Id` and in message metadata
(`aml.analyst_id`). After each host turn completes, the panel invalidates the
case React Query so `AgentRunPanel` stays in sync.

Local dev (`npm run dev` in `frontend/`): proxy `/a2a` → `localhost:8100`; start
`aml-host` with compose profile `a2a`.

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
| S6 | A2UI on IA A2A host (PoC backend; orchestrator JSON unchanged) |
| S7 | AML host agent (`aml-host:8100`) — A2A front door to orchestrator |
| S8 | React Agent Assistant panel + nginx `/a2a/` proxy + A2UI renderer |
| S9 | A2UI on all stages, audit host parity test, `docs/A2UI.md`, gateway arg hardening |

See [A2UI.md](A2UI.md) for catalogs, extension handshake, and action mapping.

## Production hardening notes

- **Retries:** Orchestrator Phase 2 uses `call_with_retry` for transient LLM/provider errors.
- **Circuit breaker:** A2A adapter opens after `AML_A2A_CIRCUIT_FAILURE_THRESHOLD` consecutive failures; fast-fails until recovery window elapses.
- **Stale runs:** API startup resets `RUNNING` rows older than `AML_STALE_RUNNING_MINUTES`.
- **Timeouts:** Align `AML_A2A_TIMEOUT_SECONDS` with your slowest stage (Due Diligence).
