"""Per-stage agent transport configuration (in-process vs A2A).

Environment variables
---------------------
``AML_AGENT_TRANSPORT_DEFAULT``
    ``in_process`` (default) or ``a2a``.

``AML_AGENT_TRANSPORT_<STAGE>``
    Override for one stage, e.g. ``AML_AGENT_TRANSPORT_DUE_DILIGENCE=a2a``.
    Stage names use the :class:`AgentName` enum value (uppercase, underscores).

``AML_A2A_<STAGE>_URL``
    A2A agent card URL when transport is ``a2a``, e.g.
    ``AML_A2A_DUE_DILIGENCE_URL=http://dd-agent:8103/.well-known/agent-card.json``.

``AML_A2A_TIMEOUT_SECONDS``
    Wall-clock timeout for remote A2A HTTP calls (default ``600``).

``AML_A2A_CIRCUIT_FAILURE_THRESHOLD``
    Consecutive failures before the A2A circuit opens (default ``5``).

``AML_A2A_CIRCUIT_RECOVERY_SECONDS``
    Seconds before a half-open probe is allowed (default ``60``).

Sprint 3: ``a2a`` transport invokes remote stage hosts via :class:`A2aAdapter`
and the run-scoped tool gateway (Sprint 2).

Sprint 4: set ``AML_ADK_MODE=orchestrator`` in ``adk web`` so hybrid callbacks
call :meth:`Orchestrator.trigger_agent` and inherit this transport config.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum

from ..models.enums import AgentName


class AgentTransport(str, Enum):
    IN_PROCESS = "in_process"
    A2A = "a2a"


def _parse_transport(raw: str | None, *, default: AgentTransport) -> AgentTransport:
    if raw is None or not raw.strip():
        return default
    normalized = raw.strip().lower().replace("-", "_")
    try:
        return AgentTransport(normalized)
    except ValueError as err:
        raise ValueError(
            f"invalid agent transport {raw!r}; expected in_process or a2a"
        ) from err


@dataclass(frozen=True)
class AgentTransportConfig:
    """Resolved transport mode per AML workflow stage."""

    default_transport: AgentTransport = AgentTransport.IN_PROCESS
    stage_transport: dict[AgentName, AgentTransport] = field(default_factory=dict)
    a2a_agent_card_urls: dict[AgentName, str] = field(default_factory=dict)
    a2a_timeout_seconds: float = 600.0

    def transport_for(self, agent: AgentName) -> AgentTransport:
        return self.stage_transport.get(agent, self.default_transport)

    def a2a_endpoint(self, agent: AgentName) -> str | None:
        return self.a2a_agent_card_urls.get(agent)


def load_agent_transport_config() -> AgentTransportConfig:
    """Load transport settings from environment (idempotent, no side effects)."""
    default = _parse_transport(
        os.getenv("AML_AGENT_TRANSPORT_DEFAULT"),
        default=AgentTransport.IN_PROCESS,
    )

    stage_transport: dict[AgentName, AgentTransport] = {}
    a2a_urls: dict[AgentName, str] = {}

    for agent in AgentName:
        env_key = f"AML_AGENT_TRANSPORT_{agent.value}"
        override = os.getenv(env_key)
        if override is not None:
            stage_transport[agent] = _parse_transport(override, default=default)

        url_key = f"AML_A2A_{agent.value}_URL"
        url = os.getenv(url_key)
        if url and url.strip():
            a2a_urls[agent] = url.strip()

    timeout_raw = os.getenv("AML_A2A_TIMEOUT_SECONDS")
    timeout = float(timeout_raw) if timeout_raw else 600.0

    return AgentTransportConfig(
        default_transport=default,
        stage_transport=stage_transport,
        a2a_agent_card_urls=a2a_urls,
        a2a_timeout_seconds=timeout,
    )
