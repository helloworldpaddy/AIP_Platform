"""Helpers for loading optional AML schema extensions inside a transaction.

When an optional table (case_transactions, case_swift_messages, …) is missing,
asyncpg aborts the whole transaction on ``UndefinedTableError`` even if Python
catches the exception.  Use a SAVEPOINT so the caller's transaction survives.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import uuid4

import asyncpg

T = TypeVar("T")


async def load_optional(
    conn: asyncpg.Connection,
    loader: Callable[[], Awaitable[T]],
    *,
    default: T,
    savepoint_prefix: str = "optional",
) -> T:
    """Run ``loader()``; return ``default`` if optional tables are absent.

    SAVEPOINTs are only used inside an explicit transaction — autocommit
    read paths can catch ``UndefinedTableError`` directly.
    """
    if not conn.is_in_transaction():
        try:
            return await loader()
        except asyncpg.UndefinedTableError:
            return default

    sp = f"{savepoint_prefix}_{uuid4().hex[:12]}"
    await conn.execute(f'SAVEPOINT "{sp}"')
    try:
        result = await loader()
    except asyncpg.UndefinedTableError:
        await conn.execute(f'ROLLBACK TO SAVEPOINT "{sp}"')
        return default
    else:
        await conn.execute(f'RELEASE SAVEPOINT "{sp}"')
        return result
