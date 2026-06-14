"""A2UI integration for AML A2A stage hosts (Sprint 6).

Uses ``a2ui-agent-sdk`` for schema/catalog validation and ADK event conversion.
We ship a local ``SendA2uiJsonToClientTool`` because ``SendA2uiToClientToolset`` in
sdk 0.2.4 fails to import against current ADK (missing ``models`` alias).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from a2a.types import AgentCard, AgentCapabilities
from a2ui.adk.a2a.event_converter import A2uiEventConverter
from a2ui.a2a.extension import (
    A2UI_EXTENSION_BASE_URI,
    get_a2ui_agent_extension,
)
from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.parser.payload_fixer import parse_and_fix
from a2ui.schema.catalog import A2uiCatalog
from a2ui.schema.constants import (
    A2UI_TOOL_ERROR_KEY,
    A2UI_TOOL_NAME,
    A2UI_VALIDATED_JSON_KEY,
    DEFAULT_WORKFLOW_RULES,
    VERSION_0_9,
)
from a2ui.schema.manager import A2uiSchemaManager
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools import base_tool
from google.adk.tools import tool_context
from google.genai import types as genai_types

from ...models.enums import AgentName

log = logging.getLogger(__name__)

A2UI_SESSION_CATALOG_KEY = "system:a2ui_catalog"
A2UI_EXTENSION_VERSION = "0.9"

# Catalog id advertised on agent cards (basic bundled catalog, v0.9).
IA_A2UI_CATALOG_ID = "https://a2ui.org/schemas/a2ui-basic-catalog-0.9.json"

# Sprint 9 — per-stage UI focus (same BasicCatalog schema; different analyst surfaces).
_STAGE_A2UI_SUMMARY: dict[AgentName, str] = {
    AgentName.INITIAL_ASSESSMENT: (
        "risk band, leading hypothesis, and open questions for the alert"
    ),
    AgentName.TRANSACTION_ENRICHMENT: (
        "counter-party table (hop distance, relationship) and a graph traversal summary"
    ),
    AgentName.DUE_DILIGENCE: (
        "sanctions and KYC evidence cards with match confidence and source system"
    ),
    AgentName.CASE_ANALYSIS: (
        "classification banner, narrative draft excerpt, and policy citation list"
    ),
}


@dataclass(frozen=True)
class A2uiConfig:
    """Resolved A2UI feature flags."""

    enabled: bool
    version: str = A2UI_EXTENSION_VERSION
    stages: frozenset[AgentName] = frozenset({AgentName.INITIAL_ASSESSMENT})

    def enabled_for(self, agent_name: AgentName) -> bool:
        return self.enabled and agent_name in self.stages


def load_a2ui_config() -> A2uiConfig:
    """Load A2UI settings from the environment."""
    raw = os.getenv("AML_A2UI_ENABLED", "false").strip().lower()
    enabled = raw in {"1", "true", "yes", "on"}
    stages_raw = os.getenv(
        "AML_A2UI_STAGES",
        AgentName.INITIAL_ASSESSMENT.value,
    )
    stages: set[AgentName] = set()
    for part in stages_raw.split(","):
        token = part.strip()
        if not token:
            continue
        stages.add(AgentName(token))
    version = os.getenv("AML_A2UI_VERSION", A2UI_EXTENSION_VERSION).strip()
    return A2uiConfig(enabled=enabled, version=version, stages=frozenset(stages))


def _schema_manager(version: str = VERSION_0_9) -> A2uiSchemaManager:
    return A2uiSchemaManager(
        version,
        catalogs=[BasicCatalog.get_config(version)],
    )


def catalog_for_stage(agent_name: AgentName) -> A2uiCatalog | None:
    """Return the A2UI catalog for a stage, if A2UI is configured for it."""
    cfg = load_a2ui_config()
    if not cfg.enabled_for(agent_name):
        return None
    manager = _schema_manager(cfg.version if cfg.version != "0.9" else VERSION_0_9)
    if not manager._supported_catalogs:
        return None
    return manager._supported_catalogs[0]


def a2ui_instruction_suffix(*, agent_name: AgentName) -> str:
    """Extra system instruction when A2UI is enabled for a stage."""
    catalog = catalog_for_stage(agent_name)
    if catalog is None:
        return ""
    summary = _STAGE_A2UI_SUMMARY.get(agent_name, "key findings for the analyst")
    return (
        "\n\n--- A2UI (agent-driven UI) ---\n"
        + DEFAULT_WORKFLOW_RULES
        + f"\nAfter your analysis, call `send_a2ui_json_to_client` once with a "
        f"Card summarising {summary}. Use catalog components only.\n"
        "You MUST still finish with the required ```json Output block for the "
        "orchestrator contract — A2UI is an additional rich UI surface, not a "
        "replacement for structured JSON output.\n"
        "If A2UI validation fails, fix the payload or omit the tool call; never "
        "skip the ```json Output block.\n"
        + catalog.render_as_llm_instructions()
        + _stage_a2ui_examples(agent_name)
    )


def _stage_a2ui_examples(agent_name: AgentName) -> str:
    if agent_name == AgentName.INITIAL_ASSESSMENT:
        return _ia_a2ui_examples()
    if agent_name == AgentName.TRANSACTION_ENRICHMENT:
        return _te_a2ui_examples()
    if agent_name == AgentName.DUE_DILIGENCE:
        return _dd_a2ui_examples()
    if agent_name == AgentName.CASE_ANALYSIS:
        return _ca_a2ui_examples()
    return ""


def _ia_a2ui_examples() -> str:
    return """
Example A2UI payload (abbreviated, v0.9) for Initial Assessment:
[
  {
    "version": "v0.9",
    "createSurface": {"surfaceId": "ia-summary", "catalogId": "<catalogId>"},
  },
  {
    "version": "v0.9",
    "updateComponents": {
      "surfaceId": "ia-summary",
      "components": [
        {"id": "root", "component": "Card", "child": "body"},
        {"id": "body", "component": "Column", "children": ["title"]},
        {"id": "title", "component": "Text", "text": "Risk band: HIGH"}
      ]
    }
  }
]
"""


def _te_a2ui_examples() -> str:
    return """
Example A2UI payload (abbreviated, v0.9) for Transaction Enrichment:
[
  {"version": "v0.9", "createSurface": {"surfaceId": "te-parties", "catalogId": "<catalogId>"}},
  {
    "version": "v0.9",
    "updateComponents": {
      "surfaceId": "te-parties",
      "components": [
        {"id": "root", "component": "Card", "child": "body"},
        {"id": "body", "component": "Column", "children": ["title", "graph"]},
        {"id": "title", "component": "Text", "text": "Parties discovered (hop 1–2)"},
        {"id": "graph", "component": "Text", "text": "Graph: 3 counterparties, 2 high-risk jurisdictions"}
      ]
    }
  }
]
"""


def _dd_a2ui_examples() -> str:
    return """
Example A2UI payload (abbreviated, v0.9) for Due Diligence:
[
  {"version": "v0.9", "createSurface": {"surfaceId": "dd-evidence", "catalogId": "<catalogId>"}},
  {
    "version": "v0.9",
    "updateComponents": {
      "surfaceId": "dd-evidence",
      "components": [
        {"id": "root", "component": "Card", "child": "body"},
        {"id": "body", "component": "Column", "children": ["sanctions", "kyc"]},
        {"id": "sanctions", "component": "Text", "text": "Sanctions: no true match (confidence 0.12)"},
        {"id": "kyc", "component": "Text", "text": "KYC: PEP flag — senior management approval required"}
      ]
    }
  }
]
"""


def _ca_a2ui_examples() -> str:
    return """
Example A2UI payload (abbreviated, v0.9) for Case Analysis:
[
  {"version": "v0.9", "createSurface": {"surfaceId": "ca-narrative", "catalogId": "<catalogId>"}},
  {
    "version": "v0.9",
    "updateComponents": {
      "surfaceId": "ca-narrative",
      "components": [
        {"id": "root", "component": "Card", "child": "body"},
        {"id": "body", "component": "Column", "children": ["class", "narrative"]},
        {"id": "class", "component": "Text", "text": "Classification: ESCALATE — STR recommended"},
        {"id": "narrative", "component": "Text", "text": "Narrative draft: structuring pattern across 4 wires…"}
      ]
    }
  }
]
"""


def apply_a2ui_agent_card_extensions(
    agent_card: AgentCard,
    *,
    catalog_ids: list[str],
    version: str = A2UI_EXTENSION_VERSION,
) -> AgentCard:
    """Attach the A2UI A2A extension to an agent card."""
    extension = get_a2ui_agent_extension(
        version,
        supported_catalog_ids=catalog_ids,
    )
    capabilities = agent_card.capabilities or AgentCapabilities()
    existing = list(capabilities.extensions or [])
    if not any(ext.uri == extension.uri for ext in existing):
        existing.append(extension)
    capabilities.extensions = existing
    agent_card.capabilities = capabilities
    return agent_card


def build_a2ui_event_converter() -> A2uiEventConverter:
    """ADK → A2A converter that emits ``application/json+a2ui`` parts."""
    return A2uiEventConverter(catalog_key=A2UI_SESSION_CATALOG_KEY)


async def seed_a2ui_session_catalog(
    callback_context: CallbackContext,
    *,
    agent_name: AgentName,
) -> None:
    """Store the stage catalog on the session for :class:`A2uiEventConverter`."""
    catalog = catalog_for_stage(agent_name)
    if catalog is None:
        return
    inv = callback_context.get_invocation_context()
    inv.session.state[A2UI_SESSION_CATALOG_KEY] = catalog
    log.debug(
        "a2ui.session_catalog agent=%s catalog_id=%s",
        agent_name.value,
        catalog.catalog_id,
    )


class SendA2uiJsonToClientTool(base_tool.BaseTool):
    """Validate and forward A2UI JSON to the A2A event converter."""

    def __init__(self, catalog: A2uiCatalog) -> None:
        self._catalog = catalog
        super().__init__(
            name=A2UI_TOOL_NAME,
            description=(
                "Send validated A2UI JSON to the client for rich UI rendering. "
                "Call once after analysis with a Card summarising findings."
            ),
        )

    def _get_declaration(self) -> genai_types.FunctionDeclaration | None:
        return genai_types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={
                    "a2ui_json": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description="Valid A2UI JSON message list for the client.",
                    ),
                },
                required=["a2ui_json"],
            ),
        )

    async def run_async(
        self,
        *,
        args: dict[str, Any],
        tool_context: tool_context.ToolContext,
    ) -> Any:
        try:
            raw = args.get("a2ui_json")
            if not raw:
                raise ValueError("missing a2ui_json")
            payload = parse_and_fix(raw)
            self._catalog.validator.validate(payload)
            tool_context.actions.skip_summarization = True
            return {A2UI_VALIDATED_JSON_KEY: payload}
        except Exception as err:
            log.warning("a2ui.tool.failed err=%s", err)
            return {A2UI_TOOL_ERROR_KEY: str(err)}


def a2ui_tools_for_stage(agent_name: AgentName) -> list[SendA2uiJsonToClientTool]:
    """Build A2UI tools for a stage host (empty when disabled)."""
    catalog = catalog_for_stage(agent_name)
    if catalog is None:
        return []
    return [SendA2uiJsonToClientTool(catalog)]


def a2ui_extension_uri(version: str = A2UI_EXTENSION_VERSION) -> str:
    return f"{A2UI_EXTENSION_BASE_URI}/v{version}"


def extension_on_card(agent_card: AgentCard, *, version: str = A2UI_EXTENSION_VERSION) -> bool:
    """Return True if the agent card advertises the A2UI extension."""
    caps = agent_card.capabilities
    if caps is None or not caps.extensions:
        return False
    prefix = f"{A2UI_EXTENSION_BASE_URI}/v"
    return any(ext.uri and ext.uri.startswith(prefix) for ext in caps.extensions)
