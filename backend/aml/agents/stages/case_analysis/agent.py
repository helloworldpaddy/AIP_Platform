"""Canonical ADK agent — **Case Analysis** (AML stage 4).

Single source of truth: reused by the FastAPI orchestrator
(``backend.aml.agents.case_analysis.CaseAnalysisAgent``) and by
``adk web backend/aml/agents/stages`` (select ``case_analysis``).
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[5]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agents.rag_agent.config.settings import get_settings  # noqa: E402

from backend.aml.agents.adk_runner import build_llm_agent  # noqa: E402
from backend.aml.agents.prompts import CASE_ANALYSIS_INSTRUCTION  # noqa: E402
from backend.aml.agents.tools import adk_tools_named  # noqa: E402

TOOL_NAMES = ["record_evidence"]

root_agent = build_llm_agent(
    name="case_analysis",
    instruction=CASE_ANALYSIS_INSTRUCTION,
    model=get_settings().gemini.generation_model,
    tools=adk_tools_named(TOOL_NAMES),
    temperature=0.1,
    description="AML stage 4 — Case Analysis & narrative.",
)
