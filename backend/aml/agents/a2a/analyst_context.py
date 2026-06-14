"""Analyst identity for AML host-agent tool calls (Sprint 7)."""

from __future__ import annotations

from contextvars import ContextVar, Token

_analyst_id: ContextVar[str | None] = ContextVar("aml_host_analyst_id", default=None)
_reset_token: ContextVar[Token | None] = ContextVar("aml_analyst_reset_token", default=None)


def set_analyst_context(analyst_id: str) -> Token:
    """Bind analyst id for the current async task; return reset token."""
    token = _analyst_id.set(analyst_id.strip())
    _reset_token.set(token)
    return token


def reset_analyst_context(token: Token) -> None:
    _analyst_id.reset(token)


def reset_bound_analyst_context() -> None:
    """Reset analyst context using the task-local token (safe for pickled session state)."""
    token = _reset_token.get()
    if token is not None:
        _analyst_id.reset(token)
        _reset_token.set(None)


def current_analyst_id() -> str | None:
    return _analyst_id.get()


def require_analyst_id() -> str:
    """Return the bound analyst id or raise if the A2A client omitted it."""
    analyst = _analyst_id.get()
    if not analyst or not analyst.strip():
        raise PermissionError(
            "missing analyst_id in A2A metadata — set aml.analyst_id on the message"
        )
    return analyst.strip()
