"""Dispatch context-aware AML tools for a run-scoped gateway token."""

from __future__ import annotations

import inspect
import logging
import os
import time
from typing import Any
from uuid import UUID

from ...db.client import AmlDbClient
from ...models.enums import AgentName, AgentRunStatus
from ..context import AgentToolContext, bind_tool_context
from ..ports import ToolGatewaySpec
from ..tools import ADK_TOOLS
from .tokens import ToolGatewayClaims, mint_tool_gateway_token

log = logging.getLogger(__name__)


def _gateway_base_url() -> str:
    return os.getenv("AML_TOOL_GATEWAY_BASE_URL", "http://localhost:8000").rstrip("/")


def _gateway_ttl_seconds() -> int:
    raw = os.getenv("AML_TOOL_GATEWAY_TTL_SECONDS", "3600")
    try:
        return max(60, int(raw))
    except ValueError:
        return 3600


class ToolGatewayService:
    """Mint and verify run-scoped credentials; invoke allowed tools with DB context."""

    def __init__(self, db: AmlDbClient) -> None:
        self._db = db

    def mint_for_run(
        self,
        *,
        run_id: UUID,
        case_id: UUID,
        agent_name: AgentName,
        allowed_tools: list[str],
    ) -> ToolGatewaySpec:
        unknown = [t for t in allowed_tools if t not in ADK_TOOLS]
        if unknown:
            raise ValueError(f"unknown tool(s) for gateway: {unknown}")

        exp = int(time.time()) + _gateway_ttl_seconds()
        token = mint_tool_gateway_token(
            claims=ToolGatewayClaims(
                run_id=run_id,
                case_id=case_id,
                agent=agent_name,
                allowed_tools=tuple(allowed_tools),
                exp=exp,
            )
        )
        url = f"{_gateway_base_url()}/internal/tool-gateway/runs/{run_id}/invoke"
        return ToolGatewaySpec(
            transport="http",
            url=url,
            token=token,
            allowed_tools=tuple(allowed_tools),
        )

    async def invoke(
        self,
        *,
        claims: ToolGatewayClaims,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        if tool_name not in claims.allowed_tools:
            raise PermissionError(
                f"tool {tool_name!r} not allowed for run {claims.run_id}"
            )
        if tool_name not in ADK_TOOLS:
            raise LookupError(f"unknown tool: {tool_name}")

        async with self._db.transaction() as repos:
            run = await repos.agent_runs.get(claims.run_id)
            if run is None:
                raise LookupError(f"agent_run {claims.run_id} not found")
            if run.case_id != claims.case_id:
                raise PermissionError("token case_id does not match run")
            if run.agent != claims.agent:
                raise PermissionError("token agent does not match run")
            if run.status != AgentRunStatus.RUNNING:
                raise PermissionError(
                    f"run {claims.run_id} is not RUNNING (status={run.status.value})"
                )

            tool_ctx = AgentToolContext(
                case_id=claims.case_id,
                agent_run_id=claims.run_id,
                actor_id=claims.agent.value,
                repos=repos,
            )
            fn = ADK_TOOLS[tool_name].func
            try:
                with bind_tool_context(tool_ctx):
                    result = fn(**arguments)
                    if inspect.isawaitable(result):
                        result = await result
            except TypeError as err:
                log.warning(
                    "tool_gateway.invoke.bad_arguments tool=%s err=%s args=%s",
                    tool_name,
                    err,
                    list(arguments.keys()),
                )
                return {"error": f"invalid arguments for {tool_name}: {err}"}

        if not isinstance(result, dict):
            return {"result": result}
        return result


def build_tool_gateway_service(db: AmlDbClient) -> ToolGatewayService:
    return ToolGatewayService(db)
