"""Narrative repository — versioned, lockable on submission."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

from ...models.enums import Classification
from ...models.state import Citation, Narrative


def _to_narrative(row: asyncpg.Record) -> Narrative:
    d = dict(row)
    if d.get("citations") is not None and d["citations"] and not isinstance(
        d["citations"][0], Citation
    ):
        d["citations"] = [Citation.model_validate(c) for c in d["citations"]]
    return Narrative.model_validate(d)


class NarrativesRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def create(
        self,
        *,
        case_id: UUID,
        classification: Classification,
        rationale: str,
        markdown_body: str,
        citations: list[Citation],
        created_by: str,
    ) -> Narrative:
        next_version = await self._conn.fetchval(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM narratives WHERE case_id = $1",
            case_id,
        )
        row = await self._conn.fetchrow(
            """
            INSERT INTO narratives (
                case_id, version, classification, rationale,
                markdown_body, citations, created_by
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
            """,
            case_id,
            next_version,
            classification.value,
            rationale,
            markdown_body,
            # mode="json" coerces UUIDs to strings so the JSONB codec can
            # serialise them; plain model_dump() leaves them as UUID
            # objects, which json.dumps refuses.
            [c.model_dump(mode="json") for c in citations],
            created_by,
        )
        return _to_narrative(row)

    async def update_draft(
        self,
        *,
        narrative_id: UUID,
        rationale: str | None = None,
        markdown_body: str | None = None,
        citations: list[Citation] | None = None,
        human_modified: bool = False,
    ) -> Narrative:
        row = await self._conn.fetchrow(
            """
            UPDATE narratives
               SET rationale     = COALESCE($2, rationale),
                   markdown_body = COALESCE($3, markdown_body),
                   citations     = COALESCE($4, citations),
                   human_modified = human_modified OR $5
             WHERE id = $1
               AND submitted = FALSE
            RETURNING *
            """,
            narrative_id,
            rationale,
            markdown_body,
            [c.model_dump(mode="json") for c in citations]
            if citations is not None
            else None,
            human_modified,
        )
        if row is None:
            raise LookupError(
                f"narrative {narrative_id} not found or already submitted"
            )
        return _to_narrative(row)

    async def submit(
        self,
        *,
        narrative_id: UUID,
        analyst_id: str,
    ) -> Narrative:
        """Submission flips both `submitted` and `locked` so the
        narrative-lock-guard trigger blocks all future writes."""
        row = await self._conn.fetchrow(
            """
            UPDATE narratives
               SET submitted    = TRUE,
                   submitted_at = NOW(),
                   submitted_by = $2,
                   locked       = TRUE
             WHERE id = $1
               AND submitted = FALSE
            RETURNING *
            """,
            narrative_id,
            analyst_id,
        )
        if row is None:
            raise LookupError(
                f"narrative {narrative_id} not found or already submitted"
            )
        return _to_narrative(row)

    async def list_for_case(self, case_id: UUID) -> list[Narrative]:
        rows = await self._conn.fetch(
            "SELECT * FROM narratives WHERE case_id = $1 ORDER BY version",
            case_id,
        )
        return [_to_narrative(r) for r in rows]

    async def latest(self, case_id: UUID) -> Narrative | None:
        row = await self._conn.fetchrow(
            """
            SELECT * FROM narratives
             WHERE case_id = $1
             ORDER BY version DESC
             LIMIT 1
            """,
            case_id,
        )
        return _to_narrative(row) if row else None
