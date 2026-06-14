"""Shared A2A request metadata between orchestrator client and stage hosts."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from ..ports import ToolGatewaySpec
from ...models.enums import AgentName

AML_A2A_METADATA_KEY = "aml"


def build_a2a_request_metadata(
    *,
    case_id: UUID,
    run_id: UUID,
    agent_name: AgentName,
    tool_gateway: ToolGatewaySpec,
    analyst_id: str | None = None,
) -> dict[str, Any]:
    """Metadata attached to each A2A ``send_message`` call."""
    aml: dict[str, Any] = {
        "case_id": str(case_id),
        "run_id": str(run_id),
        "agent": agent_name.value,
        "tool_gateway": {
            "transport": tool_gateway.transport,
            "url": tool_gateway.url,
            "token": tool_gateway.token,
            "allowed_tools": list(tool_gateway.allowed_tools),
        },
    }
    if analyst_id:
        aml["analyst_id"] = analyst_id.strip()
    return {AML_A2A_METADATA_KEY: aml}


def parse_aml_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not metadata:
        return None
    aml = metadata.get(AML_A2A_METADATA_KEY)
    return aml if isinstance(aml, dict) else None


def parse_analyst_id_from_metadata(metadata: dict[str, Any] | None) -> str | None:
    """Extract analyst identity from A2A message metadata (Sprint 7 host agent)."""
    aml = parse_aml_metadata(metadata)
    if aml is None:
        return None
    raw = aml.get("analyst_id") or aml.get("analystId")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def parse_tool_gateway_from_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    aml = parse_aml_metadata(metadata)
    if aml is None:
        return None
    gateway = aml.get("tool_gateway")
    return gateway if isinstance(gateway, dict) else None


def build_host_client_metadata(*, analyst_id: str) -> dict[str, Any]:
    """Minimal metadata for browser → AML host agent requests."""
    return {AML_A2A_METADATA_KEY: {"analyst_id": analyst_id.strip()}}
