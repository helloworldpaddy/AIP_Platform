"""Default :class:`base.BaseAgent` registry for :class:`Orchestrator`.

Each value is an AML workflow stage backed by :class:`llm_agent_base.LlmDrivenAgent`
(ADK ``LlmAgent`` plus ``FunctionTool`` instances).  Importing
this module loads tool modules so legacy :class:`tools.registry.ToolSpec`
registration runs before any trigger.

The HTTP surface remains ``POST /cases/{id}/agents/{agent}/trigger`` — the
frontend does not call ADK directly.
"""

from __future__ import annotations

from .base import BaseAgent
from .case_analysis import CaseAnalysisAgent
from .due_diligence import DueDiligenceAgent
from .initial_assessment import InitialAssessmentAgent
from .transaction_enrichment import TransactionEnrichmentAgent
from .tools import (  # noqa: F401 — import populates tool registry
    external_search,
    kyc_lookup,
    neo4j_hop_traversal,
    policy_rag_search,
    record_evidence,
    record_party,
)
from ..models.enums import AgentName


def build_default_agents() -> dict[AgentName, BaseAgent]:
    """Wire one instance of every agent.

    Side note: providers for the data tools (KYC, Graph, Search) MUST be
    configured via `set_kyc_provider` / `set_graph_provider` /
    `set_search_provider` before any agent that uses them is invoked.
    """
    return {
        AgentName.INITIAL_ASSESSMENT: InitialAssessmentAgent(),
        AgentName.TRANSACTION_ENRICHMENT: TransactionEnrichmentAgent(),
        AgentName.DUE_DILIGENCE: DueDiligenceAgent(),
        AgentName.CASE_ANALYSIS: CaseAnalysisAgent(),
    }
