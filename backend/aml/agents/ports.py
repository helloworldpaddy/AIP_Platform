"""Execution ports — orchestrator ↔ domain agent boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..models.enums import AgentName
from .base import AgentContext, AgentResult, BaseAgent


@dataclass(frozen=True)
class ToolGatewaySpec:
    """Run-scoped tool endpoint for remote agents (Sprint 2+).

    Remote stages call back into the orchestrator to perform case-bound tool
    writes (``record_evidence``, ``kyc_lookup``, etc.) without DB credentials.
    """

    transport: str  # e.g. "mcp", "http"
    url: str
    token: str
    allowed_tools: tuple[str, ...]


class AgentExecutionPort(Protocol):
    """Execute one agent stage turn (in-process ADK or remote A2A)."""

    async def execute(
        self,
        *,
        agent_name: AgentName,
        agent: BaseAgent,
        ctx: AgentContext,
        user_message: str,
        tool_gateway: ToolGatewaySpec | None = None,
    ) -> AgentResult:
        """Run the stage and return an :class:`AgentResult` for Phase 3 persist."""
        ...
