"""Canonical ADK agent — **Transaction Enrichment** (AML stage 2).

Single source of truth: reused by the FastAPI orchestrator
(``backend.aml.agents.transaction_enrichment.TransactionEnrichmentAgent``) and
by ``adk web backend/aml/agents/stages`` (select ``transaction_enrichment``).
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[5]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agents.rag_agent.config.settings import get_settings  # noqa: E402

from backend.aml.agents.adk_runner import build_llm_agent  # noqa: E402
from backend.aml.agents.prompts import TRANSACTION_ENRICHMENT_INSTRUCTION  # noqa: E402
from backend.aml.agents.tools import adk_tools_named  # noqa: E402

TOOL_NAMES = ["neo4j_hop_traversal", "record_evidence", "record_party"]

root_agent = build_llm_agent(
    name="transaction_enrichment",
    instruction=TRANSACTION_ENRICHMENT_INSTRUCTION,
    model=get_settings().gemini.generation_model,
    tools=adk_tools_named(TOOL_NAMES),
    temperature=0.1,
    description="AML stage 2 — Transaction Enrichment (graph hops + parties).",
)
