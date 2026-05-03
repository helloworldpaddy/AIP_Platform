"""Orchestrator — the workflow engine.

Public API (everything FastAPI / ADK call into):

    trigger_agent(case_id, agent, *, triggered_by, extra_input)
        Idempotent: re-triggering with the same `extra_input` resumes the
        prior run instead of starting a new one.  Wraps the agent in
        rate-limit retries; on success records the CoT and opens any
        gates the agent declared.

    approve_run(run_id, analyst_id)        — HITL: clear AWAITING_REVIEW
    reject_run(run_id, analyst_id, reason)
    apply_override(run_id, analyst_id, new_output, diff_ops)
    resolve_gate(gate_id, status, analyst_id, notes)
    submit_narrative(narrative_id, analyst_id) — locks the case

Every public method records a hash-chained `audit_trail` event so the
behaviour of the agent + analyst is fully reconstructible.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from ..agents.base import AgentContext, AgentResult, BaseAgent, GateSpec
from ..db.client import AmlDbClient
from ..db.state_loader import load_investigation_state
from ..models.enums import (
    ActorType,
    AgentName,
    AgentRunStatus,
    AuditEventType,
    CaseStage,
    CaseStatus,
    GateStatus,
)
from ..models.state import AgentRun, HumanGate, InvestigationState, Narrative
from ..utils.hashing import idempotency_key
from ..utils.masking import mask_dict
from ..utils.rate_limit import RetryExhausted, call_with_retry
from .transitions import (
    NEXT_AGENT_FOR_STAGE,
    NEXT_STAGE,
    STAGE_FOR_AGENT,
    is_terminal_status,
    stage_lt,
)

log = logging.getLogger(__name__)


class GateBlocked(RuntimeError):
    """Raised when an agent trigger is refused because of an open human gate."""

    def __init__(self, agent: AgentName, gate: HumanGate) -> None:
        super().__init__(
            f"agent {agent.value} blocked by open gate '{gate.gate_name}'"
        )
        self.agent = agent
        self.gate = gate


class Orchestrator:
    def __init__(
        self,
        db: AmlDbClient,
        agents: dict[AgentName, BaseAgent],
        *,
        max_retry_attempts: int = 4,
    ) -> None:
        self._db = db
        self._agents = agents
        self._max_attempts = max_retry_attempts

    # =========================================================================
    # Agent triggers
    # =========================================================================
    async def trigger_agent(
        self,
        *,
        case_id: UUID,
        agent_name: AgentName,
        triggered_by: str,
        extra_input: dict[str, Any] | None = None,
    ) -> AgentRun:
        agent = self._require_agent(agent_name)
        extra_input = extra_input or {}

        # ---------- Phase 1: gate check + get-or-create the agent_run row ----
        async with self._db.transaction() as repos:
            state = await load_investigation_state(repos, case_id)
            if state.case.locked:
                raise PermissionError(
                    f"case {case_id} is locked; no further agent triggers"
                )

            # Re-validate any human gate that blocks this agent.
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

            input_payload = agent.idempotency_input(extra_input)
            key = idempotency_key(
                case_id=case_id, agent=agent_name.value, input_payload=input_payload
            )
            run, created = await repos.agent_runs.get_or_create_run(
                case_id=case_id,
                agent=agent_name,
                idempotency_key=key,
                input_payload=input_payload,
                model_name=agent.model_name,
            )

            # Resume / no-op decisions.
            if not created and is_terminal_status(run.status):
                log.info(
                    "orchestrator.noop terminal_status=%s run_id=%s",
                    run.status.value,
                    run.id,
                )
                return run

            run = await repos.agent_runs.mark_running(run.id)
            await repos.audit.append(
                case_id=case_id,
                actor_type=ActorType.AGENT,
                actor_id=agent_name.value,
                event_type=AuditEventType.AGENT_STARTED,
                event_payload={
                    "run_id": str(run.id),
                    "attempt": run.attempt,
                    "resumed": not created,
                    "input": mask_dict(input_payload),
                },
                agent_run_id=run.id,
            )

        # ---------- Phase 2: execute the agent (no DB transaction held) ------
        # We deliberately drop the transaction across the LLM call so we
        # don't hold a connection (and an open txn) for the duration of an
        # external API round-trip.  Evidence / party writes happen inside
        # `agent.run()` against a fresh transactional bundle (see Phase 3
        # below — the agent gets a *transactional* repos handle for that).
        started = time.monotonic()
        result_or_err = await self._execute_with_retry(
            agent=agent, case_id=case_id, run=run, extra_input=extra_input
        )
        duration_ms = int((time.monotonic() - started) * 1000)

        # ---------- Phase 3: persist outcome + audit + gates -----------------
        if isinstance(result_or_err, BaseException):
            err = result_or_err
            async with self._db.transaction() as repos:
                await repos.agent_runs.mark_failed(
                    run_id=run.id,
                    error=f"{err.__class__.__name__}: {err}",
                    duration_ms=duration_ms,
                )
                await repos.audit.append(
                    case_id=case_id,
                    actor_type=ActorType.AGENT,
                    actor_id=agent_name.value,
                    event_type=AuditEventType.AGENT_FAILED,
                    event_payload={
                        "run_id": str(run.id),
                        "error_class": err.__class__.__name__,
                        "duration_ms": duration_ms,
                    },
                    agent_run_id=run.id,
                )
            # Bubble up so the API layer can return 5xx / 429 etc.
            raise err

        result: AgentResult = result_or_err
        token_audit = (
            result.tokens.model_dump(mode="json") if result.tokens else None
        )

        try:
            async with self._db.transaction() as repos:
                updated = await repos.agent_runs.mark_completed(
                    run_id=run.id,
                    output_payload=result.output_payload,
                    reasoning=result.reasoning,
                    reasoning_summary=result.reasoning_summary,
                    tokens=result.tokens,
                    duration_ms=duration_ms,
                    requires_review=result.requires_review,
                )

                # CoT — record the reasoning as a separate audit event so
                # downstream analytics can index it independently.
                await repos.audit.append(
                    case_id=case_id,
                    actor_type=ActorType.AGENT,
                    actor_id=agent_name.value,
                    event_type=AuditEventType.AGENT_REASONING,
                    event_payload={
                        "run_id": str(updated.id),
                        "summary": result.reasoning_summary,
                        "tokens": token_audit,
                    },
                    reasoning_text=result.reasoning,
                    agent_run_id=updated.id,
                )
                await repos.audit.append(
                    case_id=case_id,
                    actor_type=ActorType.AGENT,
                    actor_id=agent_name.value,
                    event_type=AuditEventType.AGENT_COMPLETED,
                    event_payload={
                        "run_id": str(updated.id),
                        "duration_ms": duration_ms,
                        "requires_review": result.requires_review,
                        "evidence_ids": [str(e) for e in result.new_evidence_ids],
                        "party_ids": [str(p) for p in result.new_party_ids],
                    },
                    agent_run_id=updated.id,
                )

                # Open the gates this agent declared.
                for gate in result.next_gates:
                    opened = await repos.gates.open(
                        case_id=case_id,
                        gate_name=gate.name,
                        blocks_agent=gate.blocks_agent,
                        notes=gate.notes,
                    )
                    await repos.audit.append(
                        case_id=case_id,
                        actor_type=ActorType.SYSTEM,
                        actor_id="orchestrator",
                        event_type=AuditEventType.GATE_OPENED,
                        event_payload={
                            "gate_id": str(opened.id),
                            "gate_name": opened.gate_name,
                            "blocks_agent": opened.blocks_agent.value,
                        },
                        agent_run_id=updated.id,
                    )

                # Auto-advance only if the agent didn't ask for HITL.
                if not result.requires_review:
                    await self._advance_stage(
                        repos,
                        case_id=case_id,
                        agent_name=agent_name,
                        actor_id="orchestrator",
                    )

                return updated
        except Exception as persist_err:
            # Phase 1 already committed RUNNING. If anything here fails, that txn
            # rolls back and the row stays RUNNING unless we mark_failed in a
            # fresh transaction (same pattern as API restart for stale RUNNING).
            log.exception(
                "orchestrator.persist_failed case_id=%s run_id=%s agent=%s",
                case_id,
                run.id,
                agent_name.value,
            )
            detail = str(persist_err)
            if len(detail) > 1800:
                detail = detail[:1800] + "…"
            async with self._db.transaction() as repos:
                await repos.agent_runs.mark_failed(
                    run_id=run.id,
                    error=f"PersistFailed: {persist_err.__class__.__name__}: {detail}",
                    duration_ms=duration_ms,
                )
                await repos.audit.append(
                    case_id=case_id,
                    actor_type=ActorType.AGENT,
                    actor_id=agent_name.value,
                    event_type=AuditEventType.AGENT_FAILED,
                    event_payload={
                        "run_id": str(run.id),
                        "phase": "persist_after_successful_agent_run",
                        "error_class": persist_err.__class__.__name__,
                        "detail": detail,
                        "duration_ms": duration_ms,
                    },
                    agent_run_id=run.id,
                )
            raise persist_err

    async def _execute_with_retry(
        self,
        *,
        agent: BaseAgent,
        case_id: UUID,
        run: AgentRun,
        extra_input: dict[str, Any],
    ) -> AgentResult | BaseException:
        async def _attempt() -> AgentResult:
            # Each attempt gets its own transactional bundle so any evidence
            # the agent records is committed alongside its output even if a
            # later step in the orchestrator fails.
            async with self._db.transaction() as inner_repos:
                fresh_state = await load_investigation_state(inner_repos, case_id)
                ctx = AgentContext(
                    state=fresh_state,
                    repos=inner_repos,
                    run=run,
                    extra_input=extra_input,
                )
                return await agent.run(ctx)

        try:
            return await call_with_retry(
                _attempt,
                max_attempts=self._max_attempts,
                base_delay_seconds=1.0,
                max_delay_seconds=20.0,
            )
        except RetryExhausted as exhausted:
            return exhausted.last_error
        except Exception as err:  # noqa: BLE001 — re-raised by caller
            return err

    # =========================================================================
    # HITL: approval / rejection / overrides
    # =========================================================================
    async def approve_run(
        self, *, run_id: UUID, analyst_id: str
    ) -> AgentRun:
        async with self._db.transaction() as repos:
            run = await repos.agent_runs.approve(run_id=run_id, analyst_id=analyst_id)
            await repos.audit.append(
                case_id=run.case_id,
                actor_type=ActorType.ANALYST,
                actor_id=analyst_id,
                event_type=AuditEventType.GATE_APPROVED,
                event_payload={
                    "run_id": str(run.id),
                    "agent": run.agent.value,
                    "human_modified": run.human_modified,
                },
                agent_run_id=run.id,
            )
            await self._advance_stage(
                repos, case_id=run.case_id, agent_name=run.agent, actor_id=analyst_id
            )
            return run

    async def reject_run(
        self, *, run_id: UUID, analyst_id: str, reason: str
    ) -> AgentRun:
        async with self._db.transaction() as repos:
            run = await repos.agent_runs.reject(
                run_id=run_id, analyst_id=analyst_id, reason=reason
            )
            await repos.audit.append(
                case_id=run.case_id,
                actor_type=ActorType.ANALYST,
                actor_id=analyst_id,
                event_type=AuditEventType.GATE_REJECTED,
                event_payload={
                    "run_id": str(run.id),
                    "agent": run.agent.value,
                    "reason": reason,
                },
                agent_run_id=run.id,
            )
            return run

    async def apply_override(
        self,
        *,
        run_id: UUID,
        analyst_id: str,
        new_output: dict[str, Any],
        diff_ops: list[dict[str, Any]],
    ) -> AgentRun:
        async with self._db.transaction() as repos:
            run = await repos.agent_runs.apply_human_override(
                run_id=run_id,
                analyst_id=analyst_id,
                new_output=new_output,
                diff_ops=diff_ops,
            )
            await repos.audit.append(
                case_id=run.case_id,
                actor_type=ActorType.ANALYST,
                actor_id=analyst_id,
                event_type=AuditEventType.HUMAN_OVERRIDE,
                event_payload={
                    "run_id": str(run.id),
                    "agent": run.agent.value,
                    "ops_count": len(diff_ops),
                },
                agent_run_id=run.id,
            )
            return run

    async def resolve_gate(
        self,
        *,
        gate_id: UUID,
        status: GateStatus,
        analyst_id: str,
        notes: str | None = None,
    ) -> HumanGate:
        async with self._db.transaction() as repos:
            gate = await repos.gates.resolve(
                gate_id=gate_id,
                status=status,
                analyst_id=analyst_id,
                notes=notes,
            )
            await repos.audit.append(
                case_id=gate.case_id,
                actor_type=ActorType.ANALYST,
                actor_id=analyst_id,
                event_type=(
                    AuditEventType.GATE_APPROVED
                    if status == GateStatus.APPROVED
                    else AuditEventType.GATE_REJECTED
                ),
                event_payload={
                    "gate_id": str(gate.id),
                    "gate_name": gate.gate_name,
                    "blocks_agent": gate.blocks_agent.value,
                },
            )
            return gate

    async def submit_narrative(
        self, *, narrative_id: UUID, analyst_id: str
    ) -> Narrative:
        async with self._db.transaction() as repos:
            narrative = await repos.narratives.submit(
                narrative_id=narrative_id, analyst_id=analyst_id
            )
            # Lock the case (trigger enforces immutability after this).
            await repos.cases.lock(case_id=narrative.case_id, locked_by=analyst_id)

            await repos.audit.append(
                case_id=narrative.case_id,
                actor_type=ActorType.ANALYST,
                actor_id=analyst_id,
                event_type=AuditEventType.NARRATIVE_SUBMITTED,
                event_payload={
                    "narrative_id": str(narrative.id),
                    "version": narrative.version,
                    "classification": narrative.classification.value,
                },
            )
            await repos.audit.append(
                case_id=narrative.case_id,
                actor_type=ActorType.SYSTEM,
                actor_id="orchestrator",
                event_type=AuditEventType.RECORD_LOCKED,
                event_payload={"target": "case", "case_id": str(narrative.case_id)},
            )
            return narrative

    # =========================================================================
    # Read-only helper used by API routes
    # =========================================================================
    async def get_state(self, case_id: UUID) -> InvestigationState:
        async with self._db.connection() as repos:
            return await load_investigation_state(repos, case_id)

    # =========================================================================
    # Internal: stage advancement
    # =========================================================================
    async def _advance_stage(
        self,
        repos,
        *,
        case_id: UUID,
        agent_name: AgentName,
        actor_id: str,
    ) -> None:
        case = await repos.cases.get(case_id)
        if case is None:
            return  # nothing to do
        if case.locked:
            return

        # Don't advance past the agent's own stage.  E.g. if an analyst
        # approves the Initial Assessment, the case should move to the
        # Transaction Enrichment stage — but only if it isn't already there
        # or further along.
        own_stage = STAGE_FOR_AGENT[agent_name]
        if stage_lt(case.current_stage, own_stage):
            # Catch up to the agent's own stage first.
            await repos.cases.advance_stage(case_id, own_stage, actor_id)

        next_stage = NEXT_STAGE[own_stage]
        if next_stage == case.current_stage:
            return

        # Special terminal handling.
        if next_stage == CaseStage.COMPLETED:
            new_status = CaseStatus.AWAITING_REVIEW  # awaiting narrative submit
        else:
            new_status = CaseStatus.IN_PROGRESS

        await repos.cases.advance_stage(case_id, next_stage, actor_id)
        await repos.cases.update_status(case_id, new_status, actor_id)
        await repos.audit.append(
            case_id=case_id,
            actor_type=ActorType.SYSTEM,
            actor_id="orchestrator",
            event_type=AuditEventType.CASE_STAGE_ADVANCED,
            event_payload={
                "from_agent": agent_name.value,
                "to_stage": next_stage.value,
                "next_agent": (
                    NEXT_AGENT_FOR_STAGE[next_stage].value
                    if NEXT_AGENT_FOR_STAGE[next_stage]
                    else None
                ),
            },
        )

    # ------------------------------------------------------------------ utils
    def _require_agent(self, name: AgentName) -> BaseAgent:
        agent = self._agents.get(name)
        if agent is None:
            raise LookupError(f"no agent registered for {name.value}")
        return agent
