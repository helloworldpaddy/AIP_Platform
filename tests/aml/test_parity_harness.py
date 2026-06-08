"""Parity harness — orchestrator surfaces agree on run contracts (Sprint 5)."""

from __future__ import annotations

import pytest

from backend.aml.agents.runtime.orchestrator_client import reset_runtime_orchestrator
from backend.aml.agents.runtime.orchestrator_invoke import invoke_orchestrator_stage
from backend.aml.agents.runtime.parity import assert_trigger_parity, parity_report
from backend.aml.db.client import AmlDbClient
from backend.aml.models.enums import AgentName, CasePriority, GateStatus, LineOfBusiness
from backend.aml.models.state import CaseCreate
from backend.aml.orchestrator import Orchestrator

pytestmark = pytest.mark.integration


async def _create_case(db: AmlDbClient, *, case_number: str):
    dto = CaseCreate(
        case_number=case_number,
        alert_type="TRANSACTION_MONITORING",
        alert_payload={"rule_id": "TM-001"},
        subject_party_id="P-SUBJECT-001",
        subject_party_name="Jane Doe",
        line_of_business=LineOfBusiness.RETAIL_BANKING,
        priority=CasePriority.HIGH,
        assigned_analyst_id="analyst.test",
        created_by="seed",
    )
    async with db.transaction() as repos:
        return await repos.cases.create(dto)


@pytest.mark.asyncio
async def test_direct_trigger_matches_invoke_helper(
    aml_db: AmlDbClient,
    orchestrator: Orchestrator,
    case_number: str,
    monkeypatch,
) -> None:
    """``invoke_orchestrator_stage`` and ``Orchestrator.trigger_agent`` parity."""
    monkeypatch.setenv("AML_ADK_MODE", "hybrid")
    monkeypatch.setattr("backend.aml.db.client._singleton", aml_db)
    monkeypatch.setattr(
        "backend.aml.agents.runtime.orchestrator_invoke.build_runtime_orchestrator",
        lambda: orchestrator,
    )
    reset_runtime_orchestrator()
    case = await _create_case(aml_db, case_number=case_number)

    direct = await orchestrator.trigger_agent(
        case_id=case.id,
        agent_name=AgentName.INITIAL_ASSESSMENT,
        triggered_by="parity.test",
        extra_input={"source": "direct"},
    )

    case2 = await _create_case(aml_db, case_number=f"{case_number}-B")
    via_helper = await invoke_orchestrator_stage(
        case_number=case2.case_number,
        agent_name=AgentName.INITIAL_ASSESSMENT,
        triggered_by="parity.test",
        extra_input={"source": "invoke_helper"},
    )

    for run in (direct, via_helper):
        assert_trigger_parity(run, agent=AgentName.INITIAL_ASSESSMENT)
        report = parity_report(run)
        assert report["agent"] == AgentName.INITIAL_ASSESSMENT.value
        assert report["requires_review"] is True
        assert "risk_score" in report["output_keys"]


@pytest.mark.asyncio
async def test_all_stub_stages_satisfy_parity_contract(
    aml_db: AmlDbClient,
    orchestrator: Orchestrator,
    case_number: str,
) -> None:
    """Walk each stub stage once and validate output contract keys."""
    case = await _create_case(aml_db, case_number=case_number)

    ia = await orchestrator.trigger_agent(
        case_id=case.id,
        agent_name=AgentName.INITIAL_ASSESSMENT,
        triggered_by="parity.test",
    )
    assert_trigger_parity(ia, agent=AgentName.INITIAL_ASSESSMENT)
    await orchestrator.approve_run(run_id=ia.id, analyst_id="analyst.test")

    te = await orchestrator.trigger_agent(
        case_id=case.id,
        agent_name=AgentName.TRANSACTION_ENRICHMENT,
        triggered_by="parity.test",
    )
    assert_trigger_parity(te, agent=AgentName.TRANSACTION_ENRICHMENT)
    await orchestrator.approve_run(run_id=te.id, analyst_id="analyst.test")

    state = await orchestrator.get_state(case.id)
    open_gates = [g for g in state.gates if g.gate_name == "PARTIES_VERIFIED"]
    async with aml_db.transaction() as repos:
        for party in state.parties:
            await repos.parties.mark_verified(
                party_id=party.id, analyst_id="analyst.test"
            )

    await orchestrator.resolve_gate(
        gate_id=open_gates[0].id,
        status=GateStatus.APPROVED,
        analyst_id="analyst.test",
    )

    dd = await orchestrator.trigger_agent(
        case_id=case.id,
        agent_name=AgentName.DUE_DILIGENCE,
        triggered_by="parity.test",
    )
    assert_trigger_parity(dd, agent=AgentName.DUE_DILIGENCE)
    await orchestrator.approve_run(run_id=dd.id, analyst_id="analyst.test")

    ca = await orchestrator.trigger_agent(
        case_id=case.id,
        agent_name=AgentName.CASE_ANALYSIS,
        triggered_by="parity.test",
    )
    assert_trigger_parity(ca, agent=AgentName.CASE_ANALYSIS)
