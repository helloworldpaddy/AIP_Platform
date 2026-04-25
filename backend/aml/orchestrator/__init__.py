"""Workflow engine: drives stage transitions, enforces gates, records CoT."""

from .service import GateBlocked, Orchestrator
from .transitions import (
    NEXT_STAGE,
    STAGE_FOR_AGENT,
    STAGE_ORDER,
    is_terminal_status,
    stage_lt,
)

__all__ = [
    "GateBlocked",
    "Orchestrator",
    "NEXT_STAGE",
    "STAGE_FOR_AGENT",
    "STAGE_ORDER",
    "is_terminal_status",
    "stage_lt",
]
