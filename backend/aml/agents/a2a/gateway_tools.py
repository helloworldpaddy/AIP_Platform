"""HTTP proxy tools — remote A2A hosts call the orchestrator tool gateway."""

from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

import httpx
from google.adk.tools import FunctionTool

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GatewayToolContext:
    url: str
    token: str
    allowed_tools: tuple[str, ...]


_current: ContextVar[GatewayToolContext | None] = ContextVar(
    "aml_gateway_tool_context", default=None
)


def current_gateway_tool_context() -> GatewayToolContext:
    ctx = _current.get()
    if ctx is None:
        raise RuntimeError(
            "GatewayToolContext not set — A2A host must bind tool gateway metadata"
        )
    return ctx


def set_gateway_tool_context(ctx: GatewayToolContext):
    """Bind gateway credentials for the current async task; return reset token."""
    return _current.set(ctx)


def reset_gateway_tool_context(token) -> None:
    _current.reset(token)


async def _invoke_gateway_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    ctx = current_gateway_tool_context()
    if tool_name not in ctx.allowed_tools:
        raise PermissionError(f"tool {tool_name!r} not allowed by gateway token")
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            ctx.url,
            headers={"Authorization": f"Bearer {ctx.token}"},
            json={"tool": tool_name, "arguments": arguments},
        )
        response.raise_for_status()
        body = response.json()
    result = body.get("result", body)
    if not isinstance(result, dict):
        return {"result": result}
    return result


def _make_gateway_tool(tool_name: str):
    async def _tool(**arguments: Any) -> dict[str, Any]:
        return await _invoke_gateway_tool(tool_name, arguments)

    _tool.__name__ = tool_name
    return _tool


def gateway_tools_named(names: list[str]) -> list[FunctionTool]:
    """Build ADK tools that proxy to the orchestrator tool gateway."""
    return [FunctionTool(func=_make_gateway_tool(name)) for name in names]
