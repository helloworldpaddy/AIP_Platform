"""Tests for AML_ADK_MODE=orchestrator hybrid callbacks (Sprint 4)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from backend.aml.agents.runtime.adk_callbacks import hybrid_callbacks
from backend.aml.agents.runtime.orchestrator_invoke import format_orchestrator_run_for_chat
from backend.aml.config.adk_mode import AdkMode, load_adk_mode
from backend.aml.models.enums import AgentName, AgentRunStatus
from backend.aml.models.state import AgentRun


def _sample_run(**overrides) -> AgentRun:
    now = datetime.now(timezone.utc)
    base = dict(
        id=uuid4(),
        case_id=uuid4(),
        agent=AgentName.INITIAL_ASSESSMENT,
        attempt=1,
        idempotency_key="k",
        status=AgentRunStatus.AWAITING_REVIEW,
        output_payload={"risk_score": 70, "summary": "ok"},
        reasoning="Reasoning: triage complete.",
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return AgentRun(**base)


def test_load_adk_mode_defaults_hybrid(monkeypatch):
    monkeypatch.delenv("AML_ADK_MODE", raising=False)
    assert load_adk_mode() == AdkMode.HYBRID


def test_load_adk_mode_orchestrator(monkeypatch):
    monkeypatch.setenv("AML_ADK_MODE", "orchestrator")
    assert load_adk_mode() == AdkMode.ORCHESTRATOR


def test_format_orchestrator_run_for_chat():
    run = _sample_run()
    text = format_orchestrator_run_for_chat(run)
    assert "Reasoning: triage complete." in text
    assert "risk_score" in text
    payload = json.loads(text.split("```json\n", 1)[1].split("\n```", 1)[0])
    assert payload["risk_score"] == 70


@pytest.mark.asyncio
async def test_hybrid_callbacks_orchestrator_mode_short_circuits_llm(monkeypatch):
    monkeypatch.setenv("AML_ADK_MODE", "orchestrator")

    before, before_model, after = hybrid_callbacks(AgentName.INITIAL_ASSESSMENT)
    run = _sample_run(output_payload={"summary": "via orchestrator"})

    ctx = MagicMock()
    ctx.invocation_id = "inv-1"
    ctx.agent_name = "initial_assessment"
    ctx.state = {}
    ctx.user_content = MagicMock(
        parts=[MagicMock(text="Run initial assessment for AML-TEST-2026-001")]
    )

    with patch(
        "backend.aml.agents.runtime.adk_callbacks.invoke_orchestrator_stage",
        new=AsyncMock(return_value=run),
    ):
        await before(ctx)

    assert ctx.state.get("aml_orchestrator_mode") is True
    assert ctx.state.get("aml_run_id") == str(run.id)

    llm_request = MagicMock()
    llm_request.contents = []
    response = await before_model(ctx, llm_request)
    assert response is not None
    assert "via orchestrator" in response.content.parts[0].text

    await after(ctx)
