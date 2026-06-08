"""Unit tests for agent transport config and adapter factory."""

from __future__ import annotations

import pytest

from backend.aml.agents.adapters.a2a import A2aAdapter
from backend.aml.agents.adapters.factory import build_execution_ports
from backend.aml.agents.adapters.in_process import InProcessAdapter
from backend.aml.config.agent_transport import (
    AgentTransport,
    AgentTransportConfig,
    load_agent_transport_config,
)
from backend.aml.models.enums import AgentName, AgentRunStatus
from tests.aml.stubs import (
    StubCaseAnalysisAgent,
    StubDueDiligenceAgent,
    StubInitialAssessmentAgent,
    StubTransactionEnrichmentAgent,
)


@pytest.fixture()
def stub_agents():
    return {
        AgentName.INITIAL_ASSESSMENT: StubInitialAssessmentAgent(),
        AgentName.TRANSACTION_ENRICHMENT: StubTransactionEnrichmentAgent(),
        AgentName.DUE_DILIGENCE: StubDueDiligenceAgent(),
        AgentName.CASE_ANALYSIS: StubCaseAnalysisAgent(),
    }


def test_load_config_defaults_in_process(monkeypatch):
    monkeypatch.delenv("AML_AGENT_TRANSPORT_DEFAULT", raising=False)
    for agent in AgentName:
        monkeypatch.delenv(f"AML_AGENT_TRANSPORT_{agent.value}", raising=False)
        monkeypatch.delenv(f"AML_A2A_{agent.value}_URL", raising=False)

    config = load_agent_transport_config()
    assert config.default_transport == AgentTransport.IN_PROCESS
    for agent in AgentName:
        assert config.transport_for(agent) == AgentTransport.IN_PROCESS


def test_load_config_stage_override(monkeypatch):
    monkeypatch.setenv("AML_AGENT_TRANSPORT_DEFAULT", "in_process")
    monkeypatch.setenv("AML_AGENT_TRANSPORT_DUE_DILIGENCE", "a2a")
    monkeypatch.setenv(
        "AML_A2A_DUE_DILIGENCE_URL",
        "http://localhost:8103/.well-known/agent-card.json",
    )

    config = load_agent_transport_config()
    assert config.transport_for(AgentName.DUE_DILIGENCE) == AgentTransport.A2A
    assert config.transport_for(AgentName.INITIAL_ASSESSMENT) == AgentTransport.IN_PROCESS
    assert "http://localhost:8103" in config.a2a_endpoint(AgentName.DUE_DILIGENCE)


def test_factory_all_in_process(stub_agents):
    config = AgentTransportConfig(default_transport=AgentTransport.IN_PROCESS)
    ports = build_execution_ports(stub_agents, config)
    assert len(ports) == 4
    for port in ports.values():
        assert isinstance(port, InProcessAdapter)


def test_factory_a2a_requires_url(stub_agents):
    config = AgentTransportConfig(
        default_transport=AgentTransport.IN_PROCESS,
        stage_transport={AgentName.CASE_ANALYSIS: AgentTransport.A2A},
    )
    with pytest.raises(ValueError, match="AML_A2A_CASE_ANALYSIS_URL"):
        build_execution_ports(stub_agents, config)


def test_factory_a2a_stub_when_configured(stub_agents):
    config = AgentTransportConfig(
        default_transport=AgentTransport.IN_PROCESS,
        stage_transport={AgentName.INITIAL_ASSESSMENT: AgentTransport.A2A},
        a2a_agent_card_urls={
            AgentName.INITIAL_ASSESSMENT: "http://ia:8101/.well-known/agent-card.json",
        },
    )
    ports = build_execution_ports(stub_agents, config)
    assert isinstance(ports[AgentName.INITIAL_ASSESSMENT], A2aAdapter)
    assert isinstance(ports[AgentName.DUE_DILIGENCE], InProcessAdapter)


def test_orchestrator_mints_tool_gateway_for_a2a(stub_agents, monkeypatch):
    from uuid import uuid4

    from datetime import datetime, timezone

    from backend.aml.agents.adapters.factory import build_execution_ports
    from backend.aml.agents.initial_assessment import InitialAssessmentAgent
    from backend.aml.agents.tool_gateway import build_tool_gateway_service
    from backend.aml.config.agent_transport import AgentTransportConfig
    from backend.aml.db.client import AmlDbClient
    from backend.aml.models.state import AgentRun
    from backend.aml.orchestrator import Orchestrator

    monkeypatch.setenv("AML_TOOL_GATEWAY_SECRET", "pytest-tool-gateway-secret")
    agents = dict(stub_agents)
    agents[AgentName.INITIAL_ASSESSMENT] = InitialAssessmentAgent()

    config = AgentTransportConfig(
        default_transport=AgentTransport.IN_PROCESS,
        stage_transport={AgentName.INITIAL_ASSESSMENT: AgentTransport.A2A},
        a2a_agent_card_urls={
            AgentName.INITIAL_ASSESSMENT: "http://ia:8101/.well-known/agent-card.json",
        },
    )
    orch = Orchestrator(
        AmlDbClient(),
        agents=agents,
        execution_ports=build_execution_ports(agents, config),
        transport_config=config,
        tool_gateway=build_tool_gateway_service(AmlDbClient()),
    )
    now = datetime.now(timezone.utc)
    run = AgentRun(
        id=uuid4(),
        case_id=uuid4(),
        agent=AgentName.INITIAL_ASSESSMENT,
        attempt=1,
        idempotency_key="k",
        input_payload={},
        status=AgentRunStatus.RUNNING,
        created_at=now,
        updated_at=now,
    )
    spec = orch._mint_tool_gateway(
        agent=agents[AgentName.INITIAL_ASSESSMENT],
        agent_name=AgentName.INITIAL_ASSESSMENT,
        case_id=run.case_id,
        run=run,
    )
    assert spec is not None
    assert spec.transport == "http"
    assert "record_evidence" in spec.allowed_tools
    assert spec.token
