"""Static workflow rules — single source of truth for stage progression."""

from __future__ import annotations

from ..models.enums import AgentName, AgentRunStatus, CaseStage

# Each agent owns exactly one stage.
STAGE_FOR_AGENT: dict[AgentName, CaseStage] = {
    AgentName.INITIAL_ASSESSMENT: CaseStage.INITIAL_ASSESSMENT,
    AgentName.TRANSACTION_ENRICHMENT: CaseStage.TRANSACTION_ENRICHMENT,
    AgentName.DUE_DILIGENCE: CaseStage.DUE_DILIGENCE,
    AgentName.CASE_ANALYSIS: CaseStage.CASE_ANALYSIS,
}

# Stage progression after a successful + approved run.
NEXT_STAGE: dict[CaseStage, CaseStage] = {
    CaseStage.INTAKE: CaseStage.INITIAL_ASSESSMENT,
    CaseStage.INITIAL_ASSESSMENT: CaseStage.TRANSACTION_ENRICHMENT,
    CaseStage.TRANSACTION_ENRICHMENT: CaseStage.DUE_DILIGENCE,
    CaseStage.DUE_DILIGENCE: CaseStage.CASE_ANALYSIS,
    CaseStage.CASE_ANALYSIS: CaseStage.COMPLETED,
    CaseStage.COMPLETED: CaseStage.COMPLETED,
}

# Reverse lookup: which agent should the orchestrator dispatch to advance from
# the given stage?
NEXT_AGENT_FOR_STAGE: dict[CaseStage, AgentName | None] = {
    CaseStage.INTAKE: AgentName.INITIAL_ASSESSMENT,
    CaseStage.INITIAL_ASSESSMENT: AgentName.TRANSACTION_ENRICHMENT,
    CaseStage.TRANSACTION_ENRICHMENT: AgentName.DUE_DILIGENCE,
    CaseStage.DUE_DILIGENCE: AgentName.CASE_ANALYSIS,
    CaseStage.CASE_ANALYSIS: None,
    CaseStage.COMPLETED: None,
}

# Stable ordinal for stages — used by the orchestrator to decide whether the
# case has already passed a stage (string comparison of enum values would be
# alphabetic, which is wrong for these labels).
STAGE_ORDER: dict[CaseStage, int] = {
    CaseStage.INTAKE: 0,
    CaseStage.INITIAL_ASSESSMENT: 1,
    CaseStage.TRANSACTION_ENRICHMENT: 2,
    CaseStage.DUE_DILIGENCE: 3,
    CaseStage.CASE_ANALYSIS: 4,
    CaseStage.COMPLETED: 5,
}


def stage_lt(a: CaseStage, b: CaseStage) -> bool:
    """True iff stage `a` precedes stage `b` in the workflow."""
    return STAGE_ORDER[a] < STAGE_ORDER[b]


# Terminal agent-run statuses — orchestrator never re-runs these without a
# fresh idempotency key.
_TERMINAL = {
    AgentRunStatus.APPROVED,
    AgentRunStatus.COMPLETED,
    AgentRunStatus.FAILED,
    AgentRunStatus.REJECTED,
}


def is_terminal_status(status: AgentRunStatus) -> bool:
    return status in _TERMINAL
