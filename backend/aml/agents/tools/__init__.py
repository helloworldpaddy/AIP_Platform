"""Tool functions exposed to the LLM.

Each tool is a plain async Python callable (so it can be unit-tested or
re-used outside an LLM context).  Two parallel registrations exist:

* `ToolSpec` (in `registry.py`) — the legacy/test-friendly form, retained
  for any code that still wants to introspect parameters as JSON Schema.
* `FunctionTool` (in `ADK_TOOLS`) — what the AML agents actually pass to
  `google.adk.agents.LlmAgent`.  ADK derives its function declaration from
  the callable's signature + docstring.

Per-call context (case_id, agent_run_id, repos) is delivered through the
`agents.context` contextvar — set by the orchestrator before each agent
invocation, read inside the tool.
"""

from __future__ import annotations

from google.adk.tools import FunctionTool

from .data_tools import external_search, kyc_lookup, neo4j_hop_traversal
from .policy_tool import policy_rag_search
from .recorder_tools import record_evidence, record_party
from .registry import ToolFn, all_tools

ADK_TOOLS: dict[str, FunctionTool] = {
    "policy_rag_search": FunctionTool(func=policy_rag_search),
    "kyc_lookup": FunctionTool(func=kyc_lookup),
    "neo4j_hop_traversal": FunctionTool(func=neo4j_hop_traversal),
    "external_search": FunctionTool(func=external_search),
    "record_evidence": FunctionTool(func=record_evidence),
    "record_party": FunctionTool(func=record_party),
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
