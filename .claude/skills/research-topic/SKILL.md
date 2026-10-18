---
name: research-topic
description: Research a new technology, library, pattern, standard or regulation on the internet (via Exa) and turn it into an implementation-ready brief for THIS AML platform — how it works, options compared, how it fits the ADK/Orchestrator/A2A/A2UI architecture, files to touch, test plan and risks. Use when the user says "research X", "look into X before we build it", "how should we add X", "is X a good fit", "what's the latest on X", or wants to evaluate something before implementing it. Does not change code.
argument-hint: <topic or question to research>
allowed-tools: mcp__plugin_exa_exa__web_search_exa, mcp__plugin_exa_exa__web_fetch_exa, mcp__plugin_exa_exa__web_search_advanced_exa, mcp__plugin_exa_exa__agent_run, WebSearch, WebFetch, Read, Grep, Glob, Write
---

# Research a topic before implementing it

Topic: **$ARGUMENTS**

Goal: give the user a decision-ready brief so they can go straight to implementation in this repo. The deliverable is a Markdown file in `docs/research/` plus a short chat summary. **Do not edit application code** in this skill — implementation is a separate, follow-up step the user triggers.

## 0. Frame the question

- If `$ARGUMENTS` is empty or too vague to search (e.g. "agents"), ask **one** clarifying question, then proceed.
- Restate the question as: *what* we want to learn, *why* (the feature/problem in this project), and *what decision* the brief must support.
- Note today's date from the environment; convert any "recent / latest / this year" into explicit dates. Prefer sources from the last 12 months for fast-moving topics (ADK, A2A, A2UI, Gemini, MCP).

## 1. Ground in the codebase first

Read just enough to know where the topic would land:

- `CLAUDE.md` (architecture, invariants, conventions) — always.
- Grep for existing usage of the topic, related names, or the subsystem it touches. Typical landing zones:
  - Stage agents / prompts: `backend/aml/agents/stages/`, `backend/aml/agents/prompts.py`, `backend/aml/agents/adk_runner.py`
  - Orchestration & gates: `backend/aml/orchestrator/` (`service.py`, `transitions.py`)
  - Transport / A2A / tool gateway: `backend/aml/agents/adapters/`, `backend/aml/agents/a2a/`, `backend/aml/agents/tool_gateway/`
  - Tools: `backend/aml/agents/tools/context_aware.py`
  - Data: `backend/aml/db/schema.sql`, `backend/aml/db/repositories/`, Neo4j access
  - UI / A2UI: `frontend/src/`, `docs/A2UI.md`
  - Deploy: `docker/`, `backend/aml/agents/fast_api_app.py`
- Check pinned versions (`pyproject.toml`, `requirements.txt`, `frontend/package.json`) so research targets the versions we actually run — and flags upgrades if needed.

Record: current state, the exact files/functions the change would touch, and constraints that apply.

## 2. Research externally with Exa

Use the Exa MCP tools (from the `exa` plugin):

| Tool | Use for |
|---|---|
| `web_search_exa` | Finding sources. Write natural-language, descriptive queries ("official Google ADK documentation for ParallelAgent with callbacks"), not keyword soup. Run several angles in parallel: official docs, GitHub repo/issues, release notes/changelog, spec, real-world implementation write-ups, known pitfalls. |
| `web_fetch_exa` | Reading the actual pages you will cite. Never cite a page you have only seen as a search snippet. |
| `web_search_advanced_exa` | Date/domain-filtered searches (e.g. only `google.github.io`, `github.com`, `a2a-protocol.org`, last 6 months) — if enabled. |
| `agent_run` | Broad multi-hop surveys (e.g. "compare every maintained X library with Y support") — only if authenticated; otherwise do it with parallel searches. |

Rules:
- **Primary sources first**: official docs, specs, source code, maintainers' release notes. Use blogs/forums only to surface pitfalls, and label them as such.
- Capture **version numbers and publish/updated dates** for every claim that could go stale.
- When sources conflict, say so and prefer the newer primary source; verify in source code if it matters.
- For broad topics with independent sub-questions, you may fan out to 2–4 `general-purpose` subagents (one per sub-question) and have each return findings + URLs; keep only their conclusions in context.
- **If Exa fails** (auth/rate limit): tell the user the fix (run `/mcp` → exa → authenticate, or set an API key), then continue with `WebSearch` / `WebFetch` and mention the fallback in the brief.
- **Never put case data in queries.** No customer names, case numbers, account/transaction identifiers or analyst notes in any external search — research the *technique*, not our data.

## 3. Evaluate fit against this project

Judge every option against the project's non-negotiables (from `CLAUDE.md`):

- **Google ADK-native**: `LlmAgent` + ADK workflow agents (`SequentialAgent`/`ParallelAgent`/`LoopAgent`) over custom orchestration. **No LangChain, CrewAI or AutoGen** — reject options that require them, or show the ADK-native equivalent.
- **Orchestrator is the only writer of workflow state**; every mutation goes through `Orchestrator.trigger_agent` so the hash-chained `audit_trail` stays consistent. Append-only audit, locked cases, `human_gates`.
- **One agent definition, several runtimes** (in-process, A2A stage hosts, `adk web`, Cloud Run) — will the change work in all of them?
- **Remote agents get no DB creds** — tool access only via the run-scoped JWT tool gateway and `ADK_TOOLS`.
- **Output contract**: `Reasoning:` + one fenced ```json block; A2UI is additive only.
- **AML guardrails**: no findings without evidence; never conclude adverse matches on name alone; data residency/PII and regulator auditability.
- Typed, JSON-serializable function tools; Session State / Memory / Artifacts used as the conventions describe.
- Operational cost: Gemini tokens/latency, new infra in `docker-compose`, licensing, maintenance health (last release, open issues).

## 4. Write the brief

Save to `docs/research/<YYYY-MM-DD>-<kebab-slug>.md` (create the folder if missing) using `brief-template.md` in this skill directory. Keep it tight — aim for something the user can read in 5 minutes; put depth in the appendix.

## 5. Report back

In chat, give: the recommendation in 2–3 sentences, the top risks, the path to the brief, and the suggested first implementation step. Then ask whether to proceed with implementation (which should follow the brief's plan and add pytest tests under `tests/aml/` and ADK eval cases under `tests/eval/evalsets/` for agent changes).
