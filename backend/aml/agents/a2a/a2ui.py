"""A2UI integration for AML A2A stage hosts (Sprint 6).

Uses ``a2ui-agent-sdk`` for schema/catalog validation and ADK event conversion.
We ship a local ``SendA2uiJsonToClientTool`` because ``SendA2uiToClientToolset`` in
sdk 0.2.4 fails to import against current ADK (missing ``models`` alias).
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

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

from ...models.enums import AgentName, AgentRunStatus
from .summary_parse import analyst_lines_from_payload, enrich_failed_output_payload

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


# ADK inject_session_state treats `{identifier}` in instructions as session placeholders.
_ADK_STATE_REF = re.compile(r"\{+[^{}]*\}+")


def _escape_adk_session_state_refs(text: str) -> str:
    """Neutralize catalog prose like ``${expression}`` that ADK mis-reads as state keys."""

    def _repl(match: re.Match[str]) -> str:
        raw = match.group(0)
        inner = raw.lstrip("{").rstrip("}").strip().strip("+")
        if not inner.isidentifier():
            return raw
        return raw.replace("{", "(").replace("}", ")")

    return _ADK_STATE_REF.sub(_repl, text)


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
        + _escape_adk_session_state_refs(catalog.render_as_llm_instructions())
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


def attach_a2ui_to_output_payload(
    output_payload: dict[str, Any],
    *,
    agent_name: AgentName,
    run_id: UUID,
    status: AgentRunStatus,
    captured_messages: list[dict[str, Any]] | None = None,
    reasoning: str | None = None,
    case_priority: str | None = None,
) -> dict[str, Any]:
    """Merge agent-emitted or synthesized A2UI into the orchestrator output payload."""
    output_payload = enrich_failed_output_payload(
        output_payload,
        reasoning=reasoning,
        case_priority=case_priority,
        agent_name=agent_name.value,
    )
    existing = output_payload.get("a2ui_messages")
    if isinstance(existing, list) and existing:
        return output_payload
    if captured_messages:
        output_payload["a2ui_messages"] = captured_messages
        return output_payload
    built = build_run_surface_messages(
        agent=agent_name,
        run_id=run_id,
        status=status,
        output_payload=output_payload,
    )
    if built:
        output_payload["a2ui_messages"] = built
    return output_payload


def _stored_a2ui_is_stale(output_payload: dict[str, Any]) -> bool:
    """True when stored surfaces were built from a failed parse salvage."""
    if output_payload.get("error") != "failed_to_parse_output":
        return False
    messages = output_payload.get("a2ui_messages")
    if not isinstance(messages, list) or not messages:
        return False
    blob = str(messages).lower()
    stale_markers = (
        "risk band: not assessed",
        "structured json was incomplete",
        "risk band and hypothesis may be missing",
        "failed_to_parse_output",
    )
    return any(marker in blob for marker in stale_markers)


def hydrate_agent_run_payloads(
    runs: list[Any],
    *,
    case_priority: str | None = None,
) -> list[Any]:
    """On case load: salvage partial IA output and attach missing A2UI surfaces."""
    cfg = load_a2ui_config()
    if not cfg.enabled:
        return runs

    for run in runs:
        payload = run.output_payload
        if not isinstance(payload, dict):
            continue

        enriched = enrich_failed_output_payload(
            dict(payload),
            reasoning=run.reasoning,
            case_priority=case_priority,
            agent_name=run.agent.value,
        )

        # Drop stale synthesized surfaces so client templates can rebuild.
        if enriched.get("a2ui_messages") and _stored_a2ui_is_stale(enriched):
            enriched = dict(enriched)
            del enriched["a2ui_messages"]

        if not enriched.get("a2ui_messages") and cfg.enabled_for(run.agent):
            enriched = attach_a2ui_to_output_payload(
                enriched,
                agent_name=run.agent,
                run_id=run.id,
                status=run.status,
                reasoning=run.reasoning,
                case_priority=case_priority,
            )

        if enriched != payload:
            run.output_payload = enriched

    return runs


def build_run_surface_messages(
    *,
    agent: AgentName,
    run_id: UUID,
    status: AgentRunStatus,
    output_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """Deterministic A2UI surface when the stage host did not emit one on the wire."""
    cfg = load_a2ui_config()
    if not cfg.enabled_for(agent):
        return []
    catalog = catalog_for_stage(agent)
    if catalog is None:
        return []

    surface_id = f"{agent.value.lower()}-{str(run_id)[:8]}"
    catalog_id = catalog.catalog_id
    lines = analyst_lines_from_payload(output_payload)

    body_children: list[str] = ["title", "status"]
    components: list[dict[str, Any]] = [
        {"id": "root", "component": "Card", "child": "body"},
        {"id": "body", "component": "Column", "children": body_children},
        {
            "id": "title",
            "component": "Text",
            "text": agent.value.replace("_", " "),
            "variant": "h3",
        },
        {
            "id": "status",
            "component": "Text",
            "text": f"Awaiting review · run {str(run_id)[:8]}…"
            if status == AgentRunStatus.AWAITING_REVIEW
            else f"{status.value} · run {str(run_id)[:8]}…",
            "variant": "caption",
        },
    ]

    question_ids: list[str] = []
    for idx, (label, value) in enumerate(lines):
        line_id = f"line-{idx}"
        body_children.append(line_id)
        label_lower = label.lower()
        if label_lower == "risk band":
            components.append(
                {
                    "id": line_id,
                    "component": "Text",
                    "text": f"Risk band: {value}",
                    "variant": "h4",
                }
            )
        elif label_lower == "leading hypothesis":
            components.append(
                {
                    "id": f"{line_id}-label",
                    "component": "Text",
                    "text": "Leading hypothesis",
                    "variant": "caption",
                }
            )
            hypo_id = f"{line_id}-body"
            body_children.append(hypo_id)
            components.append(
                {"id": hypo_id, "component": "Text", "text": value, "variant": "body"}
            )
        elif label_lower.startswith("open question"):
            question_ids.append(line_id)
            components.append(
                {
                    "id": line_id,
                    "component": "Text",
                    "text": f"{label}: {value}",
                    "variant": "caption",
                }
            )
        elif label_lower.startswith("red flag"):
            question_ids.append(line_id)
            components.append(
                {
                    "id": line_id,
                    "component": "Text",
                    "text": f"{label}: {value}",
                    "variant": "body",
                }
            )
        else:
            components.append(
                {
                    "id": line_id,
                    "component": "Text",
                    "text": f"{label}: {value}",
                    "variant": "body",
                }
            )

    if output_payload.get("error") == "failed_to_parse_output" and not lines:
        components.append(
            {
                "id": "parse-note",
                "component": "Text",
                "text": "Structured JSON output was incomplete; review the chat summary above.",
                "variant": "caption",
            }
        )
        body_children.append("parse-note")

    action_children: list[str] = []
    if status == AgentRunStatus.AWAITING_REVIEW:
        components.extend(
            [
                {
                    "id": "approve-btn",
                    "component": "Button",
                    "variant": "primary",
                    "child": "approve-label",
                    "action": {
                        "event": {
                            "name": "approve_run",
                            "context": {"runId": str(run_id)},
                        }
                    },
                },
                {"id": "approve-label", "component": "Text", "text": "Approve run"},
            ]
        )
        action_children.append("approve-btn")

    if action_children:
        body_children.append("actions")
        components.append(
            {
                "id": "actions",
                "component": "Row",
                "children": action_children,
                "justify": "start",
            }
        )

    components[1]["children"] = body_children

    return [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": surface_id, "catalogId": catalog_id},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": surface_id,
                "components": components,
            },
        },
    ]
