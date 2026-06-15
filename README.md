# AML Investigation Agentic Platform

An end-to-end, human-in-the-loop **Anti-Money Laundering (AML) investigation
system**. A coordinator runs four specialised LLM agents through a gated workflow —
initial assessment, transaction enrichment, due diligence, and case analysis —
and produces a citable, regulator-ready narrative for an analyst to review and
submit.

Built for **production-style orchestration** (gates, audit, idempotency) and
**modern agent deployment** (Google ADK, optional remote A2A stage hosts, A2UI
rich surfaces, conversational Agent Assistant with **Assistant** or **Standard**
workflow modes per case).

---

## Stack

| Layer | Technology |
|-------|------------|
| API | FastAPI + asyncpg |
| System of record | PostgreSQL 16 + pgvector (`aml.*` schema, policy RAG corpus) |
| Graph | Neo4j 5 (counterparty hops for Transaction Enrichment) |
| Agents | Google ADK + Gemini (`gemini-2.5-flash` default) |
| Orchestrator | In-process or **A2A** adapters per stage |
| Analyst UI | React + Vite + TypeScript + shadcn/ui |
| Agent chat | A2A → `aml-host` + A2UI v0.9 surfaces (stream + run artifacts) |
| Workflow UX | Per-case **Assistant** (chat + A2UI) or **Standard** (run panel) |
| Containers | Docker Compose (`docker/docker-compose.yml`) |

---

## Why this exists

Compliance investigators stitch evidence across KYC, transaction monitoring,
sanctions, and internal notes, then write narratives that survive regulator
scrutiny. This platform automates the stitching while keeping the analyst in
control: every agent output is reviewable, every state change is hash-chained in
the audit trail, and a submitted narrative locks the case.

---

## Architecture

### Control plane (always)

```text
React Console (localhost:8080)
    │ REST /api/*  +  X-Analyst-Id
    ▼
aml-backend (FastAPI + Orchestrator)
    • gates · agent_runs · audit · narratives
    • mint run-scoped tool-gateway tokens (A2A mode)
    ▼
InProcessAdapter  OR  A2aAdapter ──► remote stage hosts
    ▼
Postgres · Neo4j · policy RAG · external provider stubs
```

### Full A2A + Agent Assistant (recommended for demos)

```text
Browser
  ├─ Case UI Run/Approve ──► /api ──► Orchestrator ──► A2aAdapter
  │                                      └─► ia/te/dd/ca-agent (:8101–8104)
  │                                              └─ tool gateway ──► backend
  │
  └─ Agent Assistant chat ──► /a2a ──► aml-host (:8100)
                                    └─► Orchestrator tools (same audit path)
```

Remote stage agents **never** hold DB credentials. They call
`POST /internal/tool-gateway/runs/{run_id}/invoke` with a short-lived JWT.

Deep dive: [docs/AGENT_TRANSPORT.md](docs/AGENT_TRANSPORT.md) · [docs/A2UI.md](docs/A2UI.md)

---

## Workflow stages

| # | Stage | Agent | Gate / blocker |
|---|--------|--------|----------------|
| 1 | Triage | `INITIAL_ASSESSMENT` | — |
| 2 | Enrichment | `TRANSACTION_ENRICHMENT` | Opens `PARTIES_VERIFIED` |
| 3 | Party review | Analyst | Verify parties + approve gate |
| 4 | Diligence | `DUE_DILIGENCE` | Blocked until gate cleared |
| 5 | Synthesis | `CASE_ANALYSIS` | Draft narrative + classification |
| 6 | Submission | Analyst | Submit narrative → case locked |

Each agent run can require **Approve** (HITL) before the case advances.

---

## Quick start

### 1. Configure

```bash
cp docker/.env.example docker/.env
# Set GOOGLE_API_KEY (required on backend + all agent containers)
```

For **remote A2A + A2UI + Agent Assistant**, also use `docker/.env.a2a` (transport
URLs, tool gateway, A2UI flags — no secrets).

### 2. Start the full stack (A2A profile)

```bash
docker compose -f docker/docker-compose.yml \
  --env-file docker/.env \
  --env-file docker/.env.a2a \
  --profile a2a up --build
```

| Service | URL |
|---------|-----|
| **Frontend** (SPA + API proxy) | http://localhost:8080 |
| Backend API / OpenAPI (direct) | http://localhost:8000/docs |
| AML host (A2A chat) | http://localhost:8080/a2a/ → `aml-host:8100` |
| AML host agent card | http://localhost:8100/.well-known/agent-card.json |
| IA / TE / DD / CA stage cards | :8101 / :8102 / :8103 / :8104 |
| Neo4j Browser | http://localhost:7474 |

**In-process only** (no extra agent containers):

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env up --build
```

### 3. Seed a case

```bash
export POSTGRES_HOST=localhost POSTGRES_USER=raguser POSTGRES_PASSWORD=ragpass POSTGRES_DB=ragdb

python scripts/aml_seed.py --preset services-swift --skip-policies \
  --case-number "AML-SERVICES-SWIFT-$(date +%Y%m%d-%H%M%S)"
```

Or inside the backend container:

```bash
docker exec aml-backend python scripts/aml_seed.py --preset services-swift --skip-policies
```

**Seed presets:** `demo` · `mrp-goods` · `retail` · `cards` · `services-swift`
(Services LOB with SWIFT MT103/MT202 messages and ledger transactions).

### 4. Walk through in the UI

1. Open http://localhost:8080
2. Set **Analyst ID** (e.g. `analyst.demo`) in the top bar
3. Open your seeded case
4. **Choose workflow mode** (first visit per case):
   - **Assistant · Chat & A2UI** — conversational hub + interactive summary cards
   - **Standard · Run panel** — classic per-stage run JSON, reasoning, approve/reject
5. Toggle mode anytime from the case header (`Assistant` / `Standard`)
6. **Step progress** → **Run** each stage → **Approve** when `AWAITING_REVIEW`
7. For TE: verify parties in the sidebar → approve **PARTIES_VERIFIED** gate
8. Case Analysis → review narrative → submit

**Agent Assistant** (Assistant mode): chat to run stages, check state, or approve
runs. Chat text comes from `aml-host`; **Interactive summary** cards come from stage
A2UI artifacts (see below). Prefer **Approve** on the run panel or A2UI card for
HITL; approval is idempotent if you already approved in the other surface.

After config changes, recreate affected containers:

```bash
docker compose -f docker/docker-compose.yml \
  --env-file docker/.env --env-file docker/.env.a2a \
  --profile a2a up -d --force-recreate backend frontend ia-agent te-agent dd-agent ca-agent aml-host
```

---

## Documentation

| Doc | Contents |
|-----|----------|
| [docs/AGENT_TRANSPORT.md](docs/AGENT_TRANSPORT.md) | In-process vs A2A, tool gateway, circuit breaker, AML host, sprint map S1–S9 |
| [docs/A2UI.md](docs/A2UI.md) | A2UI on stage hosts, extension handshake, Agent Assistant renderer, testing |
| [tests/eval/README.md](tests/eval/README.md) | ADK evalsets per stage, rubric judge |

---

## Analyst workflow modes

Each case supports two investigation UX paths (stored in `localStorage`, with an
optional default):

| Mode | Main column | Best for |
|------|-------------|----------|
| **Assistant** | `AgentChatPanel` — A2A chat + A2UI interactive summaries | Conversational triage, approve from cards, layout switching |
| **Standard** | `AgentRunPanel` — curated run script (JSON, reasoning, HITL) | Audit review, full agent output, parity with REST triggers |

Shared in both modes: step progress, gates, parties, narrative editor, audit trail.

Implementation: `frontend/src/lib/case-workflow-mode.ts`,
`CaseWorkflowModePicker`, `CaseWorkflowModeSwitch`, `CaseDetailPage`.

---

## Agent Assistant & A2UI

### Chat transport

- **Panel:** `AgentChatPanel` on the case detail page (Assistant mode; enabled by default).
- **Transport:** Browser → nginx `/a2a/` → `aml-host:8100` (A2A JSON-RPC + SSE fallback).
- **Identity:** `X-Analyst-Id` header + `aml.analyst_id` in message metadata.
- **Mutations:** All workflow changes go through orchestrator tools on `aml-host` (same
  audit path as REST).

### Where interactive UI comes from

```text
Chat message ("run initial assessment")
  → aml-host.trigger_workflow_stage
  → Orchestrator → A2aAdapter → ia/te/dd/ca-agent
  → optional send_a2ui_json_to_client (application/json+a2ui)
  → output_payload.a2ui_messages + ```json final_text
  → GET /cases/{id} hydrates runs (salvage + surface rebuild)
  → AgentChatPanel: chat bubble (host text) + Interactive summary (A2UI card)
```

| Surface source | When |
|----------------|------|
| **Stream A2UI** | Responding agent emits `application/json+a2ui` on the wire (stage hosts; `aml-host` is text-only today) |
| **Run artifacts** | After each chat turn, case refetch loads `agent_runs[].output_payload.a2ui_messages` |
| **Client templates** | When stored A2UI is missing or stale, `a2ui-layouts.ts` builds cards from run data |
| **Salvage** | If JSON parse failed but reasoning lists parties / red flags, backend + frontend extract structured fields |

Orchestrator contract is unchanged: structured workflow output still comes from the
```json block in agent `final_text`. A2UI is an additive analyst surface.

### A2UI renderer (v0.9 BasicCatalog)

**Components:** Card, Text, Column, Row, Button, List, Tabs, Divider, Icon, Modal
(`A2uiSurface.tsx`). Unknown components degrade to JSON (non-fatal).

**Stage-aware templates** (`a2ui-layouts.ts`):

| Stage | Default interactive focus |
|-------|---------------------------|
| Initial Assessment | Summary / Red flags / Open questions / Actions tabs |
| Transaction Enrichment | Summary / Counterparties / Actions tabs |
| Due Diligence / Case Analysis | Generic analyst tabs + run fields |

**Summary layout picker** (Assistant mode, above chat): same run data, different
presentation — Analyst tabs, Executive brief, Detailed list, or Agent layout (stored
`a2ui_messages` when quality is good). Preference: `aml.a2ui_layout_preference` in
`localStorage`.

**Button actions** map to REST where possible (`a2ui-actions.ts`): `approve_run`,
`reject_run`, `run_stage`, `verify_party`, `resolve_gate`; unknown actions fall back
to a new chat turn.

### Enable A2UI (Compose)

Set on **backend** (hydration on `GET /cases/{id}`) and **stage agent** containers:

```bash
# docker/.env.a2a (typical)
AML_A2UI_ENABLED=true
AML_A2UI_STAGES=INITIAL_ASSESSMENT,TRANSACTION_ENRICHMENT,DUE_DILIGENCE,CASE_ANALYSIS
AML_AGENT_TRANSPORT_INITIAL_ASSESSMENT=a2a
AML_AGENT_TRANSPORT_TRANSACTION_ENRICHMENT=a2a
AML_AGENT_TRANSPORT_DUE_DILIGENCE=a2a
AML_AGENT_TRANSPORT_CASE_ANALYSIS=a2a
```

Rebuild after changing A2UI or transport env:

```bash
docker compose -f docker/docker-compose.yml \
  --env-file docker/.env --env-file docker/.env.a2a \
  --profile a2a build backend frontend ia-agent te-agent dd-agent ca-agent aml-host
docker compose -f docker/docker-compose.yml \
  --env-file docker/.env --env-file docker/.env.a2a \
  --profile a2a up -d --force-recreate backend frontend ia-agent te-agent dd-agent ca-agent aml-host
```

### Customize A2UI

| Layer | Location | Changes |
|-------|----------|---------|
| Agent-driven layout | `backend/aml/agents/a2a/a2ui.py` | Stage examples, `send_a2ui_json_to_client` hints |
| Server fallback surfaces | `build_run_surface_messages()` in `a2ui.py` | Deterministic cards when agent omits A2UI |
| Partial JSON salvage | `backend/aml/agents/a2a/summary_parse.py` | IA red flags, TE parties, inferred fields |
| Client templates | `frontend/src/lib/a2ui-layouts.ts` | Per-stage tabs and layout variants |
| Run → surface pipeline | `frontend/src/lib/a2ui-from-run.ts`, `a2ui-run-content.ts` | Extraction + layout build |

See [docs/A2UI.md](docs/A2UI.md) for extension handshake, testing, and resilience.

---

## AML host agent tools

Conversational front door (`aml-host`) — all mutations go through the orchestrator:

| Tool | Purpose |
|------|---------|
| `get_case_state` | Read-only progress, gates, parties |
| `trigger_workflow_stage` | Run IA / TE / DD / CA |
| `approve_awaiting_review_run` | Approve by case number (+ optional stage) |
| `approve_agent_run` | Approve by full run UUID (idempotent if already approved) |
| `reject_agent_run` | Reject with reason |
| `verify_case_party` | Mark party verified |
| `resolve_human_gate` | Approve / reject human gates |

---

## Project layout

```text
backend/aml/
  api/                 # FastAPI routes, dependencies, schemas
  agents/
    stages/            # Canonical ADK root_agent per workflow stage
    a2a/               # A2A stage hosts, aml-host, A2UI, summary_parse, sync_async
    adapters/          # InProcessAdapter, A2aAdapter (+ A2UI capture), resilience
    tool_gateway/      # Run-scoped JWT tool invoke HTTP API
    runtime/           # Hybrid ADK web callbacks, parity harness, run lifecycle
    tools/             # policy_rag, record_evidence, record_party, graph, KYC
  db/                  # schema.sql, repositories, state_loader (+ A2UI hydrate)
  orchestrator/        # Workflow engine (triggers, gates, retries, audit)
  models/              # Pydantic domain models + enums

agents/rag_agent/      # Policy ingestion + pgvector retrieval

frontend/src/
  pages/               # CasesPage, CaseDetailPage (+ workflow mode routing)
  components/          # AgentRunPanel, AgentChatPanel, A2uiSurface, A2uiLayoutSelector,
                       # CaseWorkflowModePicker/Switch, GatePanel, …
  lib/                 # api.ts, a2a.ts, a2ui-render.ts, a2ui-layouts.ts,
                       # a2ui-from-run.ts, a2ui-run-content.ts, a2ui-actions.ts,
                       # case-workflow-mode.ts, a2ui-layout-preference.ts, types

docker/
  docker-compose.yml   # postgres, neo4j, backend, frontend, profile a2a
  .env.example         # Secrets + Gemini
  .env.a2a             # A2A transport, gateway, A2UI overlay
  nginx.conf           # /api → backend, /a2a → aml-host

docs/
  AGENT_TRANSPORT.md
  A2UI.md

scripts/
  aml_seed.py          # Demo cases (retail, cards, services-swift, …)

tests/aml/             # Integration tests (stub agents, no LLM)
tests/eval/            # ADK evalsets + eval_config.json
```

---

## HTTP API (selected)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/cases` | Create case from alert |
| GET | `/cases/{id}` | Full investigation state |
| POST | `/cases/{id}/agents/{name}/trigger` | Trigger agent (idempotent) |
| POST | `/agents/runs/{id}/approve` | Approve pending run |
| POST | `/agents/runs/{id}/reject` | Reject run |
| POST | `/parties/{id}/verify` | Verify case party |
| POST | `/gates/{id}/resolve` | Resolve human gate |
| POST | `/narratives/{id}/submit` | Submit narrative (locks case) |
| GET | `/cases/{id}/audit` | Audit trail |
| GET | `/cases/{id}/audit/verify` | Verify hash chain |

All mutating endpoints require `X-Analyst-Id`.

---

## Configuration

Settings resolve through `agents/rag_agent/config/settings.py` (env overrides
`config.yaml`).

### Core

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_API_KEY` | — | **Required** for Gemini on backend + agent containers |
| `GENERATION_MODEL` | `gemini-2.5-flash` | Chat model for all agents |
| `EMBEDDING_MODEL` | `gemini-embedding-001` | Policy RAG embeddings |
| `POSTGRES_*` | see `docker/.env.example` | AML + RAG database |
| `NEO4J_URI` / `NEO4J_AUTH` | bolt://neo4j:7687 | Graph for TE hops |

### Agent transport ([details](docs/AGENT_TRANSPORT.md))

| Variable | Default | Description |
|----------|---------|-------------|
| `AML_AGENT_TRANSPORT_DEFAULT` | `in_process` | `in_process` or `a2a` |
| `AML_AGENT_TRANSPORT_<STAGE>` | — | Per-stage override (must set for full A2A in Compose) |
| `AML_A2A_<STAGE>_URL` | — | Agent card URL per stage |
| `AML_A2A_TIMEOUT_SECONDS` | `600` | Remote stage timeout |
| `AML_A2A_CIRCUIT_FAILURE_THRESHOLD` | `5` | Circuit breaker |
| `AML_TOOL_GATEWAY_BASE_URL` | `http://backend:8000` | URL stage agents use for tools |
| `AML_TOOL_GATEWAY_SECRET` | dev default | HMAC for gateway JWTs |
| `AML_ORCHESTRATOR_MAX_RETRY_ATTEMPTS` | `6` | Retries on transient LLM/503 errors |
| `AML_ORCHESTRATOR_RETRY_MAX_DELAY_SECONDS` | `45` | Max backoff between retries |

### A2UI ([details](docs/A2UI.md))

| Variable | Default | Description |
|----------|---------|-------------|
| `AML_A2UI_ENABLED` | `false` | Master switch (backend hydrate + stage hosts) |
| `AML_A2UI_STAGES` | `INITIAL_ASSESSMENT` | Comma-separated stage names |
| `AML_A2UI_VERSION` | `0.9` | A2UI extension / schema version |
| `VITE_A2A_BASE_URL` | `/a2a` | Frontend A2A proxy path (build-time) |
| `VITE_AML_AGENT_CHAT_ENABLED` | `true` | Hide Agent Assistant when `false` |

Local storage (browser, not env): `aml.case_workflow_mode.{caseId}`,
`aml.a2ui_layout_preference`, optional `aml.case_workflow_default_mode`.

---

## Testing

```bash
# Integration suite (Postgres required, stub agents — no LLM)
pytest tests/aml/ -q

# A2UI + A2A highlights
pytest tests/aml/test_a2ui.py tests/aml/test_a2ui_s9.py tests/aml/test_summary_parse.py -q
pytest tests/aml/test_a2a_adapter.py tests/aml/test_a2a_sync_async.py -q
pytest tests/aml/test_aml_host_agent.py tests/aml/test_audit_host_parity.py -q
```

ADK per-stage evaluation: [tests/eval/README.md](tests/eval/README.md)

---

## Google ADK (local dev)

```bash
export GOOGLE_API_KEY=...
export POSTGRES_HOST=localhost POSTGRES_USER=raguser POSTGRES_PASSWORD=ragpass POSTGRES_DB=ragdb

# Interactive stage picker
adk web backend/aml/agents/stages --port 8001

# Deployable ADK FastAPI app
uvicorn backend.aml.agents.fast_api_app:app --host 0.0.0.0 --port 8080
```

Hybrid ADK web callbacks persist runs to Postgres when you include a case number
in chat (see stage `agent.py` modules and `backend/aml/agents/runtime/`).

---

## Data model highlights

- **`audit_trail`** — append-only, hash-chained; `GET /audit/verify` detects tampering.
- **`agent_runs`** — unique on `(case_id, agent, idempotency_key)`; `FAILED` runs can be re-triggered with a new key.
- **`human_gates`** — e.g. `PARTIES_VERIFIED` blocks Due Diligence until resolved.
- **`narratives`** — submission sets `locked = TRUE` on the case (trigger-enforced).

DDL: [backend/aml/db/schema.sql](backend/aml/db/schema.sql)

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|----------------|-----|
| Run stuck `RUNNING` | Missing/invalid `GOOGLE_API_KEY` on backend or `*-agent` | Set key; recreate containers |
| `503 UNAVAILABLE` in agent error | Transient Gemini outage | Re-run stage; try `GENERATION_MODEL=gemini-2.0-flash` |
| `AML_A2A_*_URL is not set` | Backend not using `.env.a2a` | Add `--env-file docker/.env.a2a`; recreate `backend` |
| Workflow uses in-process despite `.env.a2a` | Compose injects per-stage `in_process` unless overridden | Set all `AML_AGENT_TRANSPORT_<STAGE>=a2a` in `.env.a2a` |
| Tool gateway errors in agent logs | Wrong `AML_TOOL_GATEWAY_BASE_URL` | Use `http://backend:8000` inside Docker |
| DD blocked | Parties / gate | Complete TE, verify parties, approve `PARTIES_VERIFIED` |
| Chat approve fails but UI shows approved | Duplicate approve on already-`APPROVED` run | Expected — use case state or idempotent approve tool |
| Malformed run ID in chat | LLM truncated UUID | Use full ID from run panel or `approve_awaiting_review_run` |
| No A2UI card after stage run | `AML_A2UI_ENABLED` off on backend/stage; in-process transport | Use `.env.a2a`, set all `AML_AGENT_TRANSPORT_*=a2a`, rebuild agents |
| Interactive summary shows “incomplete JSON” | Agent cut off before ```json block | Salvaged fields may still appear; re-run stage for full JSON or approve from Standard panel |
| TE card shows “risk band not assessed” | Old template / stale stored surface | Hard refresh; rebuild frontend; use Analyst layout (TE uses counterparties tabs) |
| Agent Assistant missing | `VITE_AML_AGENT_CHAT_ENABLED=false` or no `a2a` profile | Build with chat enabled; start `aml-host` + nginx `/a2a` proxy |

---

## Sprint delivery map (S1–S9)

| Sprint | Deliverable |
|--------|-------------|
| S1–S2 | Execution ports, in-process adapter, tool gateway |
| S3–S5 | A2A adapters, stage hosts, circuit breaker, parity harness |
| S6 | A2UI on stage hosts (orchestrator JSON unchanged) |
| S7 | AML host agent — orchestrator front door |
| S8 | React Agent Assistant + nginx `/a2a/` proxy |
| S9 | A2UI on all stages, audit parity tests, gateway hardening, docs |
| S9+ | Assistant vs Standard workflow modes, client A2UI templates + layout picker, IA/TE salvage for partial JSON, run hydration on case load |

Recent frontend/backend additions (post-S9): `CaseWorkflowModePicker`, stage-aware
`a2ui-layouts.ts`, `summary_parse.py` salvage, `hydrate_agent_run_payloads`, extended
`A2uiSurface` (List/Tabs/Modal/Icon), structured `a2ui-actions` for HITL buttons.

---

## License

MIT
