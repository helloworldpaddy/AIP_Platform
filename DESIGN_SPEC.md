# DESIGN_SPEC.md — AML Investigation Agents (ADK)

## Overview

A regulated Anti-Money-Laundering (AML) investigation platform that runs a
four-stage, human-in-the-loop (HITL) agent workflow over a single case. Each
stage is a Google ADK `LlmAgent` (Gemini + `FunctionTool`s). The same agent
definitions are served two ways from one source of truth:

- **`adk web`** — interactive single-agent debugging UI. Tools run in
  "standalone" mode and return safe stubs when no orchestrator/database context
  is bound.
- **FastAPI API** — the production analyst surface. The `Orchestrator` binds a
  per-case database context and drives each agent via
  `POST /cases/{case_id}/agents/{agent_name}/trigger`. Tools then perform real
  DB writes and provider calls. The React frontend (`AgentRunPanel`) calls this
  endpoint.

The agents live under `backend/aml/agents/stages/` so a single `adk web
backend/aml/agents/stages` command discovers all of them, and the orchestrator
imports the identical `root_agent` objects.

## Workflow stages

1. **Initial Assessment** (`initial_assessment`) — classifies the alert,
   forms a hypothesis, finds governing policy via `policy_rag_search`, records
   evidence.
2. **Transaction Enrichment** (`transaction_enrichment`) — hop-1/hop-2 graph
   traversal (`neo4j_hop_traversal`), records each counter-party
   (`record_party`) and link (`record_evidence`). Opens the `PARTIES_VERIFIED`
   gate so Due Diligence cannot start until an analyst verifies parties.
3. **Due Diligence** (`due_diligence`) — KYC (`kyc_lookup`) + external search
   (`external_search`) per party, per-party risk scoring. Aborts if any party
   is unverified.
4. **Case Analysis** (`case_analysis`) — final classification
   (FALSE_POSITIVE / ESCALATE / SAR) and the analyst-ready Markdown narrative;
   persists a draft narrative.

A supporting **`rag_agent`** (policy RAG over PostgreSQL/pgvector) is also
discoverable in `adk web`; it backs the `policy_rag_search` tool.

## Example use cases

- Analyst triggers Initial Assessment on a structuring alert → receives a risk
  band, hypothesis, investigation plan, and policy citations.
- Developer opens `adk web`, selects `due_diligence`, and exercises the
  prompt/JSON contract with stubbed KYC/search results (no DB required).

## Tools required

| Tool | Purpose | Real dependency | Standalone (adk web) |
|------|---------|-----------------|----------------------|
| `policy_rag_search` | Policy corpus retrieval | pgvector retrieval service | empty results stub |
| `kyc_lookup` | Internal KYC record | `KycProvider` | LOW-risk stub record |
| `neo4j_hop_traversal` | Graph hops | `GraphProvider` (Neo4j) | empty neighbors stub |
| `external_search` | Adverse media / sanctions | `SearchProvider` | single stub hit |
| `record_evidence` | Write to evidence ledger | `AgentToolContext` + repos | stub evidence_id |
| `record_party` | Upsert counter-party | `AgentToolContext` + repos | stub party_id |

Tools are **context-aware**: when an `AgentToolContext` is bound (orchestrator),
they perform real work; otherwise they return stubs so `adk web` keeps working.

## Constraints & safety rules

- Every factual claim in agent output JSON must be anchored to a recorded
  `evidence_id` (no fabricated identifiers).
- HITL is mandatory: every stage requires analyst review; party verification
  gates Due Diligence.
- PII (customer identifiers, KYC) is confidential; `contains_pii` is set on KYC
  evidence.
- Model is `gemini-2.5-flash` (from `config.yaml` / `GENERATION_MODEL`) and is
  not changed by this refactor.
- The frontend keeps using the orchestrator endpoint; ADK is never called
  directly from the browser.

## Success criteria

- `adk web backend/aml/agents/stages` lists all five agents and each chats
  end-to-end with stub tools (no DB).
- `POST /cases/{id}/agents/{name}/trigger` continues to run each stage against
  the real DB with unchanged request/response contracts.
- No duplicated agent definitions: each stage is defined once and reused by both
  surfaces.

## Deployment

- Target: **Cloud Run** (container), aligned with the existing Docker setup.
- CI/CD: none for now (prototype); can be added later via `agents-cli scaffold
  enhance`.
- A small ADK `get_fast_api_app` server (pointed at the stages directory)
  provides a deployable `adk web`-parity service; the analyst FastAPI app
  (`backend/aml/main.py`) remains the production surface.

## Reference samples

- `genmedia-for-commerce` — full-stack agent (React UI + FastAPI) with
  `fast_api_app.py`; closest match for serving ADK agents alongside a web UI.
