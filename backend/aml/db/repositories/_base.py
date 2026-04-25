"""Tiny shared helpers for repositories."""

from __future__ import annotations

from typing import Any

import asyncpg


def row_to_dict(row: asyncpg.Record | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def rows_to_dicts(rows: list[asyncpg.Record]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]
