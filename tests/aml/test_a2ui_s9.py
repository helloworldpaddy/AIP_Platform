"""Sprint 9 — multi-stage A2UI catalogs and schema validation."""

from __future__ import annotations

import pytest

from backend.aml.agents.a2a.a2ui import (
    a2ui_instruction_suffix,
    catalog_for_stage,
)
from backend.aml.models.enums import AgentName


@pytest.fixture(autouse=True)
def _enable_all_stages(monkeypatch):
    monkeypatch.setenv("AML_A2UI_ENABLED", "true")
    monkeypatch.setenv(
        "AML_A2UI_STAGES",
        ",".join(
            a.value
            for a in (
                AgentName.INITIAL_ASSESSMENT,
                AgentName.TRANSACTION_ENRICHMENT,
                AgentName.DUE_DILIGENCE,
                AgentName.CASE_ANALYSIS,
            )
        ),
    )


@pytest.mark.parametrize(
    "agent_name,keyword",
    [
        (AgentName.INITIAL_ASSESSMENT, "risk band"),
        (AgentName.TRANSACTION_ENRICHMENT, "counter-party"),
        (AgentName.DUE_DILIGENCE, "sanctions"),
        (AgentName.CASE_ANALYSIS, "classification"),
    ],
)
def test_all_workflow_stages_have_a2ui_catalog(agent_name, keyword):
    catalog = catalog_for_stage(agent_name)
    assert catalog is not None
    suffix = a2ui_instruction_suffix(agent_name=agent_name)
    assert keyword in suffix.lower()
    assert "send_a2ui_json_to_client" in suffix


def test_a2ui_schema_validates_stage_example_payloads(monkeypatch):
    """Catalog validator accepts a minimal IA Card + Text surface."""
    monkeypatch.setenv("AML_A2UI_ENABLED", "true")
    catalog = catalog_for_stage(AgentName.INITIAL_ASSESSMENT)
    assert catalog is not None
    catalog_id = catalog.catalog_id
    messages = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "ia-summary", "catalogId": catalog_id},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "ia-summary",
                "components": [
                    {"id": "root", "component": "Card", "child": "title"},
                    {"id": "title", "component": "Text", "text": "IA summary"},
                ],
            },
        },
    ]
    catalog.validator.validate(messages)
