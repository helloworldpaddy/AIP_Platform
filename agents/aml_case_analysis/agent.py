"""ADK Web entry for **Case Analysis** (stage 4). See ``aml_initial_assessment/agent.py`` for how to run ``adk web``."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from google.adk.tools import FunctionTool  # noqa: E402

from agents.rag_agent.config.settings import get_settings  # noqa: E402
from agents.rag_agent.utils.logging_config import configure_logging  # noqa: E402

from backend.aml.agents.adk_runner import build_llm_agent  # noqa: E402
from backend.aml.agents.adk_web_tools import record_evidence_adk_web  # noqa: E402
from backend.aml.agents.prompts import CASE_ANALYSIS_INSTRUCTION  # noqa: E402

configure_logging()

root_agent = build_llm_agent(
    name="aml_case_analysis",
    instruction=CASE_ANALYSIS_INSTRUCTION,
    model=get_settings().gemini.generation_model,
    tools=[FunctionTool(func=record_evidence_adk_web)],
    temperature=0.1,
    description="AML stage 4 — Case Analysis & narrative (ADK Web preview).",
)
