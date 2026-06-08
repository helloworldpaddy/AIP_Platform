"""Shared Orchestrator factory for ADK web / runtime tools."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...config.agent_transport import load_agent_transport_config
from ...db.client import get_aml_db_client
from ..tool_gateway import build_tool_gateway_service

if TYPE_CHECKING:
    from ...orchestrator.service import Orchestrator

_orchestrator: Orchestrator | None = None


def build_runtime_orchestrator() -> Orchestrator:
    """Process-wide orchestrator with transport config + tool gateway (Sprint 4)."""
    global _orchestrator
    if _orchestrator is None:
        from ..registry import build_default_agents
        from ...orchestrator.service import Orchestrator

        db = get_aml_db_client()
        _orchestrator = Orchestrator(
            db,
            build_default_agents(),
            transport_config=load_agent_transport_config(),
            tool_gateway=build_tool_gateway_service(db),
        )
    return _orchestrator


def reset_runtime_orchestrator() -> None:
    """Test helper — drop cached singleton."""
    global _orchestrator
    _orchestrator = None
