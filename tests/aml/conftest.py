"""Pytest fixtures for the AML integration suite.

These tests exercise the orchestrator + FastAPI surface against a real
Postgres (the one provisioned by `docker/docker-compose.yml`).  No LLM is
required — agents are replaced with deterministic stubs from `stubs.py`.

Cleanup strategy
----------------
The audit_trail table has a trigger that blocks UPDATE/DELETE/TRUNCATE,
and `cases` cascades to it.  Per-test DELETEs would therefore fail.

We instead reset state once per session by dropping and re-creating the
entire `aml` schema, then let each test mint a unique `case_number` so
they cannot collide.  The schema reset uses a synchronous psycopg
connection so it doesn't get bound to a particular asyncio event loop;
the asyncpg pool the tests actually use is function-scoped.

If the configured Postgres is unreachable the whole module is skipped —
unit tests in other packages continue to run normally.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import psycopg
import pytest
import pytest_asyncio
import secrets

from agents.rag_agent.config.settings import get_settings
from backend.aml.agents.base import BaseAgent
from backend.aml.api.app import create_app
from backend.aml.api.dependencies import get_db, get_orchestrator
from backend.aml.db.client import AmlDbClient
from backend.aml.models.enums import AgentName
from backend.aml.orchestrator import Orchestrator

from .stubs import (
    StubCaseAnalysisAgent,
    StubDueDiligenceAgent,
    StubInitialAssessmentAgent,
    StubTransactionEnrichmentAgent,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AML_SCHEMA_SQL = _REPO_ROOT / "backend" / "aml" / "db" / "schema.sql"


def _sync_dsn() -> str:
    """psycopg-style DSN derived from the same settings asyncpg uses."""
    db = get_settings().database
    return (
        f"host={db.host} port={db.port} dbname={db.name} "
        f"user={db.user} password={db.password.get_secret_value()}"
    )


@pytest.fixture(scope="session")
def _reset_schema() -> None:
    """Drop and re-apply the AML schema once per pytest session.

    Uses psycopg (sync) so this fixture has no event-loop affinity — it
    can run before the asyncpg pool is even constructed.  Skips the suite
    if Postgres isn't reachable.
    """
    try:
        conn = psycopg.connect(_sync_dsn(), connect_timeout=2)
    except (psycopg.OperationalError, OSError) as err:
        pytest.skip(f"AML Postgres not reachable: {err}")
        return  # for the type checker

    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA IF EXISTS aml CASCADE")
            cur.execute(_AML_SCHEMA_SQL.read_text(encoding="utf-8"))
    finally:
        conn.close()


@pytest_asyncio.fixture()
async def aml_db(_reset_schema) -> AsyncIterator[AmlDbClient]:
    """Function-scoped asyncpg pool so it's bound to the test's loop.

    Each test pays one connect/close cycle (~50ms); in exchange we never
    have to reason about pools that span loops.
    """
    db = AmlDbClient()
    # Force a fresh pool — the module-level singleton may carry state
    # across tests if anyone calls `get_aml_db_client()`.
    db._pool = None
    await db.connect()
    try:
        yield db
    finally:
        await db.close()


@pytest.fixture()
def case_number() -> str:
    """Unique case number per test so rows don't collide across runs."""
    return f"AML-TEST-{secrets.token_hex(4).upper()}"


@pytest.fixture()
def stub_agents() -> dict[AgentName, BaseAgent]:
    return {
        AgentName.INITIAL_ASSESSMENT: StubInitialAssessmentAgent(),
        AgentName.TRANSACTION_ENRICHMENT: StubTransactionEnrichmentAgent(),
        AgentName.DUE_DILIGENCE: StubDueDiligenceAgent(),
        AgentName.CASE_ANALYSIS: StubCaseAnalysisAgent(),
    }


@pytest.fixture()
def orchestrator(
    aml_db: AmlDbClient, stub_agents: dict[AgentName, BaseAgent]
) -> Orchestrator:
    return Orchestrator(aml_db, agents=stub_agents)


@pytest_asyncio.fixture()
async def api_app(
    aml_db: AmlDbClient, stub_agents: dict[AgentName, BaseAgent]
):
    """FastAPI app wired to the test pool + stub orchestrator.

    Uses `dependency_overrides` so route handlers see the same singletons
    the test fixtures hold — avoids spawning a second pool.
    """
    orch = Orchestrator(aml_db, agents=stub_agents)
    app = create_app()
    app.dependency_overrides[get_db] = lambda: aml_db
    app.dependency_overrides[get_orchestrator] = lambda: orch
    yield app
    app.dependency_overrides.clear()
