"""Tool functions exposed to the LLM.

Each tool is a plain async Python callable (so it can be unit-tested or
re-used outside an LLM context).  Two parallel registrations exist:

* `ToolSpec` (in `registry.py`) — the legacy/test-friendly form, retained
  for any code that still wants to introspect parameters as JSON Schema.
* `FunctionTool` (in `ADK_TOOLS`) — what the AML agents actually pass to
  `google.adk.agents.LlmAgent`.  ADK derives its function declaration from
  the callable's signature + docstring.

`ADK_TOOLS` is built from the **context-aware** wrappers in
`context_aware.py`: when the orchestrator binds an `AgentToolContext` they run
the real implementations (DB writes + provider calls); standalone (`adk web`)
they return safe stubs.  This is the single tool set used by both surfaces.

Per-call context (case_id, agent_run_id, repos) is delivered through the
`agents.context` contextvar — set by the orchestrator before each agent
invocation, read inside the tool.
"""

from __future__ import annotations

from google.adk.tools import FunctionTool

from . import context_aware
from .data_tools import external_search, kyc_lookup, neo4j_hop_traversal
from .policy_tool import policy_rag_search
from .recorder_tools import record_evidence, record_party
from .registry import ToolFn, all_tools

ADK_TOOLS: dict[str, FunctionTool] = {
    "policy_rag_search": FunctionTool(func=context_aware.policy_rag_search),
    "kyc_lookup": FunctionTool(func=context_aware.kyc_lookup),
    "neo4j_hop_traversal": FunctionTool(func=context_aware.neo4j_hop_traversal),
    "external_search": FunctionTool(func=context_aware.external_search),
    "record_evidence": FunctionTool(func=context_aware.record_evidence),
    "record_party": FunctionTool(func=context_aware.record_party),
}


def validate_adk_tool_names(names: list[str]) -> None:
    """Ensure every name resolves to a :class:`google.adk.tools.FunctionTool`.

    Call at agent construction time so typos fail fast instead of at runtime
    inside ``LlmAgent``.
    """
    missing = [n for n in names if n not in ADK_TOOLS]
    if missing:
        known = ", ".join(sorted(ADK_TOOLS))
        raise ValueError(
            f"Unknown ADK tool name(s): {missing}. "
            f"Register in ADK_TOOLS or fix tool_names. Known: {known}"
        )


def adk_tools_named(names: list[str]) -> list[FunctionTool]:
    """Resolve tool names to ADK ``FunctionTool`` instances (declaration order)."""
    validate_adk_tool_names(names)
    return [ADK_TOOLS[n] for n in names]


__all__ = [
    "external_search",
    "kyc_lookup",
    "neo4j_hop_traversal",
    "policy_rag_search",
    "record_evidence",
    "record_party",
    "ToolFn",
    "all_tools",
    "ADK_TOOLS",
    "adk_tools_named",
    "validate_adk_tool_names",
]
