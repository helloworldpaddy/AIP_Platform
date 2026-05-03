"""End-to-end orchestrator walkthrough against a real Postgres.

Drives the full four-agent flow with deterministic stub agents and the
actual hash-chained audit pipeline.  The test asserts that:

    1. Initial assessment runs and parks in AWAITING_REVIEW
    2. Approval advances the stage to TRANSACTION_ENRICHMENT
    3. Transaction enrichment opens the PARTIES_VERIFIED gate
    4. Triggering due diligence while the gate is open raises GateBlocked
    5. After verifying parties + resolving the gate, due diligence proceeds
    6. Case analysis drafts a narrative
    7. Submitting the narrative locks the case
    8. The audit chain remains valid throughout
"""

from __future__ import annotations

import pytest

from backend.aml.db.client import AmlDbClient
from backend.aml.models.enums import (
    AgentName,
    AuditEventType,
    CasePriority,
    CaseStage,
    CaseStatus,
    GateStatus,
    LineOfBusiness,
)
from backend.aml.models.state import CaseCreate
from backend.aml.orchestrator import GateBlocked, Orchestrator

pytestmark = pytest.mark.integration


async def _create_case(db: AmlDbClient, *, case_number: str):
    dto = CaseCreate(
        case_number=case_number,
        alert_type="TRANSACTION_MONITORING",
        alert_payload={"rule_id": "TM-001", "amount": 250_000},
        subject_party_id="P-SUBJECT-001",
        subject_party_name="Jane Doe",
        line_of_business=LineOfBusiness.RETAIL_BANKING,
        priority=CasePriority.HIGH,
        assigned_analyst_id="analyst.test",
        created_by="seed",
    )
    async with db.transaction() as repos:
        return await repos.cases.create(dto)


async def test_full_walkthrough(
    aml_db: AmlDbClient,
    orchestrator: Orchestrator,
    case_number: str,
) -> None:
    case = await _create_case(aml_db, case_number=case_number)

    # ------------- 1. Initial assessment ------------------------------------
    run = await orchestrator.trigger_agent(
        case_id=case.id,
        agent_name=AgentName.INITIAL_ASSESSMENT,
        triggered_by="analyst.test",
    )
    assert run.status.value == "AWAITING_REVIEW"
    assert run.output_payload["risk_score"] == 72

    # ------------- 2. Approval advances the stage ---------------------------
    await orchestrator.approve_run(run_id=run.id, analyst_id="analyst.test")

    state = await orchestrator.get_state(case.id)
    assert state.case.current_stage == CaseStage.TRANSACTION_ENRICHMENT
    assert state.case.status == CaseStatus.IN_PROGRESS

    # ------------- 3. Transaction enrichment opens the gate -----------------
    txn_run = await orchestrator.trigger_agent(
        case_id=case.id,
        agent_name=AgentName.TRANSACTION_ENRICHMENT,
        triggered_by="analyst.test",
    )
    assert txn_run.status.value == "AWAITING_REVIEW"

    state = await orchestrator.get_state(case.id)
    assert len(state.parties) == 2
    open_gates = [g for g in state.gates if g.status == GateStatus.OPEN_REQUIRED]
    assert len(open_gates) == 1
    assert open_gates[0].gate_name == "PARTIES_VERIFIED"
    assert open_gates[0].blocks_agent == AgentName.DUE_DILIGENCE

    await orchestrator.approve_run(run_id=txn_run.id, analyst_id="analyst.test")

    # ------------- 4. Due diligence is blocked by the open gate -------------
    with pytest.raises(GateBlocked):
        await orchestrator.trigger_agent(
            case_id=case.id,
            agent_name=AgentName.DUE_DILIGENCE,
            triggered_by="analyst.test",
        )

    # ------------- 5. Verify parties + resolve gate, then DD runs -----------
    async with aml_db.transaction() as repos:
        for party in state.parties:
            await repos.parties.mark_verified(
                party_id=party.id, analyst_id="analyst.test"
            )

    gate = open_gates[0]
    await orchestrator.resolve_gate(
        gate_id=gate.id,
        status=GateStatus.APPROVED,
        analyst_id="analyst.test",
        notes="All counterparties verified.",
    )

    dd_run = await orchestrator.trigger_agent(
        case_id=case.id,
        agent_name=AgentName.DUE_DILIGENCE,
        triggered_by="analyst.test",
    )
    assert dd_run.status.value == "AWAITING_REVIEW"
    assert dd_run.output_payload["sanctions_hits"] == 0
    await orchestrator.approve_run(run_id=dd_run.id, analyst_id="analyst.test")

    # ------------- 6. Case analysis drafts a narrative ----------------------
    ca_run = await orchestrator.trigger_agent(
        case_id=case.id,
        agent_name=AgentName.CASE_ANALYSIS,
        triggered_by="analyst.test",
    )
    assert ca_run.status.value == "AWAITING_REVIEW"

    state = await orchestrator.get_state(case.id)
    assert len(state.narratives) == 1
    narrative = state.narratives[0]
    assert narrative.classification.value == "FALSE_POSITIVE"
    assert narrative.submitted is False

    await orchestrator.approve_run(run_id=ca_run.id, analyst_id="analyst.test")
    state = await orchestrator.get_state(case.id)
    # After CA the case is awaiting narrative submission.
    assert state.case.current_stage == CaseStage.COMPLETED
    assert state.case.status == CaseStatus.AWAITING_REVIEW

    # ------------- 7. Submit narrative + lock case --------------------------
    await orchestrator.submit_narrative(
        narrative_id=narrative.id, analyst_id="analyst.test"
    )

    state = await orchestrator.get_state(case.id)
    assert state.case.locked is True
    assert state.case.status == CaseStatus.SUBMITTED
    assert any(n.submitted and n.locked for n in state.narratives)

    # ------------- 8. Audit chain still verifies ----------------------------
    async with aml_db.connection() as repos:
        ok, first_bad = await repos.audit.verify_chain(case.id)
        events = await repos.audit.list_for_case(case.id)
    assert ok is True
    assert first_bad is None

    event_types = {e.event_type for e in events}
    expected = {
        AuditEventType.AGENT_STARTED,
        AuditEventType.AGENT_REASONING,
        AuditEventType.AGENT_COMPLETED,
        AuditEventType.GATE_OPENED,
        AuditEventType.GATE_APPROVED,
        AuditEventType.CASE_STAGE_ADVANCED,
        AuditEventType.NARRATIVE_SUBMITTED,
        AuditEventType.RECORD_LOCKED,
    }
    missing = expected - event_types
    assert not missing, f"missing audit events: {missing}"


async def test_idempotent_trigger_returns_same_run(
    aml_db: AmlDbClient,
    orchestrator: Orchestrator,
    case_number: str,
) -> None:
    """Re-triggering an agent with the same extra_input must not duplicate runs."""
    case = await _create_case(aml_db, case_number=case_number)

    first = await orchestrator.trigger_agent(
        case_id=case.id,
        agent_name=AgentName.INITIAL_ASSESSMENT,
        triggered_by="analyst.test",
    )
    # The first run is now AWAITING_REVIEW (non-terminal); a second trigger
    # with the same extra_input should resume it but eventually re-mark it
    # AWAITING_REVIEW with the same id.
    second = await orchestrator.trigger_agent(
        case_id=case.id,
        agent_name=AgentName.INITIAL_ASSESSMENT,
        triggered_by="analyst.test",
    )
    assert first.id == second.id

    # Approve, then re-trigger: terminal status (APPROVED) → no-op, same id.
    await orchestrator.approve_run(run_id=first.id, analyst_id="analyst.test")
    third = await orchestrator.trigger_agent(
        case_id=case.id,
        agent_name=AgentName.INITIAL_ASSESSMENT,
        triggered_by="analyst.test",
    )
    assert third.id == first.id
    assert third.status.value == "APPROVED"


async def test_locked_case_refuses_further_triggers(
    aml_db: AmlDbClient,
    orchestrator: Orchestrator,
    case_number: str,
) -> None:
    case = await _create_case(aml_db, case_number=case_number)

    # Manually lock the case to simulate a fully-submitted investigation.
    async with aml_db.transaction() as repos:
        await repos.cases.lock(case_id=case.id, locked_by="analyst.test")

    with pytest.raises(PermissionError):
        await orchestrator.trigger_agent(
            case_id=case.id,
            agent_name=AgentName.INITIAL_ASSESSMENT,
            triggered_by="analyst.test",
        )
