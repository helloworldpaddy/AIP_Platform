"""Shared runtime for ADK web ↔ orchestrator hybrid execution.

ADK web stages can resolve a case by number, assemble the same prompt the
orchestrator uses, bind real DB tool context, and persist results through the
same audit / agent_runs path as production triggers.
"""

from .bootstrap import ensure_runtime_ready
from .case_resolver import parse_case_number

__all__ = ["ensure_runtime_ready", "parse_case_number"]
