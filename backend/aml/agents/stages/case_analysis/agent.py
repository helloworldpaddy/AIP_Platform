"""Canonical ADK agent — **Case Analysis** (AML stage 4).

Single source of truth: reused by the FastAPI orchestrator
(``backend.aml.agents.case_analysis.CaseAnalysisAgent``) and by
``adk web backend/aml/agents/stages`` (select ``case_analysis``).

Hybrid ADK web: include a case number in the user message. Requires prior
stages complete; persists draft narrative on success.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[5]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agents.rag_agent.config.settings import get_settings  # noqa: E402
from google.adk.tools import FunctionTool  # noqa: E402

from backend.aml.agents.adk_runner import build_llm_agent  # noqa: E402
from backend.aml.agents.prompts import CASE_ANALYSIS_INSTRUCTION  # noqa: E402
from backend.aml.agents.runtime.adk_callbacks import hybrid_callbacks  # noqa: E402
from backend.aml.agents.runtime.orchestrator_tool import (  # noqa: E402
    trigger_case_analysis_via_orchestrator,
)
from backend.aml.agents.tools import adk_tools_named  # noqa: E402
from backend.aml.models.enums import AgentName  # noqa: E402

TOOL_NAMES = ["record_evidence"]

_before, _before_model, _after = hybrid_callbacks(AgentName.CASE_ANALYSIS)
_ORCHESTRATOR_TOOL = FunctionTool(func=trigger_case_analysis_via_orchestrator)

root_agent = build_llm_agent(
    name="case_analysis",
    instruction=CASE_ANALYSIS_INSTRUCTION,
    model=get_settings().gemini.generation_model,
    tools=adk_tools_named(TOOL_NAMES),
    temperature=0.1,
    description=(
        "AML stage 4 — Case Analysis. ADK web: send a case number with prior "
        "stages complete (e.g. Run case analysis for AML-SERVICES-SWIFT-2026-005)."
    ),
    before_agent_callback=_before,
    after_agent_callback=_after,
    before_model_callback=_before_model,
    extra_tools=[_ORCHESTRATOR_TOOL],
)
