"""FastAPI dependency callables.

Three responsibilities:
    1. Hand out singletons for the AML pool client and the orchestrator.
    2. Resolve the "current analyst" from a request header (`X-Analyst-Id`).
       Real deployments would replace this with a JWT / OIDC verifier — the
       header is the simplest seam that keeps every route auth-aware today.
    3. Provide a `current_state` helper that loads `InvestigationState`
       inside a read-only connection so handler bodies stay short.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, Header, HTTPException, Path, status

from ..agents.registry import build_default_agents
from ..agents.tool_gateway import ToolGatewayService, build_tool_gateway_service
from ..config.agent_transport import load_agent_transport_config
from ..db.client import AmlDbClient, get_aml_db_client
from ..db.state_loader import load_investigation_state
from ..models.state import InvestigationState
from ..orchestrator import Orchestrator

# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------

_orchestrator: Orchestrator | None = None
_tool_gateway: ToolGatewayService | None = None


def get_db() -> AmlDbClient:
    return get_aml_db_client()


def get_tool_gateway(db: AmlDbClient = Depends(get_db)) -> ToolGatewayService:
    global _tool_gateway
    if _tool_gateway is None:
        _tool_gateway = build_tool_gateway_service(db)
    return _tool_gateway


def get_orchestrator(db: AmlDbClient = Depends(get_db)) -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        transport_config = load_agent_transport_config()
        agents = build_default_agents()
        _orchestrator = Orchestrator(
            db,
            agents=agents,
            transport_config=transport_config,
            tool_gateway=build_tool_gateway_service(db),
        )
    return _orchestrator


# ---------------------------------------------------------------------------
# Request-scoped helpers
# ---------------------------------------------------------------------------


def current_analyst(
    x_analyst_id: str | None = Header(default=None, alias="X-Analyst-Id"),
) -> str:
    """Identify the analyst making the request.

    Required on every mutating endpoint so audit rows attribute correctly.
    Replace with a real auth dependency when wiring SSO / OIDC.
    """
    if not x_analyst_id or not x_analyst_id.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing X-Analyst-Id header",
        )
    return x_analyst_id.strip()


async def get_state(
    case_id: UUID = Path(...),
    db: AmlDbClient = Depends(get_db),
) -> InvestigationState:
    async with db.connection() as repos:
        try:
            return await load_investigation_state(repos, case_id)
        except LookupError as err:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(err)
            ) from err
