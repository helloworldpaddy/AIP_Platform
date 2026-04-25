"""Seed a demo AML case (and a few policy chunks) for local exploration.

Idempotent: re-running with the same `--case-number` is a no-op for the
case row, and policy ingestion is itself content-hashed so duplicates are
absorbed.

Usage:
    python scripts/aml_seed.py
    python scripts/aml_seed.py --case-number AML-DEMO-2026-001 --skip-policies
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from agents.rag_agent.db.postgres_client import get_postgres_client  # noqa: E402
from agents.rag_agent.services.ingestion_service import (  # noqa: E402
    get_ingestion_service,
)
from agents.rag_agent.utils.logging_config import configure_logging, get_logger  # noqa: E402
from backend.aml.db.client import get_aml_db_client  # noqa: E402
from backend.aml.models.enums import (  # noqa: E402
    ActorType,
    AuditEventType,
    CasePriority,
    EvidenceType,
)
from backend.aml.models.state import CaseCreate  # noqa: E402

DEFAULT_CASE_NUMBER = "AML-DEMO-2026-001"
SAMPLE_POLICY_DIR = _REPO_ROOT / "data" / "samples"


async def _seed_policies(log) -> None:
    if not SAMPLE_POLICY_DIR.exists():
        log.warning("seed.policies.skip reason=no_sample_dir path=%s", SAMPLE_POLICY_DIR)
        return
    ingestion = get_ingestion_service()
    results = await ingestion.ingest_path(str(SAMPLE_POLICY_DIR), tags=["seed", "policy"])
    chunks = sum(r.chunks_written for r in results)
    log.info("seed.policies.done files=%d chunks=%d", len(results), chunks)


async def _seed_case(case_number: str, log) -> str:
    db = get_aml_db_client()
    await db.connect()
    async with db.transaction() as repos:
        existing = await repos.cases.get_by_number(case_number)
        if existing is not None:
            log.info(
                "seed.case.exists case_number=%s id=%s", case_number, existing.id
            )
            return str(existing.id)

        case = await repos.cases.create(
            CaseCreate(
                case_number=case_number,
                alert_type="TRANSACTION_MONITORING",
                alert_payload={
                    "rule_id": "TM-001",
                    "amount": 250_000,
                    "currency": "USD",
                    "counterparty_country": "PA",
                },
                subject_party_id="P-DEMO-SUBJECT",
                subject_party_name="Demo Subject Ltd.",
                priority=CasePriority.HIGH,
                assigned_analyst_id="analyst.demo",
                created_by="seed",
            )
        )
        await repos.audit.append(
            case_id=case.id,
            actor_type=ActorType.SYSTEM,
            actor_id="seed",
            event_type=AuditEventType.CASE_CREATED,
            event_payload={
                "case_number": case.case_number,
                "alert_type": case.alert_type,
                "priority": case.priority.value,
            },
        )

        # A single seed evidence row makes the UI render something on first
        # load before any agent has actually run.
        await repos.evidence.record(
            case_id=case.id,
            agent_run_id=None,
            evidence_type=EvidenceType.INTERNAL_NOTE,
            source_system="seed",
            source_uri=None,
            title="Initial alert metadata",
            content=(
                "Synthetic transaction-monitoring alert seeded for local "
                "exploration of the AML investigation workflow."
            ),
            structured_data={"seeded": True},
            confidence_score=1.0,
            contains_pii=False,
            created_by="seed",
        )

    log.info("seed.case.created case_number=%s id=%s", case.case_number, case.id)
    return str(case.id)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-number", default=DEFAULT_CASE_NUMBER)
    parser.add_argument(
        "--skip-policies",
        action="store_true",
        help="Don't ingest data/samples into the RAG store.",
    )
    args = parser.parse_args()

    configure_logging()
    log = get_logger("aml_seed")

    case_id: str | None = None
    rag_db = get_postgres_client()
    aml_db = get_aml_db_client()
    try:
        if not args.skip_policies:
            await _seed_policies(log)
        case_id = await _seed_case(args.case_number, log)
    finally:
        await rag_db.close()
        await aml_db.close()

    print(f"Seeded case_id={case_id} (case_number={args.case_number})")


if __name__ == "__main__":
    asyncio.run(main())
