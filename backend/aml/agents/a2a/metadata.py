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
) -> dict[str, Any]:
    """Metadata attached to each A2A ``send_message`` call."""
    return {
        AML_A2A_METADATA_KEY: {
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
    }


def parse_tool_gateway_from_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not metadata:
        return None
    aml = metadata.get(AML_A2A_METADATA_KEY)
    if not isinstance(aml, dict):
        return None
    gateway = aml.get("tool_gateway")
    return gateway if isinstance(gateway, dict) else None
