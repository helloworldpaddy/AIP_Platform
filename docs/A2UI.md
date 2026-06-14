# A2UI on AML A2A hosts (Sprint 6–9)

[A2UI](https://a2ui.org) lets stage agents emit structured UI alongside the
existing orchestrator ```json contract. The React **Agent Assistant** (Sprint 8)
renders basic v0.9 surfaces from `aml-host`; stage hosts emit A2UI when enabled.

## Architecture

```text
Browser Agent Assistant (/a2a → aml-host)
       │ orchestrator tools only
       ▼
Orchestrator.trigger_agent
       │ A2aAdapter (when transport=a2a)
       ▼
ia-agent / te-agent / dd-agent / ca-agent
       │ optional send_a2ui_json_to_client
       ▼
application/json+a2ui DataParts  +  ```json final_text (orchestrator)
```

The orchestrator **always** parses `final_text` for `output_payload`. A2UI is an
additive analyst surface; a validation failure in `send_a2ui_json_to_client`
returns an error dict to the LLM and does **not** fail the agent run.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `AML_A2UI_ENABLED` | `false` | Master switch |
| `AML_A2UI_STAGES` | `INITIAL_ASSESSMENT` | Comma-separated `AgentName` values |
| `AML_A2UI_VERSION` | `0.9` | Extension / schema version |

Sprint 9 enables all four workflow stages when A2UI is on:

```bash
AML_A2UI_ENABLED=true
AML_A2UI_STAGES=INITIAL_ASSESSMENT,TRANSACTION_ENRICHMENT,DUE_DILIGENCE,CASE_ANALYSIS
```

Compose (profile `a2a`):

```bash
AML_A2UI_ENABLED=true docker compose -f docker/docker-compose.yml \
  --env-file docker/.env --env-file docker/.env.a2a \
  --profile a2a up --build ia-agent te-agent dd-agent ca-agent aml-host frontend
```

## Per-stage UI focus (Sprint 9)

All stages use the **BasicCatalog** (`a2ui-basic-catalog-0.9.json`). Stage
hosts differ in prompt guidance and few-shot examples:

| Stage | A2UI surface emphasis |
|-------|------------------------|
| Initial Assessment | Risk band, hypothesis, open questions |
| Transaction Enrichment | Party table, graph hop summary |
| Due Diligence | Sanctions / KYC evidence with confidence |
| Case Analysis | Classification banner, narrative excerpt, citations |

Implementation: `backend/aml/agents/a2a/a2ui.py` (`_STAGE_A2UI_SUMMARY`,
`_te_a2ui_examples`, `_dd_a2ui_examples`, `_ca_a2ui_examples`).

## A2A extension handshake

1. Stage host advertises `capabilities.extensions` with
   `https://a2ui.org/a2a-extension/a2ui/v0.9` and `supportedCatalogIds`.
2. `aml-host` aggregates catalog ids from all configured stages for browser clients.
3. Browser sends `X-A2A-Extensions` and `a2uiClientCapabilities` in message metadata.
4. `A2uiEventConverter` emits `application/json+a2ui` parts on the wire.

Agent card check:

```bash
curl -s http://localhost:8101/.well-known/agent-card.json | jq '.capabilities.extensions'
```

## Action → tool mapping (Agent Assistant)

| User / A2UI action | Host tool | Orchestrator |
|--------------------|-----------|--------------|
| “run initial assessment” | `trigger_workflow_stage` | `trigger_agent(INITIAL_ASSESSMENT)` |
| “approve run …” | `approve_agent_run` | `approve_run` |
| “verify party …” | `verify_case_party` | party repo + audit |
| Button `action.name` in A2UI | `actionToUserMessage` → new host turn | same |

Mutations **never** bypass the orchestrator. Analyst identity is required via
`aml.analyst_id` in A2A metadata (`X-Analyst-Id` from the SPA).

## Frontend renderer (Sprint 8)

| File | Role |
|------|------|
| `frontend/src/lib/a2a.ts` | A2A client (SSE + fallback) |
| `frontend/src/lib/a2ui-render.ts` | Surface state reducer |
| `frontend/src/components/A2uiSurface.tsx` | Card, Text, Column, Row, Button |
| `frontend/src/components/AgentChatPanel.tsx` | Chat + surfaces |

Unknown A2UI components render as JSON (degraded, non-fatal).

## Testing

```bash
pytest tests/aml/test_a2ui.py tests/aml/test_a2ui_s9.py -q
pytest tests/aml/test_audit_host_parity.py -q
```

- **Schema:** `test_a2ui_s9.py` validates example payloads against the catalog validator.
- **Audit parity:** `test_audit_host_parity.py` asserts REST `trigger_agent` and
  host `trigger_workflow_stage` produce the same agent lifecycle audit events.

## Resilience

| Failure | Behaviour |
|---------|-----------|
| Invalid A2UI JSON from LLM | Tool returns `{a2ui_tool_error: ...}`; run continues |
| A2A stage errors | Orchestrator `A2aAdapter` + circuit breaker (Sprint 5) |
| Invalid tool args on gateway | HTTP 200 with `{error: ...}` (Sprint 9 hardening) |
| Renderer unknown component | JSON fallback in `A2uiSurface` |

## Version pinning

- `a2ui-agent-sdk` pinned in `requirements.txt` (`<1.0` pre-GA)
- Isolate A2UI logic in `backend/aml/agents/a2a/a2ui.py` + frontend `a2ui-render.ts`
