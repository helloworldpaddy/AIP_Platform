"""Canonical ADK agent — **Due Diligence** (AML stage 3).

Single source of truth: reused by the FastAPI orchestrator
(``backend.aml.agents.due_diligence.DueDiligenceAgent``) and by
``adk web backend/aml/agents/stages`` (select ``due_diligence``).

Hybrid ADK web: include a case number in the user message. Requires
``PARTIES_VERIFIED`` gate resolved and all parties verified.
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
from backend.aml.agents.prompts import DUE_DILIGENCE_INSTRUCTION  # noqa: E402
from backend.aml.agents.runtime.adk_callbacks import hybrid_callbacks  # noqa: E402
from backend.aml.agents.runtime.orchestrator_tool import (  # noqa: E402
    trigger_due_diligence_via_orchestrator,
)
from backend.aml.agents.tools import adk_tools_named  # noqa: E402
from backend.aml.models.enums import AgentName  # noqa: E402

TOOL_NAMES = ["kyc_lookup", "external_search", "record_evidence"]

_before, _before_model, _after = hybrid_callbacks(AgentName.DUE_DILIGENCE)
_ORCHESTRATOR_TOOL = FunctionTool(func=trigger_due_diligence_via_orchestrator)

root_agent = build_llm_agent(
    name="due_diligence",
    instruction=DUE_DILIGENCE_INSTRUCTION,
    model=get_settings().gemini.generation_model,
    tools=adk_tools_named(TOOL_NAMES),
    temperature=0.1,
    description=(
        "AML stage 3 — Due Diligence. ADK web: send a case number after "
        "PARTIES_VERIFIED gate is cleared (e.g. Run due diligence for AML-SERVICES-SWIFT-2026-005)."
    ),
    before_agent_callback=_before,
    after_agent_callback=_after,
    before_model_callback=_before_model,
    extra_tools=[_ORCHESTRATOR_TOOL],
)
