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

from ..db.client import AmlDbClient
from .dependencies import get_db
from .errors import install_error_handlers
from .routes.agents import case_agents_router, runs_router
from .routes.audit import router as audit_router
from .routes.cases import router as cases_router
from .routes.gates import router as gates_router
from .routes.narratives import router as narratives_router
from .routes.parties import router as parties_router
from .schemas import HealthResponse

log = logging.getLogger(__name__)


def create_app(*, cors_origins: list[str] | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = get_db()
        await db.connect()
        log.info("aml.api.startup ok")
        try:
            yield
        finally:
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

    return app
