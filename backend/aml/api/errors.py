"""Centralised exception → HTTP response mapping.

Keeps domain code (`raise GateBlocked(...)`, `raise LookupError(...)`,
`raise PermissionError(...)`) free of HTTP concerns.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from ..orchestrator import GateBlocked

log = logging.getLogger(__name__)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(GateBlocked)
    async def _gate_blocked(_request: Request, err: GateBlocked) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": "gate_blocked",
                "agent": err.agent.value,
                "gate_name": err.gate.gate_name,
                "gate_id": str(err.gate.id),
                "message": str(err),
            },
        )

    @app.exception_handler(LookupError)
    async def _not_found(_request: Request, err: LookupError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "not_found", "message": str(err)},
        )

    @app.exception_handler(PermissionError)
    async def _forbidden(_request: Request, err: PermissionError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"error": "forbidden", "message": str(err)},
        )

    @app.exception_handler(ValueError)
    async def _bad_request(_request: Request, err: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "bad_request", "message": str(err)},
        )
