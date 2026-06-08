"""Smoke tests for A2A host agent construction (no LLM)."""

from __future__ import annotations

from backend.aml.agents.a2a.host_agent import build_a2a_host_agent
from backend.aml.models.enums import AgentName


def test_build_a2a_host_agents_for_all_stages():
    for agent_name in AgentName:
        agent = build_a2a_host_agent(agent_name)
        assert agent.name in {
            "initial_assessment",
            "transaction_enrichment",
            "due_diligence",
            "case_analysis",
        }
        assert len(agent.tools) >= 1
