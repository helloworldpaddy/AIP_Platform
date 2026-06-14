"""Unit + integration tests for the run-scoped tool gateway (Sprint 2)."""

from __future__ import annotations

import time
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from backend.aml.agents.tool_gateway import (
    ToolGatewayClaims,
    ToolGatewayService,
    build_tool_gateway_service,
    mint_tool_gateway_token,
    verify_tool_gateway_token,
)
from backend.aml.api.app import create_app
from backend.aml.api.dependencies import get_db, get_tool_gateway
from backend.aml.db.client import AmlDbClient
from backend.aml.models.enums import (
    AgentName,
    AgentRunStatus,
    CasePriority,
    EvidenceType,
    LineOfBusiness,
)
from backend.aml.models.state import CaseCreate

pytestmark = pytest.mark.integration


def test_mint_and_verify_token_roundtrip():
    claims = ToolGatewayClaims(
        run_id=uuid4(),
        case_id=uuid4(),
        agent=AgentName.INITIAL_ASSESSMENT,
        allowed_tools=("record_evidence", "policy_rag_search"),
        exp=int(time.time()) + 300,
    )
    token = mint_tool_gateway_token(claims=claims, secret=b"test-secret")
    verified = verify_tool_gateway_token(token, secret=b"test-secret")
    assert verified.run_id == claims.run_id
    assert verified.allowed_tools == claims.allowed_tools


def test_verify_rejects_tampered_token():
    claims = ToolGatewayClaims(
        run_id=uuid4(),
        case_id=uuid4(),
        agent=AgentName.DUE_DILIGENCE,
        allowed_tools=("kyc_lookup",),
        exp=int(time.time()) + 300,
    )
    token = mint_tool_gateway_token(claims=claims, secret=b"test-secret")
    with pytest.raises(ValueError, match="signature"):
        verify_tool_gateway_token(token + "x", secret=b"test-secret")


def test_verify_rejects_expired_token():
    claims = ToolGatewayClaims(
        run_id=uuid4(),
        case_id=uuid4(),
        agent=AgentName.CASE_ANALYSIS,
        allowed_tools=("record_evidence",),
        exp=int(time.time()) - 10,
    )
    token = mint_tool_gateway_token(claims=claims, secret=b"test-secret")
    with pytest.raises(ValueError, match="expired"):
        verify_tool_gateway_token(token, secret=b"test-secret")


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


async def _running_run(
    db: AmlDbClient,
    *,
    case_id,
    agent: AgentName = AgentName.INITIAL_ASSESSMENT,
):
    async with db.transaction() as repos:
        run, _ = await repos.agent_runs.get_or_create_run(
            case_id=case_id,
            agent=agent,
            idempotency_key=f"test-{uuid4()}",
            input_payload={},
        )
        return await repos.agent_runs.mark_running(run.id)


async def test_gateway_invoke_record_evidence(
    aml_db: AmlDbClient,
    case_number: str,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AML_TOOL_GATEWAY_SECRET", "pytest-tool-gateway-secret")
    case = await _create_case(aml_db, case_number=case_number)
    run = await _running_run(aml_db, case_id=case.id)

    gateway = build_tool_gateway_service(aml_db)
    spec = gateway.mint_for_run(
        run_id=run.id,
        case_id=case.id,
        agent_name=AgentName.INITIAL_ASSESSMENT,
        allowed_tools=["record_evidence"],
    )

    result = await gateway.invoke(
        claims=verify_tool_gateway_token(spec.token),
        tool_name="record_evidence",
        arguments={
            "evidence_type": EvidenceType.POLICY_RULE.value,
            "source_system": "tool-gateway-test",
            "title": "Gateway evidence",
            "content": "Recorded via tool gateway.",
        },
    )
    assert "evidence_id" in result

    async with aml_db.connection() as repos:
        evidence = await repos.evidence.list_for_case(case.id)
    assert len(evidence) == 1
    assert evidence[0].title == "Gateway evidence"


async def test_gateway_invoke_rejects_disallowed_tool(
    aml_db: AmlDbClient,
    case_number: str,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AML_TOOL_GATEWAY_SECRET", "pytest-tool-gateway-secret")
    case = await _create_case(aml_db, case_number=case_number)
    run = await _running_run(aml_db, case_id=case.id)

    gateway = build_tool_gateway_service(aml_db)
    spec = gateway.mint_for_run(
        run_id=run.id,
        case_id=case.id,
        agent_name=AgentName.INITIAL_ASSESSMENT,
        allowed_tools=["record_evidence"],
    )
    claims = verify_tool_gateway_token(spec.token)

    with pytest.raises(PermissionError, match="not allowed"):
        await gateway.invoke(
            claims=claims,
            tool_name="kyc_lookup",
            arguments={"party_id": "P-1"},
        )


async def test_http_invoke_endpoint(
    aml_db: AmlDbClient,
    case_number: str,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AML_TOOL_GATEWAY_SECRET", "pytest-tool-gateway-secret")
    case = await _create_case(aml_db, case_number=case_number)
    run = await _running_run(aml_db, case_id=case.id)

    gateway = build_tool_gateway_service(aml_db)
    spec = gateway.mint_for_run(
        run_id=run.id,
        case_id=case.id,
        agent_name=AgentName.INITIAL_ASSESSMENT,
        allowed_tools=["record_evidence"],
    )

    app = create_app()
    app.dependency_overrides[get_db] = lambda: aml_db
    app.dependency_overrides[get_tool_gateway] = lambda: gateway

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/internal/tool-gateway/runs/{run.id}/invoke",
            json={
                "tool": "record_evidence",
                "arguments": {
                    "evidence_type": EvidenceType.POLICY_RULE.value,
                    "source_system": "http-test",
                    "title": "HTTP gateway evidence",
                    "content": "Via HTTP route.",
                },
            },
            headers={"Authorization": f"Bearer {spec.token}"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tool"] == "record_evidence"
    assert "evidence_id" in body["result"]


async def test_gateway_invoke_returns_error_on_bad_arguments(
    aml_db: AmlDbClient,
    case_number: str,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AML_TOOL_GATEWAY_SECRET", "pytest-tool-gateway-secret")
    case = await _create_case(aml_db, case_number=case_number)
    run = await _running_run(aml_db, case_id=case.id)

    gateway = build_tool_gateway_service(aml_db)
    spec = gateway.mint_for_run(
        run_id=run.id,
        case_id=case.id,
        agent_name=AgentName.INITIAL_ASSESSMENT,
        allowed_tools=["policy_rag_search"],
    )
    claims = verify_tool_gateway_token(spec.token)

    result = await gateway.invoke(
        claims=claims,
        tool_name="policy_rag_search",
        arguments={},
    )
    assert "error" in result
    assert "query" in result["error"].lower()
