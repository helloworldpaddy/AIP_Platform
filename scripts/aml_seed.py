"""Seed a demo AML case (and a few policy chunks) for local exploration.

Idempotent: re-running with the same `--case-number` is a no-op for the
case row, and policy ingestion is itself content-hashed so duplicates are
absorbed.

Usage:
    python scripts/aml_seed.py
    python scripts/aml_seed.py --case-number AML-DEMO-2026-001 --skip-policies
    python scripts/aml_seed.py --preset mrp-goods
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from backend.aml.db.client import get_aml_db_client  # noqa: E402
from backend.aml.models.enums import (  # noqa: E402
    ActorType,
    AuditEventType,
    CasePriority,
    EvidenceType,
)
from backend.aml.models.state import CaseCreate  # noqa: E402

SAMPLE_POLICY_DIR = _REPO_ROOT / "data" / "samples"


@dataclass(frozen=True)
class _SeedPreset:
    case_number: str
    subject_party_id: str
    subject_party_name: str
    alert_type: str
    alert_payload: dict[str, Any]
    priority: CasePriority
    evidence_title: str
    evidence_content: str


_PRESETS: dict[str, _SeedPreset] = {
    "demo": _SeedPreset(
        case_number="AML-DEMO-2026-001",
        subject_party_id="P-DEMO-SUBJECT",
        subject_party_name="Demo Subject Ltd.",
        alert_type="TRANSACTION_MONITORING",
        alert_payload={
            "rule_id": "TM-001",
            "amount": 250_000,
            "currency": "USD",
            "counterparty_country": "PA",
        },
        priority=CasePriority.HIGH,
        evidence_title="Initial alert metadata",
        evidence_content=(
            "Synthetic transaction-monitoring alert seeded for local "
            "exploration of the AML investigation workflow."
        ),
    ),
    "mrp-goods": _SeedPreset(
        case_number="AML-MRP-GOODS-2026-001",
        subject_party_id="P-MRP-GOODS",
        subject_party_name="MRP Goods",
        alert_type="TRANSACTION_MONITORING",
        alert_payload={
            "rule_id": "TM-IM-014",
            "amount": 890_000,
            "currency": "USD",
            "counterparty_country": "IN",
            "narrative": (
                "Spike in cross-border supplier payments; goods-import "
                "MCC cluster; beneficiary names vary while originator stable."
            ),
        },
        priority=CasePriority.HIGH,
        evidence_title="Initial alert — import / supplier payment pattern",
        evidence_content=(
            "Transaction monitoring alert on MRP Goods (focus party): "
            "elevated aggregate outbound wires to goods-related counterparties "
            "in multiple jurisdictions within 45 days."
        ),
    ),
}


async def _seed_policies(log: logging.Logger) -> None:
    """Loads RAG / embedding stack; keep imports inside this path."""
    from agents.rag_agent.services.ingestion_service import (  # noqa: E402
        get_ingestion_service,
    )
    from agents.rag_agent.utils.logging_config import (  # noqa: E402
        configure_logging,
    )

    configure_logging()
    if not SAMPLE_POLICY_DIR.exists():
        log.warning("seed.policies.skip reason=no_sample_dir path=%s", SAMPLE_POLICY_DIR)
        return
    ingestion = get_ingestion_service()
    results = await ingestion.ingest_path(str(SAMPLE_POLICY_DIR), tags=["seed", "policy"])
    chunks = sum(r.chunks_written for r in results)
    log.info("seed.policies.done files=%d chunks=%d", len(results), chunks)


async def _seed_case(preset: _SeedPreset, log: logging.Logger) -> str:
    db = get_aml_db_client()
    await db.connect()
    async with db.transaction() as repos:
        existing = await repos.cases.get_by_number(preset.case_number)
        if existing is not None:
            log.info(
                "seed.case.exists case_number=%s id=%s",
                preset.case_number,
                existing.id,
            )
            return str(existing.id)

        case = await repos.cases.create(
            CaseCreate(
                case_number=preset.case_number,
                alert_type=preset.alert_type,
                alert_payload=preset.alert_payload,
                subject_party_id=preset.subject_party_id,
                subject_party_name=preset.subject_party_name,
                priority=preset.priority,
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
            title=preset.evidence_title,
            content=preset.evidence_content,
            structured_data={"seeded": True},
            confidence_score=1.0,
            contains_pii=False,
            created_by="seed",
        )

    log.info("seed.case.created case_number=%s id=%s", case.case_number, case.id)
    return str(case.id)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preset",
        choices=sorted(_PRESETS.keys()),
        default="demo",
        help="Which seed scenario to load (default: demo).",
    )
    parser.add_argument(
        "--case-number",
        default=None,
        help="Override case number from the preset (optional).",
    )
    parser.add_argument(
        "--skip-policies",
        action="store_true",
        help="Don't ingest data/samples into the RAG store.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )
    log = logging.getLogger("aml_seed")

    preset = _PRESETS[args.preset]
    if args.case_number is not None:
        preset = _SeedPreset(
            case_number=args.case_number,
            subject_party_id=preset.subject_party_id,
            subject_party_name=preset.subject_party_name,
            alert_type=preset.alert_type,
            alert_payload=preset.alert_payload,
            priority=preset.priority,
            evidence_title=preset.evidence_title,
            evidence_content=preset.evidence_content,
        )

    case_id: str | None = None
    aml_db = get_aml_db_client()
    try:
        if not args.skip_policies:
            from agents.rag_agent.db.postgres_client import (  # noqa: E402
                get_postgres_client,
            )

            rag_db = get_postgres_client()
            try:
                await _seed_policies(log)
            finally:
                await rag_db.close()
        case_id = await _seed_case(preset, log)
    finally:
        await aml_db.close()

    print(f"Seeded case_id={case_id} (case_number={preset.case_number})")


if __name__ == "__main__":
    asyncio.run(main())
