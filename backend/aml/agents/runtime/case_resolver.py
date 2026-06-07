"""Resolve AML cases from user text (case number)."""

from __future__ import annotations

import re
from uuid import UUID

from ...db.client import get_aml_db_client
from ...models.state import Case

# AML-DEMO-2026-001, AML-SERVICES-SWIFT-2026-003, etc.
_CASE_NUMBER_RE = re.compile(
    r"\b(AML-[A-Z0-9]+(?:-[A-Z0-9]+)*-\d{4}-\d{3,})\b",
    re.IGNORECASE,
)


def parse_case_number(text: str) -> str | None:
    """Extract the first AML case number from free-form user text."""
    if not text:
        return None
    m = _CASE_NUMBER_RE.search(text.strip())
    return m.group(1).upper() if m else None


async def load_case_by_number(case_number: str) -> Case:
    """Return the case row or raise ``LookupError``."""
    db = get_aml_db_client()
    await db.connect()
    async with db.connection() as repos:
        case = await repos.cases.get_by_number(case_number)
        if case is None:
            raise LookupError(f"case not found: {case_number}")
        if case.locked:
            raise PermissionError(
                f"case {case_number} is locked; no further agent runs"
            )
        return case


async def case_id_for_number(case_number: str) -> UUID:
    case = await load_case_by_number(case_number)
    return case.id
