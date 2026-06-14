"""Sprint 7 — AML host agent (A2A front door to orchestrator)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from google.adk.a2a.converters.request_converter import A2A_METADATA_KEY

from backend.aml.agents.a2a.aml_host_agent import (
    bind_analyst_from_a2a_metadata,
    build_aml_host_agent,
)
from backend.aml.agents.a2a.analyst_context import (
    current_analyst_id,
    require_analyst_id,
    reset_bound_analyst_context,
    set_analyst_context,
)
from backend.aml.agents.a2a.host_tools import (
    approve_agent_run,
    get_case_state,
    set_host_orchestrator,
    trigger_workflow_stage,
)
from backend.aml.agents.a2a.host_app import create_aml_host_app
from backend.aml.agents.a2a.metadata import (
    build_host_client_metadata,
    parse_analyst_id_from_metadata,
)
from backend.aml.models.enums import AgentName, AgentRunStatus, CaseStage
from backend.aml.models.state import CaseCreate


@pytest.fixture(autouse=True)
def _reset_host_orchestrator():
    set_host_orchestrator(None)
    yield
    set_host_orchestrator(None)


def test_build_aml_host_agent_exposes_orchestrator_tools():
    agent = build_aml_host_agent()
    tool_names = {getattr(t, "name", None) for t in (agent.tools or [])}
    assert tool_names == {
        "get_case_state",
        "trigger_workflow_stage",
        "approve_agent_run",
        "reject_agent_run",
        "resolve_human_gate",
        "verify_case_party",
    }


def test_parse_analyst_id_from_metadata():
    meta = build_host_client_metadata(analyst_id="analyst.jane")
    assert parse_analyst_id_from_metadata(meta) == "analyst.jane"
    assert parse_analyst_id_from_metadata({}) is None


@pytest.mark.asyncio
async def test_bind_analyst_from_a2a_metadata():
    class _RunConfig:
        custom_metadata = {
            A2A_METADATA_KEY: build_host_client_metadata(analyst_id="analyst.test")
        }

    class _Inv:
        run_config = _RunConfig()

    class _Ctx:
        def __init__(self):
            self.state = {}

        def get_invocation_context(self):
            return _Inv()

    ctx = _Ctx()
    await bind_analyst_from_a2a_metadata(ctx)
    assert current_analyst_id() == "analyst.test"
    reset_bound_analyst_context()
    assert current_analyst_id() is None


def test_require_analyst_id_rejects_missing():
    with pytest.raises(PermissionError, match="missing analyst_id"):
        require_analyst_id()


@pytest.mark.asyncio
async def test_trigger_workflow_stage_requires_analyst_id():
    result = await trigger_workflow_stage("AML-TEST-001", "INITIAL_ASSESSMENT")
    assert result["ok"] is False
    assert "missing analyst_id" in result["error"]


async def _create_case(repos, *, case_number: str):
    dto = CaseCreate(
        case_number=case_number,
        alert_type="TRANSACTION_MONITORING",
        alert_payload={"rule_id": "TM-001"},
        subject_party_id="P-SUBJECT-001",
        subject_party_name="Jane Doe",
        created_by="analyst.test",
    )
    return await repos.cases.create(dto)


@pytest.mark.asyncio
async def test_trigger_workflow_stage_hits_orchestrator(
    orchestrator, aml_db, case_number: str, monkeypatch
):
    monkeypatch.setattr("backend.aml.db.client._singleton", aml_db)
    token = set_analyst_context("analyst.test")
    set_host_orchestrator(orchestrator)
    try:
        async with aml_db.transaction() as repos:
            await _create_case(repos, case_number=case_number)

        with patch(
            "backend.aml.agents.a2a.host_tools.ensure_runtime_ready",
            new=AsyncMock(),
        ):
            result = await trigger_workflow_stage(
                case_number, AgentName.INITIAL_ASSESSMENT.value
            )
    finally:
        reset_analyst_context(token)

    assert result["ok"] is True
    assert result["agent"] == AgentName.INITIAL_ASSESSMENT.value
    assert result["status"] in {
        AgentRunStatus.AWAITING_REVIEW.value,
        AgentRunStatus.COMPLETED.value,
    }


@pytest.mark.asyncio
async def test_gate_blocked_surfaces_structured_error(
    orchestrator, aml_db, case_number: str, monkeypatch
):
    monkeypatch.setattr("backend.aml.db.client._singleton", aml_db)
    token = set_analyst_context("analyst.test")
    set_host_orchestrator(orchestrator)
    try:
        async with aml_db.transaction() as repos:
            case = await _create_case(repos, case_number=case_number)
            await repos.cases.advance_stage(
                case_id=case.id,
                stage=CaseStage.DUE_DILIGENCE,
                updated_by="analyst.test",
            )
            gate = await repos.gates.open(
                case_id=case.id,
                gate_name="PARTIES_VERIFIED",
                blocks_agent=AgentName.DUE_DILIGENCE,
                notes="verify parties first",
            )

        with patch(
            "backend.aml.agents.a2a.host_tools.ensure_runtime_ready",
            new=AsyncMock(),
        ):
            result = await trigger_workflow_stage(
                case_number, AgentName.DUE_DILIGENCE.value
            )
    finally:
        reset_analyst_context(token)

    assert result["ok"] is False
    assert result["gate_id"] == str(gate.id)
    assert result["blocks_agent"] == AgentName.DUE_DILIGENCE.value
    assert "blocked" in result["error"].lower()


@pytest.mark.asyncio
async def test_get_case_state_summary(orchestrator, aml_db, case_number: str, monkeypatch):
    monkeypatch.setattr("backend.aml.db.client._singleton", aml_db)
    token = set_analyst_context("analyst.test")
    try:
        async with aml_db.transaction() as repos:
            await _create_case(repos, case_number=case_number)

        with patch(
            "backend.aml.agents.a2a.host_tools.ensure_runtime_ready",
            new=AsyncMock(),
        ):
            result = await get_case_state(case_number)
    finally:
        reset_analyst_context(token)

    assert result["ok"] is True
    assert result["state"]["case_number"] == case_number
    assert isinstance(result["state"]["progress"], list)


@pytest.mark.asyncio
async def test_approve_agent_run(orchestrator, aml_db, case_number: str, monkeypatch):
    monkeypatch.setattr("backend.aml.db.client._singleton", aml_db)
    token = set_analyst_context("analyst.test")
    set_host_orchestrator(orchestrator)
    try:
        async with aml_db.transaction() as repos:
            case = await _create_case(repos, case_number=case_number)

        with patch(
            "backend.aml.agents.a2a.host_tools.ensure_runtime_ready",
            new=AsyncMock(),
        ):
            run = await orchestrator.trigger_agent(
                case_id=case.id,
                agent_name=AgentName.INITIAL_ASSESSMENT,
                triggered_by="analyst.test",
            )
            assert run.status == AgentRunStatus.AWAITING_REVIEW
            result = await approve_agent_run(str(run.id))
    finally:
        reset_analyst_context(token)

    assert result["ok"] is True
    assert result["status"] == AgentRunStatus.APPROVED.value


def test_create_aml_host_app_smoke():
    app = create_aml_host_app(public_host="localhost", port=8199)
    assert app is not None
