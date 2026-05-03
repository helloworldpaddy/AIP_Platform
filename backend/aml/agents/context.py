"""Per-invocation context for agent tools.

Tools are module-level async functions (so they can be exposed to ADK and
reused across cases), but they need to know *which* case + agent_run they're
serving so they can write to the correct rows in `evidence_ledger` /
`case_parties`.

We use `contextvars` because they are async-task-local: each `Orchestrator`
invocation sets the var before calling the LLM, and any tool callback —
even if executed inside an `await` — sees the right context.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from dataclasses import field
from typing import Iterator
from uuid import UUID

from ..db.client import AmlRepositories


@dataclass(frozen=True)
class AgentToolContext:
    case_id: UUID
    agent_run_id: UUID
    actor_id: str  # the agent's name, used as evidence.created_by
    repos: AmlRepositories
    # ADK may execute multiple tool calls concurrently. Our repositories share
    # a single asyncpg connection, so we must serialize DB writes per agent turn.
    db_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_current: ContextVar[AgentToolContext | None] = ContextVar(
    "aml_agent_tool_context", default=None
)


def current_tool_context() -> AgentToolContext:
    ctx = _current.get()
    if ctx is None:
        raise RuntimeError(
            "AgentToolContext not set — tools must run inside `bind_tool_context()`"
        )
    return ctx


def is_tool_context_bound() -> bool:
    """True when tools are running inside the AML orchestrator (DB-backed)."""
    return _current.get() is not None


@contextmanager
def bind_tool_context(ctx: AgentToolContext) -> Iterator[None]:
    token = _current.set(ctx)
    try:
        yield
    finally:
        _current.reset(token)
