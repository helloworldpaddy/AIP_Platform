"""Audit-trail repository.

The table is append-only at the SQL level (the `trg_audit_no_update` trigger
rejects every UPDATE / DELETE / TRUNCATE).  Inserts go through the
`trg_audit_chain` trigger which fills `prev_hash` and computes
`data_hash = sha256(prev_hash ‖ canonical(row))`.

Verifying chain integrity is therefore a pure read-side operation —
`verify_chain` walks the rows in insertion order and re-computes the hash to
detect tampering.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

from ...models.enums import ActorType, AuditEventType
from ...models.state import AuditEvent
from ...utils.hashing import sha256_hex


def _to_event(row: asyncpg.Record) -> AuditEvent:
    return AuditEvent.model_validate(dict(row))


class AuditRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def append(
        self,
        *,
        case_id: UUID,
        actor_type: ActorType,
        actor_id: str,
        event_type: AuditEventType,
        event_payload: dict[str, Any] | None = None,
        reasoning_text: str | None = None,
        agent_run_id: UUID | None = None,
    ) -> AuditEvent:
        row = await self._conn.fetchrow(
            """
            INSERT INTO audit_trail (
                case_id, agent_run_id, actor_type, actor_id,
                event_type, event_payload, reasoning_text
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
            """,
            case_id,
            agent_run_id,
            actor_type.value,
            actor_id,
            event_type.value,
            event_payload or {},
            reasoning_text,
        )
        return _to_event(row)

    async def list_for_case(
        self, case_id: UUID, *, limit: int = 200
    ) -> list[AuditEvent]:
        rows = await self._conn.fetch(
            """
            SELECT * FROM audit_trail
             WHERE case_id = $1
             ORDER BY id
             LIMIT $2
            """,
            case_id,
            limit,
        )
        return [_to_event(r) for r in rows]

    async def verify_chain(self, case_id: UUID) -> tuple[bool, int | None]:
        """Walk the chain in order; return `(ok, first_bad_id_or_None)`.

        Mirrors the canonical-string layout used by the `audit_chain_insert`
        trigger so the recomputed hash matches the stored `data_hash`.
        """
        rows = await self._conn.fetch(
            """
            SELECT id, case_id, actor_type, actor_id, event_type,
                   event_payload, reasoning_text, prev_hash, data_hash
              FROM audit_trail
             WHERE case_id = $1
             ORDER BY id
            """,
            case_id,
        )

        prev_hash = ""
        for r in rows:
            payload = r["event_payload"]
            if isinstance(payload, dict):
                # The trigger casts JSONB to text — Postgres stores keys in
                # arbitrary order, so we re-fetch the canonical text rather
                # than re-serialising in Python.
                payload_text = await self._conn.fetchval(
                    "SELECT $1::jsonb::text", payload
                )
            else:
                payload_text = payload or "{}"

            canonical = (
                (prev_hash or "")
                + "|"
                + str(r["case_id"])
                + "|"
                + str(r["actor_type"])
                + "|"
                + r["actor_id"]
                + "|"
                + str(r["event_type"])
                + "|"
                + (payload_text or "{}")
                + "|"
                + (r["reasoning_text"] or "")
            )
            if sha256_hex(canonical) != r["data_hash"]:
                return False, int(r["id"])
            prev_hash = r["data_hash"]
        return True, None
