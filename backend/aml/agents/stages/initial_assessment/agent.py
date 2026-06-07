"""Canonical ADK agent — **Initial Assessment** (AML stage 1).

Single source of truth: reused by the FastAPI orchestrator
(``backend.aml.agents.initial_assessment.InitialAssessmentAgent``) and by
``adk web backend/aml/agents/stages`` (select ``initial_assessment``).

Hybrid ADK web: include a case number in the user message (e.g.
``AML-SERVICES-SWIFT-2026-005``). Callbacks resolve the case, assemble the
orchestrator-equivalent prompt, bind real DB tool context, and persist the run.
Optional tool ``trigger_initial_assessment_via_orchestrator`` runs the full
production Orchestrator path for parity testing.
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
from backend.aml.agents.prompts import INITIAL_ASSESSMENT_INSTRUCTION  # noqa: E402
from backend.aml.agents.runtime.adk_callbacks import hybrid_callbacks  # noqa: E402
from backend.aml.agents.runtime.orchestrator_tool import (  # noqa: E402
    trigger_initial_assessment_via_orchestrator,
)
from backend.aml.agents.tools import adk_tools_named  # noqa: E402
from backend.aml.models.enums import AgentName  # noqa: E402

TOOL_NAMES = ["policy_rag_search", "record_evidence"]

_before, _before_model, _after = hybrid_callbacks(AgentName.INITIAL_ASSESSMENT)
_ORCHESTRATOR_TOOL = FunctionTool(func=trigger_initial_assessment_via_orchestrator)

root_agent = build_llm_agent(
    name="initial_assessment",
    instruction=INITIAL_ASSESSMENT_INSTRUCTION,
    model=get_settings().gemini.generation_model,
    tools=adk_tools_named(TOOL_NAMES),
    temperature=0.1,
    description=(
        "AML stage 1 — Initial Assessment. ADK web: send a case number "
        "(e.g. AML-SERVICES-SWIFT-2026-005) to run end-to-end with real DB tools."
    ),
    before_agent_callback=_before,
    after_agent_callback=_after,
    before_model_callback=_before_model,
    extra_tools=[_ORCHESTRATOR_TOOL],
)
