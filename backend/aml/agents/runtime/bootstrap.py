"""One-time DB + provider wiring for standalone ADK web sessions."""

from __future__ import annotations

import logging

from ...db.client import get_aml_db_client
from ...integrations.demo_providers import DemoKycProvider, DemoSearchProvider
from ...integrations.neo4j_provider import build_neo4j_provider_if_configured
from ..tools.data_tools import set_graph_provider, set_kyc_provider, set_search_provider

log = logging.getLogger(__name__)

_bootstrapped = False
_neo4j_provider = None


async def ensure_runtime_ready() -> None:
    """Connect AML Postgres and register data-tool providers (idempotent)."""
    global _bootstrapped, _neo4j_provider

    db = get_aml_db_client()
    await db.connect()

    if _bootstrapped:
        return

    set_kyc_provider(DemoKycProvider())
    set_search_provider(DemoSearchProvider())

    _neo4j_provider = build_neo4j_provider_if_configured()
    if _neo4j_provider is not None:
        try:
            await _neo4j_provider.connect()
            set_graph_provider(_neo4j_provider)
            log.info("runtime.bootstrap.neo4j connected")
        except Exception:  # noqa: BLE001
            log.exception("runtime.bootstrap.neo4j.failed")
            _neo4j_provider = None

    _bootstrapped = True
    log.info("runtime.bootstrap.ready")
