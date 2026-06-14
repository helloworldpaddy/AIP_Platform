"""Per-stage A2A Starlette app (``to_a2a``) for remote AML workflow stages."""

from __future__ import annotations

import logging
import os

from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
from google.adk.a2a.executor.config import A2aAgentExecutorConfig
from google.adk.a2a.utils.agent_card_builder import AgentCardBuilder
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.runners import Runner
from starlette.applications import Starlette

from ...models.enums import AgentName
from .a2ui import (
    apply_a2ui_agent_card_extensions,
    build_a2ui_event_converter,
    catalog_for_stage,
    load_a2ui_config,
)
from .host_agent import build_a2a_host_agent
from .sync_async import run_coroutine_sync

log = logging.getLogger(__name__)


def _build_executor_config(*, agent_name: AgentName) -> A2aAgentExecutorConfig | None:
    """Return A2UI-aware executor config when enabled for this stage."""
    if catalog_for_stage(agent_name) is None:
        return None
    converter = build_a2ui_event_converter()
    return A2aAgentExecutorConfig(event_converter=converter)


async def _build_agent_card(
    agent,
    *,
    rpc_url: str,
    agent_name: AgentName,
) -> object | None:
    """Build agent card and attach A2UI extension when configured."""
    a2ui_cfg = load_a2ui_config()
    catalog = catalog_for_stage(agent_name)
    if not a2ui_cfg.enabled_for(agent_name) or catalog is None:
        return None

    builder = AgentCardBuilder(agent=agent, rpc_url=rpc_url)
    card = await builder.build()
    return apply_a2ui_agent_card_extensions(
        card,
        catalog_ids=[catalog.catalog_id],
        version=a2ui_cfg.version,
    )


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
    ``AML_A2UI_ENABLED``
        When ``true``, Initial Assessment (or ``AML_A2UI_STAGES``) advertises
        the A2UI extension and emits ``application/json+a2ui`` DataParts.
    """
    if agent_name is None:
        raw = os.environ.get("AML_A2A_STAGE", "").strip()
        if not raw:
            raise ValueError("AML_A2A_STAGE is required for the A2A stage server")
        agent_name = AgentName(raw)

    host = public_host or os.getenv("AML_A2A_PUBLIC_HOST", "localhost")
    listen_port = port or int(os.getenv("PORT", "8101"))
    rpc_url = f"http://{host}:{listen_port}/"

    agent = build_a2a_host_agent(agent_name)
    executor_config = _build_executor_config(agent_name=agent_name)

    agent_card = run_coroutine_sync(
        _build_agent_card(agent, rpc_url=rpc_url, agent_name=agent_name)
    )

    def agent_executor_factory(runner: Runner) -> A2aAgentExecutor:
        if executor_config is None:
            return A2aAgentExecutor(runner=runner)
        # A2uiEventConverter implements the legacy event converter signature.
        return A2aAgentExecutor(
            runner=runner,
            config=executor_config,
            use_legacy=True,
        )

    return to_a2a(
        agent,
        host=host,
        port=listen_port,
        protocol="http",
        agent_card=agent_card,
        agent_executor_factory=agent_executor_factory,
    )


def get_app() -> Starlette:
    """Uvicorn factory entrypoint (``uvicorn module:get_app --factory``)."""
    return create_a2a_stage_app()
