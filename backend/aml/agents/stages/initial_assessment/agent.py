"""Canonical ADK agent — **Initial Assessment** (AML stage 1).

Single source of truth: reused by the FastAPI orchestrator
(``backend.aml.agents.initial_assessment.InitialAssessmentAgent``) and by
``adk web backend/aml/agents/stages`` (select ``initial_assessment``).

Tools are the context-aware set in ``backend.aml.agents.tools``: real DB writes
when the orchestrator binds a context, safe stubs in standalone ``adk web``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Repo root on path so absolute imports work whether this module is loaded as
# top-level ``initial_assessment`` (adk web) or as
# ``backend.aml.agents.stages.initial_assessment`` (orchestrator).
_ROOT = Path(__file__).resolve().parents[5]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agents.rag_agent.config.settings import get_settings  # noqa: E402

from backend.aml.agents.adk_runner import build_llm_agent  # noqa: E402
from backend.aml.agents.prompts import INITIAL_ASSESSMENT_INSTRUCTION  # noqa: E402
from backend.aml.agents.tools import adk_tools_named  # noqa: E402

#: Tool names (keys into ``backend.aml.agents.tools.ADK_TOOLS``).
TOOL_NAMES = ["policy_rag_search", "record_evidence"]

root_agent = build_llm_agent(
    name="initial_assessment",
    instruction=INITIAL_ASSESSMENT_INSTRUCTION,
    model=get_settings().gemini.generation_model,
    tools=adk_tools_named(TOOL_NAMES),
    temperature=0.1,
    description="AML stage 1 — Initial Assessment (policy RAG + evidence).",
)
