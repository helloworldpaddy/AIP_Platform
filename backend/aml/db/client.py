"""Async Postgres client for the AML platform.

Owns one process-wide asyncpg pool, registers JSONB / UUID[] codecs once per
connection, and hands out a `AmlRepositories` bundle scoped to a single
connection (so the orchestrator can run multi-repo writes atomically inside
a single transaction).

Typical usage from a FastAPI route:

    db = get_aml_db_client()
    async with db.transaction() as repos:
        case = await repos.cases.create(dto)
        await repos.audit.append(case_id=case.id, ...)

Read-only call:

    async with db.connection() as repos:
        case = await repos.cases.get(case_id)
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg

from agents.rag_agent.config.settings import get_settings

from .repositories import (
    AgentRunsRepository,
    AuditRepository,
    CaseMonitoringRepository,
    CasePartiesRepository,
    CasesRepository,
    EvidenceRepository,
    HumanGatesRepository,
    NarrativesRepository,
)

log = logging.getLogger(__name__)


class AmlRepositories:
    """Bundle of connection-scoped repositories.

    All repositories share the same `asyncpg.Connection`; if the caller wraps
    them in `db.transaction()`, every write is part of one atomic commit.
    """

    __slots__ = (
        "_conn",
        "cases",
        "case_monitoring",
        "agent_runs",
        "evidence",
        "parties",
        "gates",
        "narratives",
        "audit",
    )

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn
        self.cases = CasesRepository(conn)
        self.case_monitoring = CaseMonitoringRepository(conn)
        self.agent_runs = AgentRunsRepository(conn)
        self.evidence = EvidenceRepository(conn)
        self.parties = CasePartiesRepository(conn)
        self.gates = HumanGatesRepository(conn)
        self.narratives = NarrativesRepository(conn)
        self.audit = AuditRepository(conn)

    @property
    def connection(self) -> asyncpg.Connection:
        return self._conn


class AmlDbClient:
    """Thin asyncpg pool wrapper specialised for the AML schema."""

    def __init__(self) -> None:
        self._db = get_settings().database
        self._pool: asyncpg.Pool | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ pool
    async def _init_connection(self, conn: asyncpg.Connection) -> None:
        """Per-connection one-shot setup (codecs).

        Runs only when asyncpg actually creates a new connection, not on
        each acquire.  Codecs are client-side state, so they survive the
        pool's `RESET ALL` on release.
        """
        await conn.set_type_codec(
            "jsonb",
            encoder=json.dumps,
            decoder=json.loads,
            schema="pg_catalog",
        )
        await conn.set_type_codec(
            "json",
            encoder=json.dumps,
            decoder=json.loads,
            schema="pg_catalog",
        )

    async def _setup_connection(self, conn: asyncpg.Connection) -> None:
        """Per-acquire session setup (search_path + timeouts).

        asyncpg pool issues `RESET ALL` on release, which wipes
        `search_path` and `statement_timeout` on the server side.  We
        re-apply them here so every acquired connection resolves the
        unqualified `cases`, `agent_runs`, etc. against the `aml` schema.
        """
        await conn.execute("SET search_path TO aml, public")
        if self._db.statement_timeout_ms:
            await conn.execute(
                f"SET statement_timeout = {int(self._db.statement_timeout_ms)}"
            )

    async def connect(self) -> None:
        if self._pool is not None:
            return
        async with self._lock:
            if self._pool is not None:
                return
            self._pool = await asyncpg.create_pool(
                dsn=self._db.dsn,
                min_size=self._db.pool_min,
                max_size=self._db.pool_max,
                init=self._init_connection,
                setup=self._setup_connection,
            )
            log.info(
                "aml.postgres.pool.connected host=%s db=%s", self._db.host, self._db.name
            )

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("AML pool not initialised — call connect() first")
        return self._pool

    # ------------------------------------------------------------- contexts
    @asynccontextmanager
    async def connection(self) -> AsyncIterator[AmlRepositories]:
        """Acquire a connection (no implicit transaction).

        Use for read-only flows.  Each repository call still issues its own
        SQL statement but they share the same physical connection.
        """
        await self.connect()
        async with self.pool.acquire() as conn:
            yield AmlRepositories(conn)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AmlRepositories]:
        """Acquire a connection inside a transaction.

        On exit the transaction commits (or rolls back on exception).  All
        repository writes performed via the yielded bundle are atomic.
        """
        await self.connect()
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                yield AmlRepositories(conn)


_singleton: AmlDbClient | None = None


def get_aml_db_client() -> AmlDbClient:
    global _singleton
    if _singleton is None:
        _singleton = AmlDbClient()
    return _singleton
