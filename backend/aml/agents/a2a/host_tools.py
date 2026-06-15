"""Deterministic orchestrator tools for the AML A2A host agent (Sprint 7)."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from google.adk.tools import FunctionTool

from ...db.client import get_aml_db_client
from ...db.state_loader import load_investigation_state
from ...models.enums import ActorType, AgentName, AgentRunStatus, AuditEventType, GateStatus
from ...models.state import InvestigationState
from ...orchestrator.service import GateBlocked, Orchestrator
from ..runtime.bootstrap import ensure_runtime_ready
from ..runtime.case_resolver import load_case_by_number
from ..runtime.orchestrator_client import build_runtime_orchestrator
from .analyst_context import require_analyst_id

log = logging.getLogger(__name__)

_orchestrator_override: Orchestrator | None = None


def set_host_orchestrator(orch: Orchestrator | None) -> None:
    """Test helper — inject a stub orchestrator."""
    global _orchestrator_override
    _orchestrator_override = orch


def _get_orchestrator() -> Orchestrator:
    if _orchestrator_override is not None:
        return _orchestrator_override
    return build_runtime_orchestrator()


def _summarize_state(state: InvestigationState) -> dict[str, Any]:
    return {
        "case_number": state.case.case_number,
        "case_id": str(state.case.id),
        "status": state.case.status.value,
        "current_stage": state.case.current_stage.value,
        "locked": state.case.locked,
        "progress": [
            {
                "stage": item.stage.value,
                "agent": item.agent.value,
                "status": item.status.value,
                "latest_run_id": str(item.latest_run_id)
                if item.latest_run_id
                else None,
                "requires_review": item.requires_review,
                "blocking_gate": (
                    {
                        "id": str(item.blocking_gate.id),
                        "name": item.blocking_gate.gate_name,
                    }
                    if item.blocking_gate
                    else None
                ),
            }
            for item in state.progress
        ],
        "open_gates": [
            {
                "id": str(gate.id),
                "name": gate.gate_name,
                "blocks_agent": gate.blocks_agent.value,
            }
            for gate in state.open_gates()
        ],
        "parties": [
            {
                "id": str(party.id),
                "name": party.party_name,
                "verified": party.verified,
            }
            for party in state.parties
        ],
    }


def require_analyst_or_error() -> str | dict[str, Any]:
    """Return analyst id or a structured error dict for tool responses."""
    try:
        return require_analyst_id()
    except PermissionError as err:
        return {"ok": False, "error": str(err)}


async def get_case_state(case_number: str) -> dict[str, Any]:
    """Load a read-only summary of investigation state for a case."""
    analyst = require_analyst_or_error()
    if isinstance(analyst, dict):
        return analyst
    await ensure_runtime_ready()
    try:
        case = await load_case_by_number(case_number.strip().upper())
    except LookupError as err:
        return {"ok": False, "error": str(err)}

    db = get_aml_db_client()
    async with db.connection() as repos:
        state = await load_investigation_state(repos, case.id)
    return {"ok": True, "state": _summarize_state(state)}


async def trigger_workflow_stage(case_number: str, stage: str) -> dict[str, Any]:
    """Trigger one AML workflow stage via the production orchestrator."""
    analyst = require_analyst_or_error()
    if isinstance(analyst, dict):
        return analyst
    try:
        agent_name = AgentName(stage.strip().upper())
    except ValueError:
        return {"ok": False, "error": f"unknown stage: {stage!r}"}

    await ensure_runtime_ready()
    try:
        case = await load_case_by_number(case_number.strip().upper())
    except LookupError as err:
        return {"ok": False, "error": str(err)}
    except PermissionError as err:
        return {"ok": False, "error": str(err)}

    orch = _get_orchestrator()
    try:
        run = await orch.trigger_agent(
            case_id=case.id,
            agent_name=agent_name,
            triggered_by=analyst,
            extra_input={"source": "aml_host_agent"},
        )
    except GateBlocked as err:
        return {
            "ok": False,
            "error": str(err),
            "gate_id": str(err.gate.id),
            "gate_name": err.gate.gate_name,
            "blocks_agent": err.gate.blocks_agent.value,
        }
    except PermissionError as err:
        return {"ok": False, "error": str(err)}

    if run.status == AgentRunStatus.FAILED:
        return {
            "ok": False,
            "error": run.error or f"{run.agent.value} failed",
            "run_id": str(run.id),
            "agent": run.agent.value,
            "status": run.status.value,
        }

    return {
        "ok": True,
        "run_id": str(run.id),
        "agent": run.agent.value,
        "status": run.status.value,
        "output_payload": run.output_payload,
        "requires_review": run.status == AgentRunStatus.AWAITING_REVIEW,
    }


async def approve_agent_run(run_id: str) -> dict[str, Any]:
    """Approve an agent run awaiting human review."""
    analyst = require_analyst_or_error()
    if isinstance(analyst, dict):
        return analyst
    await ensure_runtime_ready()
    orch = _get_orchestrator()
    db = get_aml_db_client()
    try:
        async with db.connection() as repos:
            resolved_id = await repos.agent_runs.resolve_id(run_id)
            existing = await repos.agent_runs.get(resolved_id)
        if existing is None:
            return {"ok": False, "error": f"agent_run {run_id} not found"}
        if existing.status in (
            AgentRunStatus.APPROVED,
            AgentRunStatus.COMPLETED,
        ):
            return {
                "ok": True,
                "already_approved": True,
                "run_id": str(existing.id),
                "agent": existing.agent.value,
                "status": existing.status.value,
                "message": (
                    "Run is already approved or completed (e.g. via the case UI). "
                    "No further approval needed."
                ),
            }
        if existing.status not in (
            AgentRunStatus.AWAITING_REVIEW,
            AgentRunStatus.MODIFIED,
        ):
            return {
                "ok": False,
                "error": (
                    f"run is {existing.status.value}, not awaiting review "
                    f"(cannot approve)"
                ),
                "run_id": str(existing.id),
                "status": existing.status.value,
            }
        run = await orch.approve_run(run_id=resolved_id, analyst_id=analyst)
    except Exception as err:  # noqa: BLE001 — surface to LLM as structured error
        return {"ok": False, "error": f"{err.__class__.__name__}: {err}"}
    return {
        "ok": True,
        "run_id": str(run.id),
        "agent": run.agent.value,
        "status": run.status.value,
    }


async def approve_awaiting_review_run(
    case_number: str,
    stage: str = "",
) -> dict[str, Any]:
    """Approve the run awaiting review for a case (optional stage filter)."""
    analyst = require_analyst_or_error()
    if isinstance(analyst, dict):
        return analyst
    await ensure_runtime_ready()
    try:
        case = await load_case_by_number(case_number.strip().upper())
    except LookupError as err:
        return {"ok": False, "error": str(err)}
    db = get_aml_db_client()
    try:
        async with db.connection() as repos:
            pending = await repos.agent_runs.list_awaiting_review(case.id)
        if stage.strip():
            try:
                agent_name = AgentName(stage.strip().upper())
            except ValueError:
                return {"ok": False, "error": f"unknown stage: {stage!r}"}
            pending = [r for r in pending if r.agent == agent_name]
        if not pending:
            async with db.connection() as repos:
                all_runs = await repos.agent_runs.list_for_case(case.id)
            if stage.strip():
                scoped = [r for r in all_runs if r.agent == agent_name]
                latest = max(scoped, key=lambda r: r.attempt) if scoped else None
            else:
                reviewable = [
                    r
                    for r in all_runs
                    if r.status in (
                        AgentRunStatus.APPROVED,
                        AgentRunStatus.COMPLETED,
                    )
                ]
                latest = max(reviewable, key=lambda r: r.completed_at or r.created_at)
                if not reviewable:
                    latest = None
            if latest and latest.status in (
                AgentRunStatus.APPROVED,
                AgentRunStatus.COMPLETED,
            ):
                return {
                    "ok": True,
                    "already_approved": True,
                    "run_id": str(latest.id),
                    "agent": latest.agent.value,
                    "status": latest.status.value,
                    "message": (
                        "No run awaiting review — latest run is already approved "
                        "or completed (often approved in the case UI)."
                    ),
                }
            return {
                "ok": False,
                "error": "no runs awaiting review for this case",
                "hint": "Call get_case_state to see current stage status.",
            }
        if len(pending) > 1:
            return {
                "ok": False,
                "error": "multiple runs awaiting review — specify stage or full run_id",
                "run_ids": [str(r.id) for r in pending],
            }
        return await approve_agent_run(str(pending[0].id))
    except Exception as err:  # noqa: BLE001
        return {"ok": False, "error": f"{err.__class__.__name__}: {err}"}


async def reject_agent_run(run_id: str, reason: str) -> dict[str, Any]:
    """Reject an agent run awaiting human review."""
    analyst = require_analyst_or_error()
    if isinstance(analyst, dict):
        return analyst
    await ensure_runtime_ready()
    orch = _get_orchestrator()
    db = get_aml_db_client()
    try:
        async with db.connection() as repos:
            resolved_id = await repos.agent_runs.resolve_id(run_id)
        run = await orch.reject_run(
            run_id=resolved_id,
            analyst_id=analyst,
            reason=reason.strip() or "rejected via aml host agent",
        )
    except Exception as err:  # noqa: BLE001
        return {"ok": False, "error": f"{err.__class__.__name__}: {err}"}
    return {
        "ok": True,
        "run_id": str(run.id),
        "agent": run.agent.value,
        "status": run.status.value,
    }


async def resolve_human_gate(
    gate_id: str,
    status: str,
    notes: str = "",
) -> dict[str, Any]:
    """Resolve a human gate (APPROVED or REJECTED)."""
    analyst = require_analyst_or_error()
    if isinstance(analyst, dict):
        return analyst
    try:
        gate_status = GateStatus(status.strip().upper())
    except ValueError:
        return {"ok": False, "error": f"invalid gate status: {status!r}"}

    await ensure_runtime_ready()
    orch = _get_orchestrator()
    try:
        gate = await orch.resolve_gate(
            gate_id=UUID(gate_id),
            status=gate_status,
            analyst_id=analyst,
            notes=notes.strip() or None,
        )
    except Exception as err:  # noqa: BLE001
        return {"ok": False, "error": f"{err.__class__.__name__}: {err}"}
    return {
        "ok": True,
        "gate_id": str(gate.id),
        "gate_name": gate.gate_name,
        "status": gate.status.value,
    }


async def verify_case_party(party_id: str) -> dict[str, Any]:
    """Mark a case party as verified (typical PARTIES_VERIFIED gate driver)."""
    analyst = require_analyst_or_error()
    if isinstance(analyst, dict):
        return analyst
    await ensure_runtime_ready()
    db = get_aml_db_client()
    try:
        async with db.transaction() as repos:
            party = await repos.parties.mark_verified(
                party_id=UUID(party_id),
                analyst_id=analyst,
            )
            await repos.audit.append(
                case_id=party.case_id,
                actor_type=ActorType.ANALYST,
                actor_id=analyst,
                event_type=AuditEventType.HUMAN_OVERRIDE,
                event_payload={
                    "object": "case_party",
                    "party_id": str(party.id),
                    "party_external_id": party.party_external_id,
                    "verified": True,
                    "source": "aml_host_agent",
                },
            )
    except Exception as err:  # noqa: BLE001
        return {"ok": False, "error": f"{err.__class__.__name__}: {err}"}
    return {
        "ok": True,
        "party_id": str(party.id),
        "party_name": party.party_name,
        "verified": party.verified,
    }


HOST_AGENT_TOOLS: tuple[FunctionTool, ...] = (
    FunctionTool(func=get_case_state),
    FunctionTool(func=trigger_workflow_stage),
    FunctionTool(func=approve_awaiting_review_run),
    FunctionTool(func=approve_agent_run),
    FunctionTool(func=reject_agent_run),
    FunctionTool(func=resolve_human_gate),
    FunctionTool(func=verify_case_party),
)
