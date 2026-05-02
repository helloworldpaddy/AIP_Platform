# AML Investigation Agentic Platform

An end-to-end, human-in-the-loop **Anti-Money Laundering (AML) case investigation
system**. A coordinator runs four specialised LLM-driven agents through a
gated workflow — initial assessment, transaction enrichment, due diligence,
and case analysis — and produces a citable, regulator-ready narrative for an
analyst to review and submit.

The platform is built on:

- **FastAPI + asyncpg** — backend HTTP surface and connection pool
- **PostgreSQL 16 + pgvector** — system of record for cases, evidence, audit
  trail, parties, narratives, and the policy/RAG corpus
- **Neo4j 5** — counterparty graph (transactions, ownership, relationships)
- **Google Gemini** — agent reasoning + function-calling, plus
  `text-embedding-004` for the policy RAG layer
- **React + Vite + TypeScript** — analyst console (case detail, gates,
  narrative editor, audit trail)
- **Pydantic v2** for strict domain modelling, **Alembic-style** raw SQL
  schema with hash-chained immutable audit log

---

## Why this exists

Compliance investigators spend most of their time stitching together evidence
across siloed systems (KYC, transaction monitoring, sanctions, news,
internal notes) and writing narratives that survive regulator scrutiny. This
platform automates the stitching while keeping the analyst firmly in
control: every agent output is reviewable, every state change is audited,
and a submitted narrative locks the case to preserve the evidentiary chain.

---

## Architecture

```
                       ┌────────────────────────────────────────┐
                       │            React Console               │
                       │   (cases · gates · narrative editor)   │
                       └────────────────┬───────────────────────┘
                                        │ REST + X-Analyst-Id
                       ┌────────────────▼───────────────────────┐
                       │           FastAPI surface              │
                       │  /cases /agents /gates /narratives ... │
                       └────────────────┬───────────────────────┘
                                        │
                       ┌────────────────▼───────────────────────┐
                       │            Orchestrator                │
                       │  • idempotent agent triggers           │
                       │  • gate-blocking (HITL)                │
                       │  • retry + audit on every mutation     │
                       └─┬─────────────┬─────────────────┬──────┘
                         │             │                 │
            ┌────────────▼──┐  ┌───────▼────────┐  ┌─────▼──────────┐
            │  Initial      │  │ Transaction    │  │ Due Diligence  │
            │  Assessment   │  │ Enrichment     │  │  + Case        │
            │   (Gemini)    │  │  (Gemini)      │  │  Analysis      │
            └────────┬──────┘  └───────┬────────┘  └─────┬──────────┘
                     │                 │                 │
              ┌──────▼─────────────────▼─────────────────▼──────┐
              │              Tool layer (provider                │
              │              protocols, swappable)               │
              │  policy_rag · kyc_lookup · graph_hop · search    │
              └──────┬─────────────┬───────────────┬─────────────┘
                     │             │               │
             ┌───────▼───┐  ┌──────▼─────┐  ┌──────▼──────┐
             │ Postgres  │  │  Neo4j     │  │  External   │
             │ pgvector  │  │  graph     │  │  APIs       │
             │ + AML     │  │            │  │  (KYC, web) │
             │  schema   │  │            │  │             │
             └───────────┘  └────────────┘  └─────────────┘
```

### Workflow stages

A case moves through the following stages, each gated for analyst review:

1. **Triage** — `INITIAL_ASSESSMENT` agent reads the alert payload, retrieves
   relevant policy via RAG, classifies severity, and lists open questions.
2. **Enrichment** — `TRANSACTION_ENRICHMENT` agent walks the counterparty
   graph (Neo4j), records all involved parties, and **opens a
   `PARTIES_VERIFIED` gate** that blocks downstream work until the analyst
   approves each party.
3. **Diligence** — `DUE_DILIGENCE` agent (only runnable once parties are
   verified) performs KYC + sanctions + adverse-media checks and records
   evidence with confidence scores.
4. **Synthesis** — `CASE_ANALYSIS` agent drafts a Markdown narrative with
   numbered citations into the evidence ledger and a final classification
   (`SAR_FILED`, `FALSE_POSITIVE`, `ESCALATE`, etc.).
5. **Submission** — analyst reviews the narrative, edits if needed, and
   submits. Submission flips `submitted = TRUE` and `locked = TRUE`; a
   Postgres trigger then blocks all further mutations on the case.

---

## Project layout

```
backend/aml/
    api/
        app.py                  # FastAPI factory + lifespan
        dependencies.py         # get_db, get_orchestrator, current_analyst
        routes/
            cases.py            # POST/GET /cases
            agents.py           # trigger / approve / reject runs
            gates.py            # resolve human gates
            narratives.py       # draft / submit
            parties.py          # verify parties
            audit.py            # GET /cases/{id}/audit, /audit/verify
        schemas.py              # request/response Pydantic models
        errors.py               # exception → HTTP mappers
    agents/
        base.py                 # AgentResult, BaseAgent contract
        llm_agent_base.py       # Gemini function-calling mixin
        gemini_runner.py        # tool dispatch loop + reasoning log
        registry.py             # production agent factory
        prompts.py              # system prompts + JSON output schemas
        initial_assessment.py
        transaction_enrichment.py
        due_diligence.py
        case_analysis.py
        tools/
            policy_tool.py      # policy_rag_search (live, pgvector)
            data_tools.py       # kyc / graph / search PROTOCOLS (stub by default)
            evidence_tool.py    # record_evidence
    db/
        client.py               # asyncpg pool + connection-scoped repositories
        schema.sql              # 11-table AML schema with triggers
        repositories/           # cases, agent_runs, evidence, parties,
                                # gates, narratives, audit
    models/
        enums.py                # mirrors Postgres ENUMs
        state.py                # Case, AgentRun, Evidence, Narrative, ...
    orchestrator/
        service.py              # workflow engine: triggers, gates, retries
    main.py                     # uvicorn entrypoint

agents/rag_agent/               # policy retrieval substrate
    services/                   # ingestion / retrieval / embedding
    tools/                      # vector_search_tool (called by AML agents)
    db/                         # pgvector schema + asyncpg client
    config/settings.py          # shared config (DB, Gemini, embeddings)

frontend/src/
    pages/                      # CasesPage, CaseDetailPage
    components/                 # AgentRunPanel, GatePanel, PartiesPanel,
                                # NarrativeEditor, AuditTrail, StepProgress, ...
    lib/                        # API client, queries, types

docker/
    docker-compose.yml          # postgres + neo4j + backend + frontend
    Dockerfile.backend
    Dockerfile.frontend
    init-db/                    # 01-rag-schema.sh, 02-aml-schema.sh
    init-neo4j/01-constraints.cypher
    nginx.conf

scripts/
    aml_seed.py                 # seed AML-DEMO-2026-001 + sample policies
    setup_db.py / ingest.py / query.py   # RAG corpus tools

tests/aml/
    conftest.py                 # session-scoped schema reset + asyncpg pool
    stubs.py                    # deterministic stub agents (no LLM)
    test_orchestrator_walkthrough.py
    test_api_walkthrough.py
```

---

## Quickstart

### Option A (fastest): run the full app via Docker

```bash
cp docker/.env.example docker/.env       # edit credentials + GEMINI_API_KEY as needed
docker compose -f docker/docker-compose.yml up -d --build
```

Then open:

- Frontend: `http://localhost:5173`
- Backend docs: `http://localhost:8000/docs`
- Neo4j Browser: `http://localhost:7474`

### Option B (dev): run infra in Docker + backend/frontend locally

### 1. Boot infrastructure (Postgres + Neo4j)

```bash
cp docker/.env.example docker/.env       # edit credentials as needed
docker compose -f docker/docker-compose.yml up -d postgres neo4j
```

This starts:

- Postgres 16 with `pgvector` on `localhost:5432` (DB `ragdb`)
- Neo4j 5 on `localhost:7474` (browser) and `bolt://localhost:7687`

The `init-db/` scripts apply both the RAG schema (`agents/rag_agent/db/schema.sql`)
and the AML schema (`backend/aml/db/schema.sql`) on first boot.

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure secrets

Add a `.env` (or set in your shell) with at minimum:

```
GEMINI_API_KEY=...
POSTGRES_HOST=localhost
POSTGRES_USER=raguser
POSTGRES_PASSWORD=ragpass
POSTGRES_DB=ragdb
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=...
```

All settings resolve through `agents/rag_agent/config/settings.py` (Pydantic
settings — env vars override `config.yaml`).

### 4. Seed a demo case

```bash
python scripts/aml_seed.py
# → Seeded case_id=... (case_number=AML-DEMO-2026-001)
```

Pass `--skip-policies` to skip ingesting `data/samples/` into the RAG store.

### 5. Run the backend

```bash
uvicorn backend.aml.main:app --reload --port 8000
```

OpenAPI docs at `http://localhost:8000/docs`.

### 6. Run the frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

The console expects an analyst id; pick one from the bar at the top
(default fixtures: `analyst.demo`, `analyst.test`).

---

## HTTP API (selected endpoints)

| Method | Path                                       | Purpose                                  |
|--------|--------------------------------------------|------------------------------------------|
| POST   | `/cases`                                   | Create a case from an alert payload      |
| GET    | `/cases?status=...&analyst=...`            | List cases with filters                  |
| GET    | `/cases/{id}`                              | Full state aggregate (case + runs +      |
|        |                                            | parties + gates + evidence + audit head) |
| POST   | `/cases/{id}/agents/{name}/trigger`        | Trigger an agent (idempotent)            |
| POST   | `/agents/runs/{id}/approve`                | Analyst approves a pending run           |
| POST   | `/agents/runs/{id}/reject`                 | Analyst rejects (with reason)            |
| GET    | `/cases/{id}/parties`                      | List parties involved in the case        |
| POST   | `/parties/{id}/verify`                     | Mark a party as KYC-verified             |
| POST   | `/gates/{id}/resolve`                      | Resolve a human gate (APPROVED / REJECTED)|
| POST   | `/narratives/{id}/submit`                  | Submit narrative — locks the case        |
| GET    | `/cases/{id}/audit`                        | Read the audit trail                     |
| GET    | `/cases/{id}/audit/verify`                 | Verify the hash chain integrity          |

All mutating endpoints require an `X-Analyst-Id` header.

---

## Data model highlights

- **`audit_trail`** is append-only and **hash-chained**: each row stores
  `prev_hash` + `entry_hash = sha256(prev_hash || canonical(payload))`. A
  trigger blocks `UPDATE` / `DELETE` / `TRUNCATE`, and `GET /audit/verify`
  walks the chain to detect tampering.
- **`narratives`** are versioned per-case. `submitted = TRUE` flips
  `locked = TRUE`; a `narrative_lock_guard` trigger then refuses any further
  writes — the submitted artefact is preserved verbatim.
- **`agent_runs`** uses `(case_id, agent, idempotency_key)` as a UNIQUE key,
  so re-triggering a run with the same key returns the existing row instead
  of duplicating work.
- **`evidence_ledger`** dedups by `(case_id, source_system, source_uri,
  content_hash)`; agents can safely re-record the same fact.
- **`human_gates`** open programmatically when an agent emits a `GateSpec`
  (e.g. `PARTIES_VERIFIED` blocks `DUE_DILIGENCE` until resolved).

See [backend/aml/db/schema.sql](backend/aml/db/schema.sql) for the full DDL.

---

## RAG / policy retrieval substrate

The `agents/rag_agent/` package is the policy-retrieval foundation: it
ingests documents (PDF/DOCX/TXT) into a `documents` table with a `vector(768)`
column, and exposes a `vector_search_tool` (hybrid BM25 + cosine) that the
AML agents call via `policy_rag_search`. Features:

- Token-aware chunking with overlap
- Gemini `text-embedding-004` (batched, async)
- pgvector IVFFlat index, optional Redis cache, optional LLM reranking
- AML-specific entity extraction + risk-vocabulary query expansion
- Optional OpenTelemetry tracing on ingest / embed / retrieve / generate

```bash
python scripts/ingest.py --path data/samples/         # bulk ingest
python scripts/query.py "structuring red flags"       # one-off CLI query
```

---

## Testing

```bash
# Full integration walkthrough against a real Postgres (uses stub agents
# from tests/aml/stubs.py — no LLM required)
pytest tests/aml -v

# RAG / unit tests
pytest tests/ -v
pytest tests/test_integration.py -v -m integration
```

The AML suite resets the `aml` schema once per session via a sync psycopg
connection, then each test mints a unique `case_number`. The asyncpg pool is
function-scoped so it's always bound to the test's event loop. See
[tests/aml/conftest.py](tests/aml/conftest.py).

Coverage today:

- ✅ End-to-end orchestrator walkthrough (4 agents, gates, lock, audit)
- ✅ End-to-end FastAPI walkthrough (same flow over HTTP)
- ✅ Idempotent re-triggers
- ✅ Locked-case mutation rejection
- ✅ Audit-chain integrity verification
- 🟡 Per-repository unit tests (planned)
- 🟡 Tool-dispatch / Gemini runner unit tests (planned)

---

## Configuration reference

All settings resolve through `agents/rag_agent/config/settings.py`. Env
vars override `config.yaml`.

| Setting                | Default              | Description                          |
|------------------------|----------------------|--------------------------------------|
| `embedding_model`      | `text-embedding-004` | Gemini embedding model               |
| `generation_model`     | `gemini-2.0-flash`   | Gemini chat model                    |
| `embedding_dim`        | `768`                | Must match the embedding model       |
| `chunk_size`           | `800`                | Tokens per chunk                     |
| `chunk_overlap`        | `100`                | Overlap tokens                       |
| `top_k`                | `5`                  | Retrieved chunks per query           |
| `hybrid_search`        | `true`               | Combine BM25 + vector                |
| `database.pool_min`    | `1`                  | asyncpg pool min connections         |
| `database.pool_max`    | `10`                 | asyncpg pool max connections         |
| `database.statement_timeout_ms` | `30000`     | Per-statement timeout                |
| `cache_enabled`        | `false`              | Redis query/embedding cache          |

---

## Roadmap

- [ ] Wire concrete provider clients for KYC, Neo4j graph queries, and web
      search (today's protocols raise `NotImplementedError` unless stubbed).
- [ ] OpenTelemetry on FastAPI + asyncpg + Gemini calls (with trace_id /
      span_id propagated into the audit trail).
- [ ] Per-repository and per-tool unit tests.
- [ ] SAR / STR export adapters (FinCEN XML, goAML).
- [ ] Role-based access control beyond the current `X-Analyst-Id` header.
- [ ] Streaming narrative generation in the analyst console.

---

## Operational notes

- **Audit immutability** is enforced at the database level. Per-test
  `DELETE` / `TRUNCATE` will fail by design — local test cleanup uses
  `DROP SCHEMA aml CASCADE` and a re-apply.
- **Submission is irreversible.** Once `submitted = TRUE`, a trigger blocks
  all further writes on the narrative and on the case row. To "amend", the
  workflow is: open a new case (or new narrative version *before* submission).
- **Idempotency keys** should be supplied by the caller for
  `POST /cases/{id}/agents/{name}/trigger` if you want safe retries; the
  orchestrator generates one if omitted, but supplying your own (e.g. an
  alert id) lets you de-dupe across restarts.

---

## License

MIT
