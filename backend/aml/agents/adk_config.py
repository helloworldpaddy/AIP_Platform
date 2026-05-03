"""ADK 1.x identifiers for AML investigation agents.

Uses the Google ADK **tool-using LLM** stack: ``LlmAgent`` + ``FunctionTool``
+ ``InMemoryRunner`` (see ``adk_runner.py``).  The generic ``Agent`` type is
not used — every stage is an ``LlmAgent``.

FastAPI and the React UI invoke ``Orchestrator`` only; they do not import
``google.adk``.
"""

from __future__ import annotations

# Session namespace for InMemoryRunner + session service (one app, many cases).
AML_ADK_APP_NAME: str = "aml"

# Orchestrator identity for ADK runner sessions (not an end-user analyst id).
AML_ADK_RUNNER_USER_ID: str = "orchestrator"
