"""Unit tests for the A2A adapter and metadata helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from backend.aml.agents.adapters.a2a import A2aAdapter, A2aAdapterError, _collect_ids_written_during_run
from backend.aml.agents.adapters.a2a_client import A2aRemoteClient, A2aRemoteResponse
from a2a.types import Message, Part, Role, Task, TaskStatus, TaskState, TextPart
from backend.aml.agents.a2a.metadata import (
    AML_A2A_METADATA_KEY,
    build_a2a_request_metadata,
    parse_tool_gateway_from_metadata,
)
from backend.aml.agents.ports import ToolGatewaySpec
from backend.aml.models.enums import AgentName, EvidenceType
from backend.aml.models.state import CaseParty, Evidence
from tests.aml.stubs import StubInitialAssessmentAgent


@pytest.mark.asyncio
async def test_collect_ids_written_during_run_links_parties_via_evidence():
    """case_parties has no agent_run_id; harvest via source_evidence_ids."""
    case_id = uuid4()
    run_id = uuid4()
    ev_id = uuid4()
    party_linked = uuid4()
    party_old = uuid4()
    now = datetime.now(timezone.utc)

    ctx = AsyncMock()
    ctx.state.case.id = case_id
    ctx.run.id = run_id
    ctx.run.started_at = now
    ctx.repos.evidence.list_for_case = AsyncMock(
        return_value=[
            Evidence(
                id=ev_id,
                case_id=case_id,
                agent_run_id=run_id,
                evidence_type=EvidenceType.INTERNAL_NOTE,
                source_system="test",
                title="t",
                content="c",
                content_hash="h",
                retrieved_at=now,
                created_by="test",
            )
        ]
    )
    ctx.repos.parties.list_for_case = AsyncMock(
        return_value=[
            CaseParty(
                id=party_linked,
                case_id=case_id,
                party_external_id="linked",
                party_name="Linked Party",
                hop_distance=1,
                source_evidence_ids=[ev_id],
                created_at=now,
            ),
            CaseParty(
                id=party_old,
                case_id=case_id,
                party_external_id="old",
                party_name="Old Party",
                hop_distance=2,
                source_evidence_ids=[],
                created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            ),
        ]
    )

    ev_ids, party_ids = await _collect_ids_written_during_run(ctx)
    assert ev_ids == [ev_id]
    assert party_ids == [party_linked]


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


@pytest.mark.asyncio
async def test_a2a_remote_client_uses_blocking_non_streaming_send():
    """Non-streaming stage hosts need blocking message/send (polling=False)."""
    captured: dict = {}

    class _FakeFactory:
        def __init__(self, config):
            captured["config"] = config

        def create(self, card):
            return AsyncMock()

    with (
        patch("backend.aml.agents.adapters.a2a_client.A2ACardResolver") as resolver_cls,
        patch(
            "backend.aml.agents.adapters.a2a_client.ClientFactory",
            _FakeFactory,
        ),
    ):
        resolver = AsyncMock()
        resolver.get_agent_card = AsyncMock(return_value=object())
        resolver_cls.return_value = resolver

        client = A2aRemoteClient(
            agent_card_url="http://ia:8101/.well-known/agent-card.json",
        )
        await client._ensure_client()

    assert captured["config"].streaming is False
    assert captured["config"].polling is False


@pytest.mark.asyncio
async def test_send_turn_polls_get_task_when_submitted_without_text():
    """Stage hosts may return submitted immediately; client must poll tasks/get."""
    task_submitted = Task(
        id="t1",
        context_id="ctx1",
        status=TaskStatus(state=TaskState.submitted),
    )
    agent_text = '```json\n{"risk_score": 50}\n```'
    task_completed = Task(
        id="t1",
        context_id="ctx1",
        status=TaskStatus(state=TaskState.completed),
        history=[
            Message(
                role=Role.agent,
                message_id="m1",
                parts=[Part(root=TextPart(text=agent_text))],
            )
        ],
    )

    async def fake_send(*args, **kwargs):
        yield (task_submitted, None)

    mock_client = AsyncMock()
    mock_client.send_message = fake_send
    mock_client.get_task = AsyncMock(return_value=task_completed)

    remote = A2aRemoteClient(
        agent_card_url="http://ia:8101/.well-known/agent-card.json",
    )
    with patch.object(remote, "_ensure_client", AsyncMock(return_value=mock_client)):
        result = await remote.send_turn(user_message="hi")

    assert result.final_text == agent_text
    assert result.task_state == TaskState.completed
    mock_client.get_task.assert_awaited()
