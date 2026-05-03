"""
ADK Web entry for **Initial Assessment** (stage 1).

Run from the ``agents/`` directory (sibling to ``rag_agent``)::

    cd agents
    adk web --port 8000

Select ``aml_initial_assessment`` in the UI.  Tools use
``backend.aml.agents.adk_web_tools`` so the chat works without the FastAPI
orchestrator; ledger writes are stubbed unless you embed this agent in a
context-aware host.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Repo root must be on path for ``backend.aml`` and ``agents`` packages.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from google.adk.tools import FunctionTool  # noqa: E402

from agents.rag_agent.config.settings import get_settings  # noqa: E402
from agents.rag_agent.utils.logging_config import configure_logging  # noqa: E402

from backend.aml.agents.adk_runner import build_llm_agent  # noqa: E402
from backend.aml.agents.adk_web_tools import (  # noqa: E402
    policy_rag_search_adk_web,
    record_evidence_adk_web,
)
from backend.aml.agents.prompts import INITIAL_ASSESSMENT_INSTRUCTION  # noqa: E402

configure_logging()

root_agent = build_llm_agent(
    name="aml_initial_assessment",
    instruction=INITIAL_ASSESSMENT_INSTRUCTION,
    model=get_settings().gemini.generation_model,
    tools=[
        FunctionTool(func=policy_rag_search_adk_web),
        FunctionTool(func=record_evidence_adk_web),
    ],
    temperature=0.1,
    description="AML stage 1 — Initial Assessment (policy RAG + evidence; ADK Web preview).",
)
