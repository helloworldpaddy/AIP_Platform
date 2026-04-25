"""Abstract agent contract used by the orchestrator.

Every concrete agent (Initial Assessment, Transaction Enrichment, Due
Diligence, Case Analysis) implements `BaseAgent.run(ctx)` and returns an
`AgentResult`.  The orchestrator handles:

    * status transitions (`mark_running` → `mark_completed`/`mark_failed`)
    * audit-trail writes (`AGENT_STARTED`, `AGENT_REASONING`, `AGENT_COMPLETED`)
    * gate creation / closing
    * stage advancement (when `requires_review = False`)

Agents themselves only worry about *what to think* and *what evidence to
write* — never about transactions, retries or audit plumbing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from ..db.client import AmlRepositories
from ..models.enums import AgentName
from ..models.state import AgentRun, InvestigationState, TokenUsage


@dataclass(frozen=True)
class GateSpec:
    """Declarative gate the agent wants the orchestrator to open after it
    finishes (e.g. Transaction Enrichment opens `PARTIES_VERIFIED`)."""

    name: str
    blocks_agent: AgentName
    notes: str | None = None


@dataclass
class AgentContext:
    """Everything an agent needs to do its job.

    `repos` is a *transactional* repository bundle — agents may write
    `evidence` and `parties` rows; the orchestrator commits them atomically
    with the `agent_runs` status update.

    Agents MUST NOT mutate `state` in place; emit new rows via `repos`.
    """

    state: InvestigationState
    repos: AmlRepositories
    run: AgentRun  # the in-flight agent_run row (for evidence.agent_run_id)
    extra_input: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    output_payload: dict[str, Any]
    reasoning: str                              # full Chain-of-Thought
    reasoning_summary: str | None = None        # short, UI-friendly
    tokens: TokenUsage | None = None
    requires_review: bool = True                # default: HITL on every stage
    new_evidence_ids: list[UUID] = field(default_factory=list)
    new_party_ids: list[UUID] = field(default_factory=list)
    next_gates: list[GateSpec] = field(default_factory=list)


class BaseAgent(ABC):
    name: AgentName
    model_name: str = "gemini-1.5-pro"

    @abstractmethod
    async def run(self, ctx: AgentContext) -> AgentResult:
        ...

    # Optional hook: derive the logical input payload that `idempotency_key`
    # is computed from.  Defaults to `ctx.extra_input` so re-triggering with
    # the same extra_input deterministically resumes.
    def idempotency_input(self, ctx_extra: dict[str, Any]) -> dict[str, Any]:
        return ctx_extra
