"""FastAPI app factory + lifespan.

Production wiring is delegated to `dependencies.py` so tests can override
any singleton via `app.dependency_overrides`.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..agents.tools.data_tools import set_graph_provider
from ..agents.tools.data_tools import set_kyc_provider, set_search_provider
from ..db.client import AmlDbClient
from ..integrations.neo4j_provider import build_neo4j_provider_if_configured
from ..models.enums import ActorType, AuditEventType
from ..integrations.demo_providers import DemoKycProvider, DemoSearchProvider
from .dependencies import get_db
from .errors import install_error_handlers
from .routes.agents import case_agents_router, runs_router
from .routes.audit import router as audit_router
from .routes.cases import router as cases_router
from .routes.gates import router as gates_router
from .routes.graph import router as graph_router
from .routes.narratives import router as narratives_router
from .routes.parties import router as parties_router
from .schemas import HealthResponse

log = logging.getLogger(__name__)


def create_app(*, cors_origins: list[str] | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = get_db()
        await db.connect()

        # Demo-safe defaults: provide deterministic KYC + web-search stubs so
        # Due Diligence can run in local/dev without wiring real providers.
        set_kyc_provider(DemoKycProvider())
        set_search_provider(DemoSearchProvider())

        # If the API process is restarted while an agent is mid-flight, the DB row
        # can remain stuck in RUNNING forever. Reconcile those orphaned runs back
        # to PENDING so a re-trigger can safely resume.
        async with db.transaction() as repos:
            stale = await repos.connection.fetch(
                """
                SELECT id, case_id, agent, started_at
                  FROM agent_runs
                 WHERE status = 'RUNNING'
                   AND completed_at IS NULL
                   AND started_at IS NOT NULL
                   AND started_at < (NOW() - INTERVAL '2 minutes')
                """
            )
            if stale:
                await repos.connection.execute(
                    """
                    UPDATE agent_runs
                       SET status = 'PENDING',
                           started_at = NULL,
                           error = COALESCE(error, '') || E'\n[system] Requeued after API restart (stale RUNNING).'
                     WHERE status = 'RUNNING'
                       AND completed_at IS NULL
                       AND started_at IS NOT NULL
                       AND started_at < (NOW() - INTERVAL '2 minutes')
                    """
                )
                for r in stale:
                    await repos.audit.append(
                        case_id=r["case_id"],
                        actor_type=ActorType.SYSTEM,
                        actor_id="api-startup",
                        event_type=AuditEventType.AGENT_FAILED,
                        event_payload={
                            "run_id": str(r["id"]),
                            "agent": r["agent"],
                            "note": "requeued stale RUNNING run after API restart",
                            "started_at": (
                                r["started_at"].isoformat()
                                if r["started_at"] is not None
                                else None
                            ),
                        },
                        agent_run_id=r["id"],
                    )

        # Optional: wire the Neo4j-backed GraphProvider if configured.  When
        # `NEO4J_URI` is unset we leave the provider slot empty — the agent
        # will surface a "Graph provider not configured" error if it tries
        # to call `neo4j_hop_traversal`, which is the desired loud failure
        # mode for an unwired deployment.
        neo4j_provider = build_neo4j_provider_if_configured()
        if neo4j_provider is not None:
            try:
                await neo4j_provider.connect()
                set_graph_provider(neo4j_provider)
            except Exception:  # noqa: BLE001 — log + degrade
                log.exception("aml.api.neo4j.connect_failed")
                neo4j_provider = None

        log.info("aml.api.startup ok neo4j=%s", neo4j_provider is not None)
        try:
            yield
        finally:
            if neo4j_provider is not None:
                await neo4j_provider.close()
            await db.close()
            log.info("aml.api.shutdown ok")

    app = FastAPI(
        title="AML Investigation Agentic Platform",
        version="0.1.0",
        description=(
            "HTTP surface for the four-agent AML investigation workflow.  "
            "Every mutating endpoint requires the `X-Analyst-Id` header for "
            "audit attribution."
        ),
        lifespan=lifespan,
    )

    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
            allow_credentials=True,
        )

    install_error_handlers(app)

    @app.get("/healthz", response_model=HealthResponse, tags=["meta"])
    async def healthz(db: AmlDbClient = Depends(get_db)) -> HealthResponse:
        try:
            await db.connect()
            async with db.connection() as repos:
                await repos.connection.fetchval("SELECT 1")
            return HealthResponse(status="ok", db="connected")
        except Exception as err:  # noqa: BLE001
            log.exception("healthz.db.error")
            return HealthResponse(status="degraded", db=f"error: {err}")

    app.include_router(cases_router)
    app.include_router(case_agents_router)
    app.include_router(runs_router)
    app.include_router(gates_router)
    app.include_router(parties_router)
    app.include_router(narratives_router)
    app.include_router(audit_router)
    app.include_router(graph_router)

    return app
