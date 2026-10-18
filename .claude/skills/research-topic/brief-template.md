# Research: <Topic>

- **Date:** YYYY-MM-DD
- **Question:** <what we wanted to learn and the decision it supports>
- **Status:** Recommendation ready | Needs decision | Not a fit
- **Search tooling:** Exa (`web_search_exa` / `web_fetch_exa`) | fallback: WebSearch

## TL;DR

<3–5 bullets: what it is, the recommendation, effort estimate (S/M/L), biggest risk.>

## Background

<What the technology/pattern is and how it works — only what is needed to make the decision. Note the version researched.>

## Current state in this repo

<What exists today, with `path/to/file.py:line` references. Pinned versions that matter.>

## Options compared

| Option | How it works | Fits ADK-native / Orchestrator rules? | Effort | Maturity (last release, adoption) | Notes |
|---|---|---|---|---|---|
| A | | | | | |
| B | | | | | |
| Do nothing | | | | | |

## Recommendation

<Chosen option and why. What we explicitly will NOT do.>

## Implementation plan

1. <Step — files to touch (`backend/aml/...`), what changes>
2. ...

**Runtimes affected:** in-process ☐ · A2A stage hosts ☐ · aml-host ☐ · `adk web` ☐ · Cloud Run ☐ · frontend/A2UI ☐

**Config / infra:** <new env vars, settings.py/config.yaml keys, docker-compose services, dependencies to add>

**Tests:**
- pytest: <new/changed tests under `tests/aml/`, using `tests/aml/stubs.py` stubs>
- ADK evals: <cases to add under `tests/eval/evalsets/`>
- Manual: <seed preset + steps to verify in the analyst console>

## Risks & compliance

- <Audit trail / Orchestrator-only-writer impact>
- <AML guardrails: evidence requirements, name-only matching, PII/data residency>
- <Cost, latency, vendor lock-in, maintenance>

## Open questions

- <Things the user must decide or that need a spike>

## Sources

1. [Title](url) — publisher, published/updated YYYY-MM-DD, version X — primary | secondary
2. ...
