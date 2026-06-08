"""Build ADK agents for independent A2A stage hosts."""

from __future__ import annotations

import logging
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.a2a.converters.request_converter import A2A_METADATA_KEY

from agents.rag_agent.config.settings import get_settings

from ...models.enums import AgentName
from ..adk_runner import build_llm_agent
from ..prompts import (
    CASE_ANALYSIS_INSTRUCTION,
    DUE_DILIGENCE_INSTRUCTION,
    INITIAL_ASSESSMENT_INSTRUCTION,
    TRANSACTION_ENRICHMENT_INSTRUCTION,
)
from .gateway_tools import (
    GatewayToolContext,
    gateway_tools_named,
    reset_gateway_tool_context,
    set_gateway_tool_context,
)
from .metadata import parse_tool_gateway_from_metadata

log = logging.getLogger(__name__)

_STAGE_CONFIG: dict[AgentName, dict[str, Any]] = {
    AgentName.INITIAL_ASSESSMENT: {
        "adk_name": "initial_assessment",
        "instruction": INITIAL_ASSESSMENT_INSTRUCTION,
        "tool_names": ("policy_rag_search", "record_evidence"),
        "description": "AML stage 1 — Initial Assessment (A2A host).",
    },
    AgentName.TRANSACTION_ENRICHMENT: {
        "adk_name": "transaction_enrichment",
        "instruction": TRANSACTION_ENRICHMENT_INSTRUCTION,
        "tool_names": ("neo4j_hop_traversal", "record_evidence", "record_party"),
        "description": "AML stage 2 — Transaction Enrichment (A2A host).",
    },
    AgentName.DUE_DILIGENCE: {
        "adk_name": "due_diligence",
        "instruction": DUE_DILIGENCE_INSTRUCTION,
        "tool_names": ("kyc_lookup", "external_search", "record_evidence"),
        "description": "AML stage 3 — Due Diligence (A2A host).",
    },
    AgentName.CASE_ANALYSIS: {
        "adk_name": "case_analysis",
        "instruction": CASE_ANALYSIS_INSTRUCTION,
        "tool_names": ("record_evidence",),
        "description": "AML stage 4 — Case Analysis (A2A host).",
    },
}


async def bind_tool_gateway_from_a2a_metadata(
    callback_context: CallbackContext,
) -> None:
    """Read orchestrator tool-gateway credentials from A2A request metadata."""
    inv = callback_context.get_invocation_context()
    custom = inv.run_config.custom_metadata or {}
    gateway = parse_tool_gateway_from_metadata(custom.get(A2A_METADATA_KEY))
    if gateway is None:
        log.warning(
            "a2a.host missing tool_gateway metadata agent=%s",
            callback_context.agent_name,
        )
        return

    url = str(gateway.get("url") or "")
    token = str(gateway.get("token") or "")
    allowed = tuple(gateway.get("allowed_tools") or ())
    if not url or not token or not allowed:
        log.warning(
            "a2a.host incomplete tool_gateway metadata agent=%s",
            callback_context.agent_name,
        )
        return

    ctx = GatewayToolContext(url=url, token=token, allowed_tools=allowed)
    reset_token = set_gateway_tool_context(ctx)
    callback_context.state["_aml_gateway_reset"] = reset_token
    callback_context.state["aml_tool_gateway"] = gateway


async def reset_tool_gateway_from_a2a_metadata(
    callback_context: CallbackContext,
) -> None:
    reset_token = callback_context.state.get("_aml_gateway_reset")
    if reset_token is not None:
        reset_gateway_tool_context(reset_token)


def build_a2a_host_agent(agent_name: AgentName) -> LlmAgent:
    """Construct a stage agent that proxies tools through the orchestrator gateway."""
    cfg = _STAGE_CONFIG.get(agent_name)
    if cfg is None:
        raise LookupError(f"no A2A host config for {agent_name.value}")

    return build_llm_agent(
        name=cfg["adk_name"],
        instruction=cfg["instruction"],
        model=get_settings().gemini.generation_model,
        tools=gateway_tools_named(list(cfg["tool_names"])),
        temperature=0.1,
        description=cfg["description"],
        before_agent_callback=bind_tool_gateway_from_a2a_metadata,
        after_agent_callback=reset_tool_gateway_from_a2a_metadata,
    )
