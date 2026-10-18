# Research: A2A streaming and push notifications for stage hosts

- **Date:** 2026-10-17
- **Question:** Should the Orchestrator → stage-host hop (`A2aAdapter` → `a2a/stage_app.py`, :8101–8104) move from blocking `message/send` to A2A streaming (SSE) and/or push notifications — and what does each take in this codebase?
- **Status:** Recommendation ready
- **Search tooling:** Fallback — WebSearch/WebFetch + direct reads of installed and upstream source. (Exa plugin was installed mid-session and its tools were not loaded; rerun with Exa in a fresh session if broader coverage is wanted.)

## TL;DR

- **Adopt streaming now (S–M effort).** It works on our current pins (a2a-sdk 0.3.26, google-adk 2.2.0), is a two-line flip on each side plus event handling, and fixes a real correctness gap: today a dropped connection loses the `task_id`, so the Orchestrator's retry **re-runs the whole stage** under the same `run_id` (duplicate tool-gateway writes, double Gemini cost).
- **Defer push notifications (L effort).** ADK's `to_a2a` never wires a `PushNotificationSender` — not in 2.2.0 and not on `main` (2.12.0) — so push needs a hand-built server, a webhook + JWT/JWKS verification + SSRF allowlist in the backend, and turning `trigger_agent` phase 3 into a webhook-driven step. Not justified while stage runs fit in the 600 s window.
- Use the stream for **live progress in the analyst console** (tool calls, A2UI parts) as ephemeral data — not as workflow state and not in the hash-chained audit trail.
- The a2a-sdk 1.x / ADK 2.12 upgrade is a **separate decision**; streaming does not depend on it.
- Biggest risk: the stage-host task store is in-memory and must stay that way (stage hosts get no DB creds), so a stage-host restart mid-run still fails the run — streaming narrows the blast radius, it doesn't remove it.

## Background

A2A defines three ways to follow a long-running task ([spec — Streaming & async](https://a2a-protocol.org/latest/topics/streaming-and-async/)):

| Mode | Mechanism | Card flag |
|---|---|---|
| Blocking request/response | `message/send` held open until terminal | — |
| **Streaming** | `message/stream` → `text/event-stream`; events are `Task`, `TaskStatusUpdateEvent`, `TaskArtifactUpdateEvent`; stream closes on terminal / `input-required`; reconnect with `tasks/resubscribe` (`SubscribeToTask` in 1.0) | `capabilities.streaming: true` |
| **Push** | Client registers `{url, token, authentication}`; server POSTs updates on significant state changes; client verifies, then calls `tasks/get` | `capabilities.pushNotifications: true` |

The spec says push servers **MUST** authenticate to the webhook, webhooks **MUST** verify (JWT/JWKS with `kid`, `jti`, `exp` recommended), and servers **SHOULD NOT** blindly trust webhook URLs (SSRF → allowlist / egress controls).

## Current state in this repo

- **Client** — `backend/aml/agents/adapters/a2a_client.py:84-89` builds `ClientConfig(streaming=False, polling=False)`. The SDK sends one blocking `message/send`; `send_turn` then falls back to polling `tasks/get` every 1 s (`_poll_task`) *only if* it already has a `task_id` and the task isn't terminal.
- **Server** — `backend/aml/agents/a2a/stage_app.py` calls `to_a2a(...)`. With A2UI off, `agent_card=None` → ADK 2.2.0's `AgentCardBuilder` uses `AgentCapabilities()` (no streaming). With A2UI on, `_build_agent_card` also uses the default capabilities. The a2a-sdk JSON-RPC handler rejects `message/stream` with *"Streaming is not supported by the agent"* when the flag is off (`a2a/server/request_handlers/jsonrpc_handler.py:125`), and the client silently degrades to non-streaming (`a2a/client/base_client.py:109`).
- **Executor already emits progress** — ADK's `A2aAgentExecutor` publishes a `TaskStatusUpdateEvent(state=working, final=False)` per ADK event and a final artifact + `final=True` status. We discard all of it today.
- **Orchestrator** — `orchestrator/service.py:387` `_execute_with_retry` → `_attempt` opens `self._db.transaction()` and awaits `port.execute(...)` inside it, so a Postgres transaction stays open for the full remote run (up to `AML_A2A_TIMEOUT_SECONDS=600`). On `A2aAdapterError`, `call_with_retry` re-runs the **entire** stage.
- **Self-heal retry** — `adapters/a2a.py` re-sends in the same `context_id` when no ```json block came back; must keep working.
- **UI** — `frontend/src/pages/CaseDetailPage.tsx:37` polls `GET /cases/{id}` every 3 s while any run is `RUNNING`; only status is visible. The aml-host chat (`frontend/src/lib/a2a.ts`) already speaks `message/stream` to :8100, which advertises `streaming=True` (`a2a/host_app.py:41`) — a working in-repo precedent.
- **Pins** — `requirements.txt`: `google-adk[a2a]>=0.2.0`, `a2a-sdk[http-server]>=0.3.4,<0.4`. Installed: google-adk 2.2.0 (its `a2a` extra caps `a2a-sdk<0.4`), a2a-sdk 0.3.26.

## Options compared

| Option | How it works | Fits ADK-native / Orchestrator rules? | Effort | Maturity | Notes |
|---|---|---|---|---|---|
| **A. Streaming (SSE)** | Card `streaming=True`; client `streaming=True`; consume events; capture `task_id` from first event; on disconnect `resubscribe` → fall back to `tasks/get` | Yes — still `to_a2a` + `A2aAgentExecutor`; Orchestrator remains sole writer | S–M | Spec-stable since 0.2; SDK 0.3 & 1.x; already used by aml-host | Enables live progress |
| **B. Push notifications** | Stage host POSTs to `POST /internal/a2a/webhooks/...` on terminal state; Orchestrator finishes phase 3 from the webhook | Partial — must bypass `to_a2a` to inject `push_sender` (still ADK executor); phase 3 becomes async, needs new idempotency path | L | SDK supports it; ADK does not wire it ([adk-python#4126](https://github.com/google/adk-python/issues/4126) only added config RPCs) | Needs JWT/JWKS, SSRF allowlist, durable task store |
| **C. Non-blocking send + poll** | `blocking=false` / `polling=True`; get `task_id` immediately; poll `tasks/get` | Yes | S | Stable | Fixes reattach, no fine-grained progress, 1 s latency floor |
| Do nothing | — | — | 0 | — | Keeps re-run-on-disconnect bug |

## Recommendation

**Option A**, keeping the existing `tasks/get` poll as the last-resort fallback (so A subsumes C). Explicitly **not** doing now: push notifications, a durable task store on stage hosts, or the a2a-sdk 1.x upgrade.

## Implementation plan

1. **Advertise streaming on stage hosts** — `backend/aml/agents/a2a/stage_app.py`: always build the card via `AgentCardBuilder(agent=..., rpc_url=..., capabilities=AgentCapabilities(streaming=True))` (not only when A2UI is on), then apply A2UI extensions when enabled. Mirror `host_app.py:41`.
2. **Stream from the client** — `backend/aml/agents/adapters/a2a_client.py`:
   - `ClientConfig(streaming=True, ...)` behind `AML_A2A_STREAMING` (default `true`; `false` restores today's behaviour).
   - In `send_turn`, record `task_id`/`context_id` from the **first** event; keep merging snapshots and A2UI parts as now (`_merge_task_snapshot`, `_merge_a2ui_messages` already handle `(Task, update)` tuples).
   - On `httpx` stream errors with a known non-terminal `task_id`: `client.resubscribe(TaskIdParams(id=task_id))` once, then `_poll_task`. Raise `A2aRemoteError` only if the task is truly gone/failed.
   - Add an optional `on_progress: Callable[[ProgressEvent], Awaitable[None]]` callback (tool call name, status text, A2UI part) — no DB writes in the client.
3. **Don't re-run on reattachable failures** — `adapters/a2a.py`: distinguish "remote task lost" (retryable → full re-run, current behaviour) from "connection dropped but reattached" (no re-run). Keep the JSON self-heal turn as is.
4. **Live progress to the UI (phase 2, optional)** — Orchestrator publishes `on_progress` events to an in-process per-run broadcaster; new `GET /cases/{id}/runs/{run_id}/events` SSE route; `CaseDetailPage` subscribes while `RUNNING` and keeps the 3 s poll as fallback. Ephemeral only — the final `output_payload`, evidence and audit events are still written in Txn 2.
5. **Shorten the held transaction (follow-up)** — consider building the prompt/gateway token in a short txn and awaiting `port.execute` outside it; evidence is already written via the tool-gateway endpoint in its own txns. Verify against `test_audit_host_parity.py` first.

**Runtimes affected:** in-process ☐ · A2A stage hosts ☑ · aml-host ☐ · `adk web` ☐ · Cloud Run ☑ (SSE within request timeout) · frontend/A2UI ☑ (phase 2)

**Config / infra:** `AML_A2A_STREAMING` (backend), no new services. Any reverse proxy in front of stage hosts must not buffer `text/event-stream` and needs idle timeout ≥ `AML_A2A_TIMEOUT_SECONDS`.

**Tests:**
- pytest (`tests/aml/test_a2a_adapter.py`, `test_a2a_client_*`): stream yields working→completed events and final JSON; mid-stream disconnect with known `task_id` → resubscribe succeeds, **no second `send_message`**; resubscribe fails → poll fallback; task lost → `A2aRemoteError` → orchestrator re-run; streaming disabled flag → old path; A2UI parts arriving as stream events are captured; self-heal turn still uses the same `context_id`.
- Stage app: card advertises `capabilities.streaming` with and without A2UI.
- ADK evals: none required (prompts/agents unchanged).
- Manual: `docker compose ... --profile a2a up`, seed `--preset services-swift`, trigger TE, `docker restart` nothing / then kill the backend↔stage connection (e.g. restart a proxy) mid-run and confirm one run, one set of evidence rows.

## Risks & compliance

- **Audit / sole writer:** unchanged if progress stays ephemeral. Do **not** append per-event audit rows (volume, and the chain should record decisions, not token streams).
- **Stage-host restart:** `InMemoryTaskStore` loses the task → run fails → full re-run. A `DatabaseTaskStore` would fix it but would hand stage hosts DB creds, violating the "remote agents get no DB creds" rule — keep in-memory unless a separate, non-case DB is approved.
- **Proxies / LB buffering** of SSE can stall events; Cloud Run supports SSE within the request timeout.
- **AML guardrails / PII:** progress events can contain tool arguments (party names, account refs). Send them only to authenticated analyst sessions for that case; never log full payloads.
- **Push later:** when revisited, follow the spec's JWT/JWKS + `jti` replay checks and allowlist the webhook host (a2a-sdk ≥1.1.4 adds URL validation/SSRF hardening; ≥1.2.0 sends `authentication` as an `Authorization` header).

## Open questions

- Do we want phase 2 (live progress in the console) in the same change, or ship the resilience fix first?
- Are stage runs ever expected to exceed ~10 min (e.g. large SWIFT batches)? If yes, push (Option B) moves up the list.
- When to schedule the ADK 2.12 / a2a-sdk 1.x upgrade? ADK's `_compat` layer supports both SDK lines, but a2a-sdk 1.x reworked `ClientConfig`/`ClientFactory`, and 1.2.0 rejects messages whose `contextId` disagrees with the task — re-test the JSON self-heal path then.

## Sources

1. [A2A — Streaming & Asynchronous Operations](https://a2a-protocol.org/latest/topics/streaming-and-async/) — a2a-protocol.org, accessed 2026-10-17, "latest" (1.0-era) — primary
2. [a2aproject/a2a-python releases](https://github.com/a2aproject/a2a-python/releases) — GitHub, v1.1.1–v1.2.2 (2026-07-16 → 2026-10-05) — primary
3. [google-adk on PyPI (JSON API)](https://pypi.org/pypi/google-adk/json) — latest 2.12.0 uploaded 2026-10-13; `a2a` extra `a2a-sdk[http-server]>=0.3.4,<2` — primary
4. [adk-python `agent_to_a2a.py` (main)](https://github.com/google/adk-python/blob/main/src/google/adk/a2a/utils/agent_to_a2a.py) and [`_compat.py`](https://github.com/google/adk-python/blob/main/src/google/adk/a2a/_compat.py) — no `push_sender` passed to `DefaultRequestHandler`; card builder defaults to `streaming=True` — primary (source), read 2026-10-17
5. Installed sources: `google/adk/a2a/utils/agent_to_a2a.py` (2.2.0), `a2a/server/request_handlers/{default,jsonrpc}_request_handler.py`, `a2a/client/{client,base_client}.py` (0.3.26) — primary
6. [adk-python#4126](https://github.com/google/adk-python/issues/4126) (closed 2026-01-12, push-config RPCs for `to_a2a`), [#5056](https://github.com/google/adk-python/issues/5056) / [#6274](https://github.com/google/adk-python/issues/6274) (a2a-sdk 1.x support) — primary
7. [A2A push notifications: what the spec guarantees and what it leaves to you](https://dev.to/nehigna/a2a-push-notifications-what-the-spec-guarantees-and-what-it-leaves-to-you-55i9) — DEV Community — secondary (pitfalls only)
