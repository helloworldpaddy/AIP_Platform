"""Inbound request bodies that don't already exist as state models.

Outbound responses reuse the Pydantic models from `aml.models.state`
directly — FastAPI handles their serialization.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..models.enums import CasePriority, GateStatus


class TriggerAgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    extra_input: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Additional inputs the agent should consider.  Becomes part of "
            "the idempotency key — change it to force a fresh run."
        ),
    )


class RejectRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(..., min_length=1, max_length=2000)


class OverrideRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new_output: dict[str, Any]
    diff_ops: list[dict[str, Any]] = Field(
        default_factory=list,
        description="RFC-6902 JSON-Patch describing the analyst's edits.",
    )


class ResolveGateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: GateStatus
    notes: str | None = None


class UpdatePriorityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    priority: CasePriority


class AssignAnalystRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analyst_id: str | None = None  # null clears the assignment


class UpdateNarrativeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rationale: str | None = None
    markdown_body: str | None = None
    citations: list[dict[str, Any]] | None = None


class AuditChainStatus(BaseModel):
    ok: bool
    first_bad_id: int | None = None


class HealthResponse(BaseModel):
    status: str = "ok"
    db: str
