"""Pydantic v2 models for the AML Investigation State.

These mirror the Postgres tables defined in `backend/aml/db/schema.sql`
and are the shared contract between:

    * the FastAPI HTTP layer (request / response bodies)
    * the orchestration layer that drives agent_runs
    * the Google ADK agent tools (input / output schemas)
    * the React frontend (via OpenAPI codegen)

`InvestigationState` is the aggregate root passed between agents.  Agents
should treat it as read-only with respect to the database — they emit new
events (AgentRun output + Evidence + AuditEvent rows) and the orchestrator
re-hydrates the state for the next stage.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import (
    ActorType,
    AgentName,
    AgentRunStatus,
    AuditEventType,
    CasePriority,
    CaseStage,
    CaseStatus,
    Classification,
    EvidenceType,
    GateStatus,
    LineOfBusiness,
    PartyType,
)

# ---------------------------------------------------------------------------
# Base configuration shared by all models
# ---------------------------------------------------------------------------


class _ORMBase(BaseModel):
    """Base for models that round-trip with the database.

    `from_attributes=True` allows hydration from asyncpg `Record` objects
    via `Model.model_validate(record)` (records expose attribute access).
    """

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=False,
        extra="forbid",
        ser_json_timedelta="iso8601",
    )


# ---------------------------------------------------------------------------
# Case
# ---------------------------------------------------------------------------


class Case(_ORMBase):
    id: UUID
    case_number: str = Field(..., examples=["AML-2026-000123"])
    alert_type: str = Field(..., examples=["TRANSACTION_MONITORING"])
    alert_payload: dict[str, Any] = Field(default_factory=dict)
    subject_party_id: str
    subject_party_name: str
    line_of_business: LineOfBusiness = LineOfBusiness.RETAIL_BANKING
    status: CaseStatus = CaseStatus.OPEN
    current_stage: CaseStage = CaseStage.INTAKE
    priority: CasePriority = CasePriority.MEDIUM
    assigned_analyst_id: str | None = None
    locked: bool = False
    locked_at: datetime | None = None
    locked_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str | None = None


class CaseCreate(BaseModel):
    """Inbound DTO for `POST /cases`."""

    model_config = ConfigDict(extra="forbid")

    case_number: str
    alert_type: str
    alert_payload: dict[str, Any]
    subject_party_id: str
    subject_party_name: str
    line_of_business: LineOfBusiness = LineOfBusiness.RETAIL_BANKING
    priority: CasePriority = CasePriority.MEDIUM
    assigned_analyst_id: str | None = None
    created_by: str


# ---------------------------------------------------------------------------
# Agent runs
# ---------------------------------------------------------------------------


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: int = 0
    completion: int = 0
    total: int = 0


class AgentRun(_ORMBase):
    id: UUID
    case_id: UUID
    agent: AgentName
    attempt: int = 1
    idempotency_key: str
    status: AgentRunStatus = AgentRunStatus.PENDING
    input_payload: dict[str, Any] = Field(default_factory=dict)
    output_payload: dict[str, Any] | None = None
    reasoning: str | None = None             # full Chain-of-Thought
    reasoning_summary: str | None = None     # short, UI-friendly
    error: str | None = None
    model_name: str | None = None
    tokens: TokenUsage | None = None
    duration_ms: int | None = None
    # Human-in-the-loop override
    human_modified: bool = False
    human_modified_at: datetime | None = None
    human_modified_by: str | None = None
    human_diff: list[dict[str, Any]] | None = None  # RFC-6902 JSON-Patch ops
    approved_at: datetime | None = None
    approved_by: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("attempt")
    @classmethod
    def _attempt_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("attempt must be >= 1")
        return v


# ---------------------------------------------------------------------------
# Evidence + Citations
# ---------------------------------------------------------------------------


class Evidence(_ORMBase):
    id: UUID
    case_id: UUID
    agent_run_id: UUID | None = None
    evidence_type: EvidenceType
    source_system: str
    source_uri: str | None = None
    title: str
    content: str
    structured_data: dict[str, Any] = Field(default_factory=dict)
    content_hash: str
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    contains_pii: bool = False
    retrieved_at: datetime
    created_by: str


class Citation(BaseModel):
    """Footnote-style citation embedded in a narrative.

    `footnote` is the integer that appears in the markdown (e.g. `[1]`);
    `evidence_id` resolves to a row in `evidence_ledger`.
    """

    model_config = ConfigDict(extra="forbid")
    footnote: int = Field(..., ge=1)
    evidence_id: UUID
    excerpt: str | None = None  # short snippet used in the rendered narrative


# ---------------------------------------------------------------------------
# Case parties (output of Transaction Enrichment, gated for human review)
# ---------------------------------------------------------------------------


class CaseParty(_ORMBase):
    id: UUID
    case_id: UUID
    party_external_id: str
    party_name: str
    party_type: PartyType = PartyType.OTHER
    relationship: str | None = None
    hop_distance: int = Field(..., ge=0)
    risk_indicators: dict[str, Any] = Field(default_factory=dict)
    source_evidence_ids: list[UUID] = Field(default_factory=list)
    verified: bool = False
    verified_at: datetime | None = None
    verified_by: str | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Human gates
# ---------------------------------------------------------------------------


class HumanGate(_ORMBase):
    id: UUID
    case_id: UUID
    gate_name: str
    blocks_agent: AgentName
    status: GateStatus = GateStatus.OPEN_REQUIRED
    opened_at: datetime
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    notes: str | None = None


# ---------------------------------------------------------------------------
# Narrative
# ---------------------------------------------------------------------------


class Narrative(_ORMBase):
    id: UUID
    case_id: UUID
    version: int = 1
    classification: Classification
    rationale: str
    markdown_body: str
    citations: list[Citation] = Field(default_factory=list)
    submitted: bool = False
    submitted_at: datetime | None = None
    submitted_by: str | None = None
    locked: bool = False
    human_modified: bool = False
    created_at: datetime
    created_by: str


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


class AuditEvent(_ORMBase):
    id: int
    case_id: UUID
    agent_run_id: UUID | None = None
    actor_type: ActorType
    actor_id: str
    event_type: AuditEventType
    event_payload: dict[str, Any] = Field(default_factory=dict)
    reasoning_text: str | None = None
    prev_hash: str | None = None
    data_hash: str
    created_at: datetime


class CaseTransaction(BaseModel):
    """Banking transaction row from `aml.case_transactions` (read model)."""

    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: UUID
    case_id: UUID
    external_transaction_id: str
    booked_at: datetime
    amount: Decimal
    currency: str
    direction: str
    payment_channel: str
    product_category: str
    counterparty_name: str | None = None
    counterparty_external_id: str | None = None
    counterparty_country: str | None = None
    narrative: str | None = None


# ---------------------------------------------------------------------------
# Aggregate: stage progress + InvestigationState
# ---------------------------------------------------------------------------


class StageProgress(BaseModel):
    """UI-facing roll-up: status of one stage (= one agent) on the dashboard."""

    model_config = ConfigDict(extra="forbid")

    stage: CaseStage
    agent: AgentName
    status: AgentRunStatus
    latest_run_id: UUID | None = None
    requires_review: bool = False
    blocking_gate: HumanGate | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class InvestigationState(BaseModel):
    """Aggregate root passed between agents and rendered by the frontend.

    The orchestrator hydrates this from Postgres at the start of each stage
    and persists deltas (new AgentRun, new Evidence, new AuditEvents) at the
    end.  Agents MUST NOT mutate this object in place — they should emit
    new entities for the orchestrator to commit.
    """

    model_config = ConfigDict(extra="forbid")

    case: Case
    agent_runs: list[AgentRun] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    parties: list[CaseParty] = Field(default_factory=list)
    gates: list[HumanGate] = Field(default_factory=list)
    narratives: list[Narrative] = Field(default_factory=list)
    progress: list[StageProgress] = Field(default_factory=list)
    case_transactions: list[CaseTransaction] = Field(default_factory=list)

    # Convenience read-only helpers --------------------------------------------

    def latest_run(self, agent: AgentName) -> AgentRun | None:
        """Most recent run for `agent` (highest attempt)."""
        runs = [r for r in self.agent_runs if r.agent == agent]
        if not runs:
            return None
        return max(runs, key=lambda r: r.attempt)

    def open_gates(self) -> list[HumanGate]:
        return [g for g in self.gates if g.status == GateStatus.OPEN_REQUIRED]

    def is_blocked(self, agent: AgentName) -> bool:
        """True if any open gate currently blocks `agent`."""
        return any(
            g.blocks_agent == agent and g.status == GateStatus.OPEN_REQUIRED
            for g in self.gates
        )

    def submitted_narrative(self) -> Narrative | None:
        for n in self.narratives:
            if n.submitted:
                return n
        return None
