"""Per-stage A2A Starlette app (``to_a2a``) for remote AML workflow stages."""

from __future__ import annotations

import os

from google.adk.a2a.utils.agent_to_a2a import to_a2a
from starlette.applications import Starlette

from ...models.enums import AgentName
from .host_agent import build_a2a_host_agent


def create_a2a_stage_app(
    *,
    agent_name: AgentName | None = None,
    public_host: str | None = None,
    port: int | None = None,
) -> Starlette:
    """Build the A2A server for one AML stage.

    Environment
    -----------
    ``AML_A2A_STAGE``
        Required when ``agent_name`` is omitted — one of ``AgentName`` values.
    ``AML_A2A_PUBLIC_HOST``
        Hostname remote clients use in the agent card RPC URL (default ``localhost``).
    ``PORT``
        Listen port embedded in the agent card (default ``8101``).
    """
    if agent_name is None:
        raw = os.environ.get("AML_A2A_STAGE", "").strip()
        if not raw:
            raise ValueError("AML_A2A_STAGE is required for the A2A stage server")
        agent_name = AgentName(raw)

    host = public_host or os.getenv("AML_A2A_PUBLIC_HOST", "localhost")
    listen_port = port or int(os.getenv("PORT", "8101"))

    agent = build_a2a_host_agent(agent_name)
    return to_a2a(
        agent,
        host=host,
        port=listen_port,
        protocol="http",
    )


def get_app() -> Starlette:
    """Uvicorn factory entrypoint (``uvicorn module:get_app --factory``)."""
    return create_a2a_stage_app()
