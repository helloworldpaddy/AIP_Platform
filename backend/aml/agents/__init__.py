"""Agent contracts + concrete agent implementations.

The orchestrator depends only on `BaseAgent`, never on a specific ADK class,
so individual agents can be swapped (e.g. Gemini ↔ stub for tests) without
touching the workflow.
"""

from .base import AgentContext, AgentResult, BaseAgent, GateSpec
from .registry import build_default_agents

__all__ = [
    "AgentContext",
    "AgentResult",
    "BaseAgent",
    "GateSpec",
    "build_default_agents",
]
