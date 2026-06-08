"""Start / complete agent_runs for ADK web hybrid invocations."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from google.adk.sessions.session import Session

from ...db.client import get_aml_db_client
from ...db.state_loader import load_investigation_state
from ...models.enums import ActorType, AgentName, AuditEventType, GateStatus
from ...models.state import AgentRun, TokenUsage
from ...orchestrator.service import GateBlocked
from ...orchestrator.transitions import is_terminal_status
from ...utils.hashing import idempotency_key
from ...utils.masking import mask_dict
from ..base import AgentContext, AgentResult
from ..context import AgentToolContext, _current
from .event_text import (
    collect_recorded_ids,
    session_final_text,
    session_output_payload,
    session_reasoning_log,
    session_tool_calls,
)

log = logging.getLogger(__name__)


def _stage_wrapper(agent_name: AgentName):
    """Lazy load to avoid import cycle with ``stages/*/agent.py``."""
    if agent_name == AgentName.INITIAL_ASSESSMENT:
        from ..initial_assessment import InitialAssessmentAgent

        return InitialAssessmentAgent()
    if agent_name == AgentName.TRANSACTION_ENRICHMENT:
        from ..transaction_enrichment import TransactionEnrichmentAgent

        return TransactionEnrichmentAgent()
    if agent_name == AgentName.DUE_DILIGENCE:
        from ..due_diligence import DueDiligenceAgent

        return DueDiligenceAgent()
    if agent_name == AgentName.CASE_ANALYSIS:
        from ..case_analysis import CaseAnalysisAgent

        return CaseAnalysisAgent()
    raise LookupError(f"no ADK web lifecycle wrapper for {agent_name.value}")


@dataclass
class AdkWebInvocation:
    """Resources bound for one ADK web agent turn."""

    case_number: str
    case_id: UUID
    agent_name: AgentName
    run: AgentRun
    assembled_prompt: str
    started_monotonic: float = field(default_factory=time.monotonic)
    conn_cm: Any = None
    ctx_token: Any = None


def build_user_prompt(agent_name: AgentName, ctx: AgentContext) -> str:
    wrapper = _stage_wrapper(agent_name)
    return wrapper.build_user_prompt(ctx)


async def start_adk_web_run(
    *,
    case_number: str,
    agent_name: AgentName,
    invocation_id: str,
) -> AdkWebInvocation:
    """Phase-1 orchestrator logic: resolve case, create/resume run, build prompt."""
    db = get_aml_db_client()
    wrapper = _stage_wrapper(agent_name)

    async with db.transaction() as repos:
        case = await repos.cases.get_by_number(case_number)
        if case is None:
            raise LookupError(f"case not found: {case_number}")
        if case.locked:
            raise PermissionError(f"case {case_number} is locked")

        state = await load_investigation_state(repos, case.id)

        blocking = next(
            (
                g
                for g in state.gates
                if g.blocks_agent == agent_name
                and g.status == GateStatus.OPEN_REQUIRED
            ),
            None,
        )
        if blocking is not None:
            raise GateBlocked(agent_name, blocking)

        if agent_name == AgentName.DUE_DILIGENCE:
            unverified = [p for p in state.parties if not p.verified]
            if unverified:
                names = ", ".join(p.party_name for p in unverified[:5])
                raise PermissionError(
                    f"Due Diligence blocked: {len(unverified)} unverified "
                    f"parties ({names}). Resolve PARTIES_VERIFIED gate first."
                )

        extra_input = {"source": "adk_web", "invocation_id": invocation_id}
        input_payload = wrapper.idempotency_input(extra_input)
        key = idempotency_key(
            case_id=case.id,
            agent=agent_name.value,
            input_payload=input_payload,
        )
        run, created = await repos.agent_runs.get_or_create_run(
            case_id=case.id,
            agent=agent_name,
            idempotency_key=key,
            input_payload=input_payload,
            model_name=wrapper.model_name,
        )
        if not created and is_terminal_status(run.status):
            log.info(
                "runtime.start.noop terminal_status=%s run_id=%s",
                run.status.value,
                run.id,
            )
        else:
            run = await repos.agent_runs.mark_running(run.id)
            await repos.audit.append(
                case_id=case.id,
                actor_type=ActorType.AGENT,
                actor_id=agent_name.value,
                event_type=AuditEventType.AGENT_STARTED,
                event_payload={
                    "run_id": str(run.id),
                    "attempt": run.attempt,
                    "resumed": not created,
                    "source": "adk_web",
                    "input": mask_dict(input_payload),
                },
                agent_run_id=run.id,
            )

        prompt = build_user_prompt(
            agent_name,
            AgentContext(state=state, repos=repos, run=run, extra_input=extra_input),
        )
        case_id = case.id

    conn_cm = db.connection()
    repos = await conn_cm.__aenter__()
    tool_ctx = AgentToolContext(
        case_id=case_id,
        agent_run_id=run.id,
        actor_id=agent_name.value,
        repos=repos,
    )
    token = _current.set(tool_ctx)

    return AdkWebInvocation(
        case_number=case_number,
        case_id=case_id,
        agent_name=agent_name,
        run=run,
        assembled_prompt=prompt,
        conn_cm=conn_cm,
        ctx_token=token,
    )


async def complete_adk_web_run(
    inv: AdkWebInvocation,
    session: Session,
) -> AgentRun:
    """Phase-3 orchestrator logic: persist output, audit, optional stage advance."""
    db = get_aml_db_client()
    wrapper = _stage_wrapper(inv.agent_name)

    output = session_output_payload(session)
    reasoning = session_reasoning_log(session)
    tool_calls = session_tool_calls(session)
    evidence_ids, party_ids = collect_recorded_ids(tool_calls)
    duration_ms = int((time.monotonic() - inv.started_monotonic) * 1000)

    summary_text = session_final_text(session)
    summary = (summary_text[:237] + "…") if len(summary_text) > 240 else summary_text

    async with db.transaction() as repos:
        state = await load_investigation_state(repos, inv.case_id)
        ctx = AgentContext(state=state, repos=repos, run=inv.run)
        next_gates = wrapper.next_gates(ctx, output)

        result = AgentResult(
            output_payload=output,
            reasoning=reasoning,
            reasoning_summary=summary or None,
            tokens=TokenUsage(),
            requires_review=wrapper.requires_review,
            new_evidence_ids=[UUID(e) for e in evidence_ids],
            new_party_ids=[UUID(p) for p in party_ids],
            next_gates=next_gates,
        )

        result = await wrapper.finalize_adk_web_result(ctx, result)

        updated = await repos.agent_runs.mark_completed(
            run_id=inv.run.id,
            output_payload=result.output_payload,
            reasoning=result.reasoning,
            reasoning_summary=result.reasoning_summary,
            tokens=result.tokens,
            duration_ms=duration_ms,
            requires_review=result.requires_review,
        )

        token_audit = (
            result.tokens.model_dump(mode="json") if result.tokens else None
        )
        await repos.audit.append(
            case_id=inv.case_id,
            actor_type=ActorType.AGENT,
            actor_id=inv.agent_name.value,
            event_type=AuditEventType.AGENT_REASONING,
            event_payload={
                "run_id": str(updated.id),
                "summary": result.reasoning_summary,
                "tokens": token_audit,
                "source": "adk_web",
            },
            reasoning_text=result.reasoning,
            agent_run_id=updated.id,
        )
        await repos.audit.append(
            case_id=inv.case_id,
            actor_type=ActorType.AGENT,
            actor_id=inv.agent_name.value,
            event_type=AuditEventType.AGENT_COMPLETED,
            event_payload={
                "run_id": str(updated.id),
                "duration_ms": duration_ms,
                "requires_review": result.requires_review,
                "source": "adk_web",
                "evidence_ids": [str(e) for e in result.new_evidence_ids],
                "party_ids": [str(p) for p in result.new_party_ids],
            },
            agent_run_id=updated.id,
        )

        for gate in result.next_gates:
            opened = await repos.gates.open(
                case_id=inv.case_id,
                gate_name=gate.name,
                blocks_agent=gate.blocks_agent,
                notes=gate.notes,
            )
            await repos.audit.append(
                case_id=inv.case_id,
                actor_type=ActorType.SYSTEM,
                actor_id="adk_web",
                event_type=AuditEventType.GATE_OPENED,
                event_payload={
                    "gate_id": str(opened.id),
                    "gate_name": opened.gate_name,
                    "blocks_agent": opened.blocks_agent.value,
                },
                agent_run_id=updated.id,
            )

        if not result.requires_review:
            from .orchestrator_client import build_runtime_orchestrator

            orch = build_runtime_orchestrator()
            await orch._advance_stage(  # noqa: SLF001
                repos,
                case_id=inv.case_id,
                agent_name=inv.agent_name,
                actor_id="adk_web",
            )

        inv.run = updated
        return updated


async def cleanup_adk_web_invocation(inv: AdkWebInvocation | None) -> None:
    """Release DB connection and reset the tool contextvar."""
    if inv is None:
        return
    if inv.ctx_token is not None:
        _current.reset(inv.ctx_token)
        inv.ctx_token = None
    if inv.conn_cm is not None:
        await inv.conn_cm.__aexit__(None, None, None)
        inv.conn_cm = None
