"""Agent run repository.

Implements the idempotency + resumability contract from spec §3.C:

    `get_or_create_run(...)` is the entry point a trigger calls.  If a row
    already exists for `(case_id, agent, idempotency_key)`, it is returned
    untouched — the orchestrator inspects its `status` and either:

        * RUNNING / PENDING / AWAITING_REVIEW  → resume from the saved state
        * APPROVED / COMPLETED                 → no-op (already done)
        * FAILED / REJECTED                    → caller chooses to mint a new
                                                 idempotency key for a retry

Status transitions are explicit (`mark_running`, `mark_completed`,
`mark_failed`, …) so accidental clobbering of a finished run is impossible.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

from ...models.enums import AgentName, AgentRunStatus
from ...models.state import AgentRun, TokenUsage
from ._base import row_to_dict


def _to_agent_run(row: asyncpg.Record) -> AgentRun:
    d = dict(row)
    tokens = d.get("tokens")
    if tokens is not None and not isinstance(tokens, TokenUsage):
        d["tokens"] = TokenUsage.model_validate(tokens)
    return AgentRun.model_validate(d)


class AgentRunsRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------- create / resume
    async def get_or_create_run(
        self,
        *,
        case_id: UUID,
        agent: AgentName,
        idempotency_key: str,
        input_payload: dict[str, Any],
        model_name: str | None = None,
    ) -> tuple[AgentRun, bool]:
        """Return `(run, created)`.  `created=False` ⇒ resume an existing run."""
        existing = await self._conn.fetchrow(
            """
            SELECT * FROM agent_runs
             WHERE case_id = $1 AND agent = $2 AND idempotency_key = $3
            """,
            case_id,
            agent.value,
            idempotency_key,
        )
        if existing is not None:
            return _to_agent_run(existing), False

        next_attempt = await self._conn.fetchval(
            """
            SELECT COALESCE(MAX(attempt), 0) + 1
              FROM agent_runs
             WHERE case_id = $1 AND agent = $2
            """,
            case_id,
            agent.value,
        )
        row = await self._conn.fetchrow(
            """
            INSERT INTO agent_runs (
                case_id, agent, attempt, idempotency_key,
                status, input_payload, model_name
            )
            VALUES ($1, $2, $3, $4, 'PENDING', $5, $6)
            RETURNING *
            """,
            case_id,
            agent.value,
            next_attempt,
            idempotency_key,
            input_payload,
            model_name,
        )
        return _to_agent_run(row), True

    # --------------------------------------------------- status transitions
    async def mark_running(self, run_id: UUID) -> AgentRun:
        row = await self._conn.fetchrow(
            """
            UPDATE agent_runs
               SET status = 'RUNNING',
                   started_at = COALESCE(started_at, NOW())
             WHERE id = $1
            RETURNING *
            """,
            run_id,
        )
        if row is None:
            raise LookupError(f"agent_run {run_id} not found")
        return _to_agent_run(row)

    async def mark_completed(
        self,
        *,
        run_id: UUID,
        output_payload: dict[str, Any],
        reasoning: str | None,
        reasoning_summary: str | None,
        tokens: TokenUsage | None,
        duration_ms: int | None,
        requires_review: bool,
    ) -> AgentRun:
        new_status = (
            AgentRunStatus.AWAITING_REVIEW.value
            if requires_review
            else AgentRunStatus.COMPLETED.value
        )
        row = await self._conn.fetchrow(
            """
            UPDATE agent_runs
               SET status = $2,
                   output_payload    = $3,
                   reasoning         = $4,
                   reasoning_summary = $5,
                   tokens            = $6,
                   duration_ms       = $7,
                   completed_at      = NOW()
             WHERE id = $1
            RETURNING *
            """,
            run_id,
            new_status,
            output_payload,
            reasoning,
            reasoning_summary,
            tokens.model_dump() if tokens else None,
            duration_ms,
        )
        if row is None:
            raise LookupError(f"agent_run {run_id} not found")
        return _to_agent_run(row)

    async def mark_failed(
        self,
        *,
        run_id: UUID,
        error: str,
        reasoning: str | None = None,
        duration_ms: int | None = None,
    ) -> AgentRun:
        row = await self._conn.fetchrow(
            """
            UPDATE agent_runs
               SET status       = 'FAILED',
                   error        = $2,
                   reasoning    = COALESCE($3, reasoning),
                   duration_ms  = COALESCE($4, duration_ms),
                   completed_at = NOW()
             WHERE id = $1
            RETURNING *
            """,
            run_id,
            error,
            reasoning,
            duration_ms,
        )
        if row is None:
            raise LookupError(f"agent_run {run_id} not found")
        return _to_agent_run(row)

    # --------------------------------------------------- HITL: approve / edit
    async def approve(self, *, run_id: UUID, analyst_id: str) -> AgentRun:
        row = await self._conn.fetchrow(
            """
            UPDATE agent_runs
               SET status      = 'APPROVED',
                   approved_at = NOW(),
                   approved_by = $2
             WHERE id = $1
               AND status IN ('AWAITING_REVIEW', 'MODIFIED')
            RETURNING *
            """,
            run_id,
            analyst_id,
        )
        if row is None:
            raise LookupError(
                f"agent_run {run_id} not found or not in a reviewable status"
            )
        return _to_agent_run(row)

    async def reject(
        self, *, run_id: UUID, analyst_id: str, reason: str
    ) -> AgentRun:
        row = await self._conn.fetchrow(
            """
            UPDATE agent_runs
               SET status = 'REJECTED',
                   error  = COALESCE(error, '') || E'\\n[analyst:' || $2 || '] ' || $3
             WHERE id = $1
               AND status IN ('AWAITING_REVIEW', 'MODIFIED', 'COMPLETED')
            RETURNING *
            """,
            run_id,
            analyst_id,
            reason,
        )
        if row is None:
            raise LookupError(
                f"agent_run {run_id} not found or not in a reviewable status"
            )
        return _to_agent_run(row)

    async def apply_human_override(
        self,
        *,
        run_id: UUID,
        analyst_id: str,
        new_output: dict[str, Any],
        diff_ops: list[dict[str, Any]],
    ) -> AgentRun:
        """Persist an analyst's edits to an agent's output.

        Records the new payload, marks `human_modified = TRUE`, stores the
        RFC-6902 patch in `human_diff` for audit and replay.  Status moves
        to `MODIFIED` (still requires explicit approve to advance).
        """
        row = await self._conn.fetchrow(
            """
            UPDATE agent_runs
               SET output_payload    = $2,
                   human_modified    = TRUE,
                   human_modified_at = NOW(),
                   human_modified_by = $3,
                   human_diff        = $4,
                   status            = 'MODIFIED'
             WHERE id = $1
            RETURNING *
            """,
            run_id,
            new_output,
            analyst_id,
            diff_ops,
        )
        if row is None:
            raise LookupError(f"agent_run {run_id} not found")
        return _to_agent_run(row)

    # ---------------------------------------------------------------- reads
    async def get(self, run_id: UUID) -> AgentRun | None:
        row = await self._conn.fetchrow(
            "SELECT * FROM agent_runs WHERE id = $1", run_id
        )
        return _to_agent_run(row) if row else None

    async def latest_for(self, case_id: UUID, agent: AgentName) -> AgentRun | None:
        row = await self._conn.fetchrow(
            """
            SELECT * FROM agent_runs
             WHERE case_id = $1 AND agent = $2
             ORDER BY attempt DESC
             LIMIT 1
            """,
            case_id,
            agent.value,
        )
        return _to_agent_run(row) if row else None

    async def list_for_case(self, case_id: UUID) -> list[AgentRun]:
        rows = await self._conn.fetch(
            """
            SELECT * FROM agent_runs
             WHERE case_id = $1
             ORDER BY agent, attempt
            """,
            case_id,
        )
        return [_to_agent_run(r) for r in rows]
