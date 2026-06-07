"""Canonical ADK agent — **Transaction Enrichment** (AML stage 2).

Single source of truth: reused by the FastAPI orchestrator
(``backend.aml.agents.transaction_enrichment.TransactionEnrichmentAgent``) and
by ``adk web backend/aml/agents/stages`` (select ``transaction_enrichment``).

Hybrid ADK web: include a case number in the user message. Requires a completed
Initial Assessment on the case. Opens ``PARTIES_VERIFIED`` gate on completion.
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
from backend.aml.agents.prompts import TRANSACTION_ENRICHMENT_INSTRUCTION  # noqa: E402
from backend.aml.agents.runtime.adk_callbacks import hybrid_callbacks  # noqa: E402
from backend.aml.agents.runtime.orchestrator_tool import (  # noqa: E402
    trigger_transaction_enrichment_via_orchestrator,
)
from backend.aml.agents.tools import adk_tools_named  # noqa: E402
from backend.aml.models.enums import AgentName  # noqa: E402

TOOL_NAMES = ["neo4j_hop_traversal", "record_evidence", "record_party"]

_before, _before_model, _after = hybrid_callbacks(AgentName.TRANSACTION_ENRICHMENT)
_ORCHESTRATOR_TOOL = FunctionTool(
    func=trigger_transaction_enrichment_via_orchestrator
)

root_agent = build_llm_agent(
    name="transaction_enrichment",
    instruction=TRANSACTION_ENRICHMENT_INSTRUCTION,
    model=get_settings().gemini.generation_model,
    tools=adk_tools_named(TOOL_NAMES),
    temperature=0.1,
    description=(
        "AML stage 2 — Transaction Enrichment. ADK web: send a case number "
        "with IA complete (e.g. Run transaction enrichment for AML-SERVICES-SWIFT-2026-005)."
    ),
    before_agent_callback=_before,
    after_agent_callback=_after,
    before_model_callback=_before_model,
    extra_tools=[_ORCHESTRATOR_TOOL],
)
