"""Repository classes — one per aggregate.

Each repository is constructed with a single `asyncpg.Connection` so that
several repositories can share a transaction when bundled in
`AmlRepositories` (see `db.client`).
"""

from .agent_runs import AgentRunsRepository
from .audit import AuditRepository
from .case_monitoring import CaseMonitoringRepository
from .cases import CasesRepository
from .evidence import EvidenceRepository
from .gates import HumanGatesRepository
from .narratives import NarrativesRepository
from .parties import CasePartiesRepository

__all__ = [
    "AgentRunsRepository",
    "AuditRepository",
    "CaseMonitoringRepository",
    "CasesRepository",
    "EvidenceRepository",
    "HumanGatesRepository",
    "NarrativesRepository",
    "CasePartiesRepository",
]
