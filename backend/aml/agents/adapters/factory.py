"""Build per-stage :class:`AgentExecutionPort` instances from config."""

from __future__ import annotations

import logging

from ...config.agent_transport import (
    AgentTransport,
    AgentTransportConfig,
    load_agent_transport_config,
)
from ...models.enums import AgentName
from ..base import BaseAgent
from ..ports import AgentExecutionPort
from .a2a import A2aAdapter
from .in_process import InProcessAdapter

log = logging.getLogger(__name__)

_IN_PROCESS = InProcessAdapter()


def build_execution_ports(
    agents: dict[AgentName, BaseAgent],
    config: AgentTransportConfig | None = None,
) -> dict[AgentName, AgentExecutionPort]:
    """Return one execution port per registered stage agent.

    Default: all stages use :class:`InProcessAdapter` (identical to pre-adapter
    behaviour).  Per-stage ``a2a`` overrides construct :class:`A2aAdapter`
    clients that call remote ``to_a2a`` stage hosts.
    """
    config = config or load_agent_transport_config()
    ports: dict[AgentName, AgentExecutionPort] = {}

    for agent_name in agents:
        transport = config.transport_for(agent_name)
        if transport == AgentTransport.IN_PROCESS:
            ports[agent_name] = _IN_PROCESS
            log.debug(
                "adapter.factory agent=%s transport=in_process",
                agent_name.value,
            )
            continue

        card_url = config.a2a_endpoint(agent_name)
        if not card_url:
            raise ValueError(
                f"A2A transport selected for {agent_name.value} but "
                f"AML_A2A_{agent_name.value}_URL is not set"
            )
        ports[agent_name] = A2aAdapter(
            agent_name=agent_name,
            agent_card_url=card_url,
            timeout_seconds=config.a2a_timeout_seconds,
        )
        log.info(
            "adapter.factory agent=%s transport=a2a card=%s",
            agent_name.value,
            card_url,
        )

    return ports
