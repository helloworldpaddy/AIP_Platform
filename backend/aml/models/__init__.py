"""Pydantic models that mirror the AML investigation Postgres schema.

Public surface:
    enums  — string enums aligned with the SQL ENUM types
    state  — entity / aggregate models (Case, AgentRun, Evidence, …, InvestigationState)
"""

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
    PartyType,
)
from .state import (
    AgentRun,
    AuditEvent,
    Case,
    CaseParty,
    Citation,
    Evidence,
    HumanGate,
    InvestigationState,
    Narrative,
    StageProgress,
)

__all__ = [
    # enums
    "ActorType",
    "AgentName",
    "AgentRunStatus",
    "AuditEventType",
    "CasePriority",
    "CaseStage",
    "CaseStatus",
    "Classification",
    "EvidenceType",
    "GateStatus",
    "PartyType",
    # state
    "AgentRun",
    "AuditEvent",
    "Case",
    "CaseParty",
    "Citation",
    "Evidence",
    "HumanGate",
    "InvestigationState",
    "Narrative",
    "StageProgress",
]
