"""Unit tests for the A2A adapter and metadata helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from backend.aml.agents.adapters.a2a import A2aAdapter, A2aAdapterError
from backend.aml.agents.adapters.a2a_client import A2aRemoteResponse
from backend.aml.agents.a2a.metadata import (
    AML_A2A_METADATA_KEY,
    build_a2a_request_metadata,
    parse_tool_gateway_from_metadata,
)
from backend.aml.agents.ports import ToolGatewaySpec
from backend.aml.models.enums import AgentName
from tests.aml.stubs import StubInitialAssessmentAgent


def test_build_a2a_request_metadata():
    case_id = uuid4()
    run_id = uuid4()
    spec = ToolGatewaySpec(
        transport="http",
        url="http://localhost:8000/internal/tool-gateway/runs/x/invoke",
        token="tok",
        allowed_tools=("record_evidence",),
    )
    meta = build_a2a_request_metadata(
        case_id=case_id,
        run_id=run_id,
        agent_name=AgentName.INITIAL_ASSESSMENT,
        tool_gateway=spec,
    )
    aml = meta[AML_A2A_METADATA_KEY]
    assert aml["case_id"] == str(case_id)
    assert aml["run_id"] == str(run_id)
    assert aml["tool_gateway"]["token"] == "tok"


def test_parse_tool_gateway_from_metadata():
    parsed = parse_tool_gateway_from_metadata(
        {
            AML_A2A_METADATA_KEY: {
                "tool_gateway": {"url": "http://x", "token": "t", "allowed_tools": []}
            }
        }
    )
    assert parsed is not None
    assert parsed["url"] == "http://x"


@pytest.mark.asyncio
async def test_a2a_adapter_requires_tool_gateway():
    adapter = A2aAdapter(
        agent_name=AgentName.INITIAL_ASSESSMENT,
        agent_card_url="http://ia:8101/.well-known/agent-card.json",
    )
    agent = StubInitialAssessmentAgent()
    ctx = AsyncMock()
    ctx.state.case.id = uuid4()
    ctx.run.id = uuid4()
    ctx.repos = AsyncMock()

    with pytest.raises(A2aAdapterError, match="tool_gateway"):
        await adapter.execute(
            agent_name=AgentName.INITIAL_ASSESSMENT,
            agent=agent,
            ctx=ctx,
            user_message="hello",
            tool_gateway=None,
        )


@pytest.mark.asyncio
async def test_a2a_adapter_maps_json_response():
    adapter = A2aAdapter(
        agent_name=AgentName.INITIAL_ASSESSMENT,
        agent_card_url="http://ia:8101/.well-known/agent-card.json",
    )
    agent = StubInitialAssessmentAgent()
    ctx = AsyncMock()
    case_id = uuid4()
    run_id = uuid4()
    ctx.state.case.id = case_id
    ctx.run.id = run_id
    ctx.repos.evidence.list_for_case = AsyncMock(return_value=[])
    ctx.repos.parties.list_for_case = AsyncMock(return_value=[])

    spec = ToolGatewaySpec(
        transport="http",
        url="http://localhost:8000/internal/tool-gateway/runs/x/invoke",
        token="tok",
        allowed_tools=("record_evidence",),
    )

    remote_text = (
        "Reasoning: stub remote turn\n\n"
        '```json\n{"summary": "remote ok", "risk_score": 55}\n```'
    )

    with patch(
        "backend.aml.agents.adapters.a2a.A2aRemoteClient.send_turn",
        new=AsyncMock(
            return_value=A2aRemoteResponse(final_text=remote_text, task_id="t1")
        ),
    ):
        result = await adapter.execute(
            agent_name=AgentName.INITIAL_ASSESSMENT,
            agent=agent,
            ctx=ctx,
            user_message="Run initial assessment",
            tool_gateway=spec,
        )

    assert result.output_payload["risk_score"] == 55
    assert result.reasoning_summary is not None
