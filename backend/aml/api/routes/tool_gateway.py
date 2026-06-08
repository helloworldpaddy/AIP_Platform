"""Internal HTTP surface for remote agents to invoke case-scoped AML tools."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from ...agents.tool_gateway.service import ToolGatewayService
from ...agents.tool_gateway.tokens import verify_tool_gateway_token
from ...db.client import AmlDbClient
from ..dependencies import get_tool_gateway

router = APIRouter(prefix="/internal/tool-gateway", tags=["tool-gateway"])


class ToolInvokeRequest(BaseModel):
    tool: str = Field(..., description="Tool name, e.g. record_evidence")
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolInvokeResponse(BaseModel):
    tool: str
    result: dict[str, Any]


def _bearer_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing Bearer token",
        )
    return authorization.removeprefix("Bearer ").strip()


@router.post(
    "/runs/{run_id}/invoke",
    response_model=ToolInvokeResponse,
)
async def invoke_tool(
    run_id: UUID,
    body: ToolInvokeRequest,
    token: str = Depends(_bearer_token),
    gateway: ToolGatewayService = Depends(get_tool_gateway),
) -> ToolInvokeResponse:
    try:
        claims = verify_tool_gateway_token(token)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(err),
        ) from err

    if claims.run_id != run_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="token run_id mismatch",
        )

    try:
        result = await gateway.invoke(
            claims=claims,
            tool_name=body.tool,
            arguments=body.arguments,
        )
    except PermissionError as err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(err),
        ) from err
    except LookupError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except Exception as err:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{err.__class__.__name__}: {err}",
        ) from err

    return ToolInvokeResponse(tool=body.tool, result=result)


@router.get("/runs/{run_id}/tools")
async def list_allowed_tools(
    run_id: UUID,
    token: str = Depends(_bearer_token),
) -> dict[str, list[str]]:
    try:
        claims = verify_tool_gateway_token(token)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(err),
        ) from err
    if claims.run_id != run_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="token run_id mismatch",
        )
    return {"tools": list(claims.allowed_tools)}
