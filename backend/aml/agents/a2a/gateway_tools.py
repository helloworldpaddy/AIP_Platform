"""HTTP proxy tools — remote A2A hosts call the orchestrator tool gateway."""

from __future__ import annotations

import inspect
import logging
from contextvars import ContextVar, Token
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
_reset_token: ContextVar[Token | None] = ContextVar(
    "aml_gateway_reset_token", default=None
)


def current_gateway_tool_context() -> GatewayToolContext:
    ctx = _current.get()
    if ctx is None:
        raise RuntimeError(
            "GatewayToolContext not set — A2A host must bind tool gateway metadata"
        )
    return ctx


def set_gateway_tool_context(ctx: GatewayToolContext) -> Token:
    """Bind gateway credentials for the current async task; return reset token."""
    token = _current.set(ctx)
    _reset_token.set(token)
    return token


def reset_gateway_tool_context(token: Token) -> None:
    _current.reset(token)


def reset_bound_gateway_tool_context() -> None:
    """Reset gateway context using the task-local token (safe for pickled session state)."""
    token = _reset_token.get()
    if token is not None:
        _current.reset(token)
        _reset_token.set(None)


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
        if response.status_code >= 400:
            detail = response.text
            try:
                payload = response.json()
                if isinstance(payload, dict) and payload.get("detail"):
                    detail = str(payload["detail"])
            except Exception:  # noqa: BLE001
                pass
            log.warning(
                "gateway_tools.http_error tool=%s status=%s detail=%s",
                tool_name,
                response.status_code,
                detail[:300],
            )
            return {
                "error": f"tool gateway HTTP {response.status_code}",
                "detail": detail,
            }
        body = response.json()
    result = body.get("result", body)
    if not isinstance(result, dict):
        return {"result": result}
    return result


def _make_gateway_tool(tool_name: str, prototype_fn: Any) -> FunctionTool:
    """Proxy with the same signature/doc as the orchestrator tool (ADK schema parity)."""

    async def _tool(*args: Any, **kwargs: Any) -> dict[str, Any]:
        if args:
            return {
                "error": f"{tool_name} does not accept positional arguments",
                "received_args": len(args),
            }
        return await _invoke_gateway_tool(tool_name, kwargs)

    _tool.__name__ = tool_name
    _tool.__doc__ = prototype_fn.__doc__
    _tool.__signature__ = inspect.signature(prototype_fn)
    _tool.__annotations__ = dict(getattr(prototype_fn, "__annotations__", {}))
    return FunctionTool(func=_tool)


def gateway_tools_named(names: list[str]) -> list[FunctionTool]:
    """Build ADK tools that proxy to the orchestrator tool gateway."""
    from ..tools import ADK_TOOLS, validate_adk_tool_names

    validate_adk_tool_names(names)
    return [_make_gateway_tool(name, ADK_TOOLS[name].func) for name in names]
