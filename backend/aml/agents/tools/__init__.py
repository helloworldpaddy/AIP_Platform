"""Tool functions exposed to the LLM.

Tools are plain async Python callables registered as Gemini function
declarations by `gemini_runner`.  The same callables can also be wrapped
by ADK's `FunctionTool` for use outside the orchestrator (e.g. `adk web`).

Per-call context (case_id, agent_run_id, repos) is delivered via
`agents.context.current_tool_context()` — set by the orchestrator before
each agent invocation.
"""

from .data_tools import external_search, kyc_lookup, neo4j_hop_traversal
from .policy_tool import policy_rag_search
from .recorder_tools import record_evidence, record_party
from .registry import ToolFn, all_tools

__all__ = [
    "external_search",
    "kyc_lookup",
    "neo4j_hop_traversal",
    "policy_rag_search",
    "record_evidence",
    "record_party",
    "ToolFn",
    "all_tools",
]
