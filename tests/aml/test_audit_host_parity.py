"""Sprint 9 — audit parity between REST orchestrator and AML host agent tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.aml.agents.a2a.analyst_context import reset_analyst_context, set_analyst_context
from backend.aml.agents.a2a.host_tools import set_host_orchestrator, trigger_workflow_stage
from backend.aml.db.client import AmlDbClient
from backend.aml.models.enums import (
    AgentName,
    AuditEventType,
    CasePriority,
    LineOfBusiness,
)
from backend.aml.models.state import CaseCreate
from backend.aml.orchestrator import Orchestrator

pytestmark = pytest.mark.integration

_ANALYST = "analyst.parity"


async def _create_case(repos, *, case_number: str):
    dto = CaseCreate(
        case_number=case_number,
        alert_type="TRANSACTION_MONITORING",
        alert_payload={"rule_id": "TM-001"},
        subject_party_id="P-SUBJECT-001",
        subject_party_name="Jane Doe",
        line_of_business=LineOfBusiness.RETAIL_BANKING,
        priority=CasePriority.HIGH,
        assigned_analyst_id=_ANALYST,
        created_by="seed",
    )
    return await repos.cases.create(dto)


def _agent_lifecycle_events(events) -> set[AuditEventType]:
    lifecycle = {
        AuditEventType.AGENT_STARTED,
        AuditEventType.AGENT_REASONING,
        AuditEventType.AGENT_COMPLETED,
        AuditEventType.AGENT_FAILED,
    }
    return {e.event_type for e in events if e.event_type in lifecycle}


@pytest.mark.asyncio
async def test_host_trigger_matches_direct_orchestrator_audit(
    aml_db: AmlDbClient,
    orchestrator: Orchestrator,
    case_number: str,
    monkeypatch,
) -> None:
    """Host ``trigger_workflow_stage`` must produce the same agent audit events as REST."""
    monkeypatch.setattr("backend.aml.db.client._singleton", aml_db)

    async with aml_db.transaction() as repos:
        case_direct = await _create_case(repos, case_number=case_number)

    direct_run = await orchestrator.trigger_agent(
        case_id=case_direct.id,
        agent_name=AgentName.INITIAL_ASSESSMENT,
        triggered_by=_ANALYST,
        extra_input={"source": "rest_api"},
    )
    assert direct_run.status.value == "AWAITING_REVIEW"

    async with aml_db.connection() as repos:
        direct_events = await repos.audit.list_for_case(case_direct.id)
        ok, bad = await repos.audit.verify_chain(case_direct.id)
    assert ok and bad is None

    token = set_analyst_context(_ANALYST)
    set_host_orchestrator(orchestrator)
    try:
        async with aml_db.transaction() as repos:
            case_host = await _create_case(repos, case_number=f"{case_number}-HOST")

        with patch(
            "backend.aml.agents.a2a.host_tools.ensure_runtime_ready",
            new=AsyncMock(),
        ):
            result = await trigger_workflow_stage(
                case_host.case_number,
                AgentName.INITIAL_ASSESSMENT.value,
            )
    finally:
        reset_analyst_context(token)
        set_host_orchestrator(None)

    assert result["ok"] is True
    assert result["status"] == "AWAITING_REVIEW"

    async with aml_db.connection() as repos:
        host_events = await repos.audit.list_for_case(case_host.id)
        ok, bad = await repos.audit.verify_chain(case_host.id)
    assert ok and bad is None

    direct_lifecycle = _agent_lifecycle_events(direct_events)
    host_lifecycle = _agent_lifecycle_events(host_events)
    assert direct_lifecycle == host_lifecycle
    assert AuditEventType.AGENT_STARTED in direct_lifecycle
    assert AuditEventType.AGENT_COMPLETED in direct_lifecycle
