"""Agent contracts + AML workflow stages (ADK ``LlmAgent`` under the hood).

The orchestrator depends only on :class:`base.BaseAgent`.  ADK types stay inside
:class:`llm_agent_base.LlmDrivenAgent` and :mod:`adk_runner`.
"""

from .adk_config import AML_ADK_APP_NAME, AML_ADK_RUNNER_USER_ID
from .base import AgentContext, AgentResult, BaseAgent, GateSpec

__all__ = [
    "AML_ADK_APP_NAME",
    "AML_ADK_RUNNER_USER_ID",
    "AgentContext",
    "AgentResult",
    "BaseAgent",
    "GateSpec",
    "build_default_agents",
]


def __getattr__(name: str):
    """Lazily expose ``build_default_agents`` so importing this package (or a
    stage's ``adk_runner``/``tools`` via ``adk web``) does not eagerly pull the
    registry and every stage subclass."""
    if name == "build_default_agents":
        from .registry import build_default_agents

        return build_default_agents
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
