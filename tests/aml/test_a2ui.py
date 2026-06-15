"""Sprint 6 — A2UI on A2A stage hosts (IA PoC)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from a2ui.adk.a2a.part_converter import A2uiPartConverter
from a2ui.schema.constants import A2UI_TOOL_NAME, A2UI_VALIDATED_JSON_KEY
from google.genai import types as genai_types

from backend.aml.agents.a2a.a2ui import (
    SendA2uiJsonToClientTool,
    apply_a2ui_agent_card_extensions,
    a2ui_instruction_suffix,
    catalog_for_stage,
    extension_on_card,
    load_a2ui_config,
)
from backend.aml.agents.a2a.host_agent import build_a2a_host_agent
from backend.aml.agents.adapters.a2a import A2aAdapter
from backend.aml.agents.adapters.a2a_client import A2aRemoteResponse
from backend.aml.agents.adk_runner import extract_json_block
from backend.aml.agents.ports import ToolGatewaySpec
from backend.aml.models.enums import AgentName
from tests.aml.stubs import StubInitialAssessmentAgent


@pytest.fixture(autouse=True)
def _clear_a2ui_env(monkeypatch):
    monkeypatch.delenv("AML_A2UI_ENABLED", raising=False)
    monkeypatch.delenv("AML_A2UI_STAGES", raising=False)


def test_a2ui_disabled_by_default():
    cfg = load_a2ui_config()
    assert cfg.enabled is False
    assert catalog_for_stage(AgentName.INITIAL_ASSESSMENT) is None


def test_a2ui_catalog_when_enabled(monkeypatch):
    monkeypatch.setenv("AML_A2UI_ENABLED", "true")
    catalog = catalog_for_stage(AgentName.INITIAL_ASSESSMENT)
    assert catalog is not None
    assert catalog.catalog_id.startswith("https://a2ui.org/")


@pytest.fixture
def sample_a2ui_messages(monkeypatch):
    monkeypatch.setenv("AML_A2UI_ENABLED", "true")
    catalog = catalog_for_stage(AgentName.INITIAL_ASSESSMENT)
    assert catalog is not None
    catalog_id = catalog.catalog_id
    return [
        {
            "version": "v0.9",
            "createSurface": {
                "surfaceId": "ia-summary",
                "catalogId": catalog_id,
            },
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "ia-summary",
                "components": [
                    {
                        "id": "root",
                        "component": "Card",
                        "child": "title",
                    },
                    {
                        "id": "title",
                        "component": "Text",
                        "text": "IA summary",
                    },
                ],
            },
        },
    ]


def test_a2ui_instruction_suffix_escapes_adk_expression_placeholder(monkeypatch):
    monkeypatch.setenv("AML_A2UI_ENABLED", "true")
    monkeypatch.setenv("AML_A2UI_STAGES", AgentName.INITIAL_ASSESSMENT.value)
    suffix = a2ui_instruction_suffix(agent_name=AgentName.INITIAL_ASSESSMENT)
    assert "{expression}" not in suffix
    assert "(expression)" in suffix or "${expression}" in suffix


def test_apply_a2ui_agent_card_extensions():
    from a2a.types import AgentCapabilities, AgentCard, AgentSkill

    card = AgentCard(
        name="initial_assessment",
        description="test",
        url="http://localhost:8101/",
        version="1.0.0",
        capabilities=AgentCapabilities(),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[
            AgentSkill(
                id="initial_assessment",
                name="Initial Assessment",
                description="Run IA",
                tags=["aml", "initial_assessment"],
            )
        ],
    )
    patched = apply_a2ui_agent_card_extensions(
        card,
        catalog_ids=["https://a2ui.org/schemas/a2ui-basic-catalog-0.9.json"],
        version="0.9",
    )
    assert extension_on_card(patched, version="0.9")


@pytest.mark.asyncio
async def test_send_a2ui_tool_validates_minimal_payload(
    monkeypatch, sample_a2ui_messages
):
    monkeypatch.setenv("AML_A2UI_ENABLED", "true")
    catalog = catalog_for_stage(AgentName.INITIAL_ASSESSMENT)
    assert catalog is not None
    tool = SendA2uiJsonToClientTool(catalog)
    payload = json.dumps(sample_a2ui_messages)

    class _Actions:
        skip_summarization = False

    class _Ctx:
        actions = _Actions()

    result = await tool.run_async(args={"a2ui_json": payload}, tool_context=_Ctx())
    assert A2UI_VALIDATED_JSON_KEY in result
    assert isinstance(result[A2UI_VALIDATED_JSON_KEY], list)


def test_a2ui_part_converter_emits_data_part(monkeypatch, sample_a2ui_messages):
    monkeypatch.setenv("AML_A2UI_ENABLED", "true")
    catalog = catalog_for_stage(AgentName.INITIAL_ASSESSMENT)
    assert catalog is not None

    validated = sample_a2ui_messages
    part = genai_types.Part(
        function_response=genai_types.FunctionResponse(
            name=A2UI_TOOL_NAME,
            response={A2UI_VALIDATED_JSON_KEY: validated},
        )
    )
    a2a_parts = A2uiPartConverter(catalog, version="0.9").convert(part)
    assert len(a2a_parts) >= 1
    data_part = a2a_parts[0].root
    metadata = getattr(data_part, "metadata", None) or {}
    mime = metadata.get("mimeType") or metadata.get("mime_type")
    assert mime == "application/json+a2ui"


def test_ia_host_includes_a2ui_tool_when_enabled(monkeypatch):
    monkeypatch.setenv("AML_A2UI_ENABLED", "true")
    agent = build_a2a_host_agent(AgentName.INITIAL_ASSESSMENT)
    tool_names = {getattr(t, "name", None) for t in (agent.tools or [])}
    assert A2UI_TOOL_NAME in tool_names
    assert "A2UI" in (agent.instruction or "")


def test_ia_host_omits_a2ui_when_disabled():
    agent = build_a2a_host_agent(AgentName.INITIAL_ASSESSMENT)
    tool_names = {getattr(t, "name", None) for t in (agent.tools or [])}
    assert A2UI_TOOL_NAME not in tool_names


def test_orchestrator_json_parity_with_a2ui_text_response():
    """JSON ``output_payload`` contract survives when response includes A2UI tool output."""
    remote_text = (
        "Reasoning: assessed alert\n\n"
        '```json\n{"summary": "ok", "risk_score": 72, "requires_review": true}\n```'
    )
    output = extract_json_block(remote_text)
    assert output["risk_score"] == 72


@pytest.mark.asyncio
async def test_a2a_adapter_json_parity_unchanged_with_a2ui_enabled(monkeypatch):
    """A2aAdapter still parses ```json`` from final_text (orchestrator path)."""
    monkeypatch.setenv("AML_A2UI_ENABLED", "true")
    adapter = A2aAdapter(
        agent_name=AgentName.INITIAL_ASSESSMENT,
        agent_card_url="http://ia:8101/.well-known/agent-card.json",
    )
    agent = StubInitialAssessmentAgent()
    ctx = AsyncMock()
    ctx.state.case.id = uuid4()
    ctx.run.id = uuid4()
    ctx.repos.evidence.list_for_case = AsyncMock(return_value=[])
    ctx.repos.parties.list_for_case = AsyncMock(return_value=[])

    spec = ToolGatewaySpec(
        transport="http",
        url="http://localhost:8000/internal/tool-gateway/runs/x/invoke",
        token="tok",
        allowed_tools=("record_evidence",),
    )
    remote_text = (
        "Reasoning: remote IA with optional A2UI\n\n"
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
