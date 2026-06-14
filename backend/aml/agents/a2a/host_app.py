"""AML host A2A Starlette app — streaming front door on :8100 (Sprint 7)."""

from __future__ import annotations

import logging
import os

from a2a.types import AgentCapabilities
from google.adk.a2a.utils.agent_card_builder import AgentCardBuilder
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from starlette.applications import Starlette

from ...models.enums import AgentName
from .a2ui import apply_a2ui_agent_card_extensions, catalog_for_stage, load_a2ui_config
from .aml_host_agent import build_aml_host_agent
from .sync_async import run_coroutine_sync

log = logging.getLogger(__name__)


def collect_a2ui_catalog_ids() -> list[str]:
    """Aggregate supported A2UI catalog ids from configured workflow stages."""
    cfg = load_a2ui_config()
    if not cfg.enabled:
        return []
    catalog_ids: list[str] = []
    for agent_name in AgentName:
        if not cfg.enabled_for(agent_name):
            continue
        catalog = catalog_for_stage(agent_name)
        if catalog is not None:
            catalog_ids.append(catalog.catalog_id)
    return list(dict.fromkeys(catalog_ids))


async def _build_host_agent_card(agent, *, rpc_url: str) -> object:
    """Build host agent card with streaming enabled; attach A2UI when configured."""
    builder = AgentCardBuilder(
        agent=agent,
        rpc_url=rpc_url,
        capabilities=AgentCapabilities(streaming=True),
    )
    card = await builder.build()

    catalog_ids = collect_a2ui_catalog_ids()
    if catalog_ids:
        a2ui_cfg = load_a2ui_config()
        card = apply_a2ui_agent_card_extensions(
            card,
            catalog_ids=catalog_ids,
            version=a2ui_cfg.version,
        )
    return card


def create_aml_host_app(
    *,
    public_host: str | None = None,
    port: int | None = None,
) -> Starlette:
    """Build the AML host A2A server (orchestrator hub, streaming via ADK executor).

    Environment
    -----------
    ``AML_A2A_PUBLIC_HOST``
        Hostname clients use in the agent card RPC URL (default ``localhost``).
    ``PORT``
        Listen port (default ``8100``).
    ``AML_A2UI_ENABLED`` / ``AML_A2UI_STAGES``
        When enabled, the host card aggregates stage catalog ids for clients.
    """
    host = public_host or os.getenv("AML_A2A_PUBLIC_HOST", "localhost")
    listen_port = port or int(os.getenv("PORT", "8100"))
    rpc_url = f"http://{host}:{listen_port}/"

    agent = build_aml_host_agent()
    agent_card = run_coroutine_sync(_build_host_agent_card(agent, rpc_url=rpc_url))

    return to_a2a(
        agent,
        host=host,
        port=listen_port,
        protocol="http",
        agent_card=agent_card,
    )


def get_app() -> Starlette:
    """Uvicorn factory entrypoint (``uvicorn module:get_app --factory``)."""
    return create_aml_host_app()
