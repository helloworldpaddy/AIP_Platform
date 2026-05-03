"""Seed a demo AML case (and a few policy chunks) for local exploration.

Idempotent: re-running with the same `--case-number` is a no-op for the
case row, and policy ingestion is itself content-hashed so duplicates are
absorbed.

Seeded retail cases include rows in `aml.case_scenarios`, `aml.case_transactions`,
and links in `aml.case_transaction_scenario_links` when the additive schema has
been applied (`backend/aml/db/schema_case_scenarios_transactions.sql`).
When `NEO4J_URI` / `NEO4J_AUTH` are set (same as the API), ledger rows are also
upserted into Neo4j (`Party`, `:TRANSFERRED_TO`, `:Transaction`) for hop traversal.

Usage:
    python scripts/aml_seed.py
    python scripts/aml_seed.py --case-number AML-DEMO-2026-001 --skip-policies
    python scripts/aml_seed.py --preset mrp-goods
    python scripts/aml_seed.py --preset retail --skip-policies
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from backend.aml.db.client import AmlRepositories, get_aml_db_client  # noqa: E402
from backend.aml.models.enums import (  # noqa: E402
    ActorType,
    AuditEventType,
    CasePriority,
    EvidenceType,
    LineOfBusiness,
)
from backend.aml.models.state import CaseCreate  # noqa: E402

SAMPLE_POLICY_DIR = _REPO_ROOT / "data" / "samples"


@dataclass(frozen=True)
class _ScenarioSeed:
    scenario_code: str
    title: str
    trigger_summary: str | None = None
    trigger_facts: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _TxnSeed:
    external_transaction_id: str
    booked_offset_hours: int
    amount: str
    currency: str
    direction: str
    payment_channel: str
    product_category: str
    counterparty_name: str | None = None
    counterparty_external_id: str | None = None
    counterparty_country: str | None = None
    channel_details: dict[str, Any] = field(default_factory=dict)
    mcc: str | None = None
    merchant_name: str | None = None
    narrative: str | None = None


@dataclass(frozen=True)
class _SeedPreset:
    case_number: str
    subject_party_id: str
    subject_party_name: str
    alert_type: str
    alert_payload: dict[str, Any]
    priority: CasePriority
    line_of_business: LineOfBusiness
    evidence_title: str
    evidence_content: str
    scenario: _ScenarioSeed | None = None
    transactions: tuple[_TxnSeed, ...] = ()


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
        line_of_business=LineOfBusiness.RETAIL_BANKING,
        evidence_title="Initial alert metadata",
        evidence_content=(
            "Synthetic transaction-monitoring alert seeded for local "
            "exploration of the AML investigation workflow."
        ),
        scenario=_ScenarioSeed(
            scenario_code="TM-RB-VEL-001",
            title="Velocity — outbound wires (retail)",
            trigger_summary="Multiple high-value outbound wires within 30 days",
            trigger_facts={"window_days": 30, "velocity": "HIGH"},
        ),
        transactions=(
            _TxnSeed(
                external_transaction_id="CORE-TXN-DEMO-001",
                booked_offset_hours=-72,
                amount="125000.0000",
                currency="USD",
                direction="DEBIT",
                payment_channel="WIRE",
                product_category="RETAIL_CHECKING",
                counterparty_name="Correspondent Bank (PA)",
                counterparty_country="PA",
                channel_details={"swift_hint": "CORRPA", "purpose_code": "TRADE"},
                narrative="Outbound wire #1 referenced in velocity scenario.",
            ),
            _TxnSeed(
                external_transaction_id="CORE-TXN-DEMO-002",
                booked_offset_hours=-168,
                amount="85000.0000",
                currency="USD",
                direction="DEBIT",
                payment_channel="WIRE",
                product_category="RETAIL_CHECKING",
                counterparty_name="Trade Services LLC",
                counterparty_country="PA",
                channel_details={"purpose_code": "GOODS"},
                narrative="Outbound wire #2 within monitoring window.",
            ),
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
        line_of_business=LineOfBusiness.RETAIL_BANKING,
        evidence_title="Initial alert — import / supplier payment pattern",
        evidence_content=(
            "Transaction monitoring alert on MRP Goods (focus party): "
            "elevated aggregate outbound wires to goods-related counterparties "
            "in multiple jurisdictions within 45 days."
        ),
        scenario=_ScenarioSeed(
            scenario_code="TM-IM-014",
            title="Import / supplier payment aggregation",
            trigger_summary="Cross-border wires to goods-import counterparties",
            trigger_facts={"window_days": 45, "aggregate_usd": 890000},
        ),
        transactions=(
            _TxnSeed(
                external_transaction_id="CORE-TXN-MRP-001",
                booked_offset_hours=-48,
                amount="425000.0000",
                currency="USD",
                direction="DEBIT",
                payment_channel="WIRE",
                product_category="RETAIL_CHECKING",
                counterparty_name="Supplier Alpha IN",
                counterparty_country="IN",
                channel_details={"purpose": "goods_import"},
                narrative="Wire to supplier — batch 1.",
            ),
            _TxnSeed(
                external_transaction_id="CORE-TXN-MRP-002",
                booked_offset_hours=-120,
                amount="310000.0000",
                currency="USD",
                direction="DEBIT",
                payment_channel="ACH",
                product_category="RETAIL_CHECKING",
                counterparty_name="Freight & Logistics Co",
                counterparty_country="US",
                channel_details={"ach_sec_code": "CCD"},
                narrative="ACH settlement related to import corridor.",
            ),
        ),
    ),
    "retail": _SeedPreset(
        case_number="AML-RETAIL-2026-001",
        subject_party_id="party.retail.demo.001",
        subject_party_name="Retail Demo Customer",
        alert_type="TRANSACTION_MONITORING",
        alert_payload={
            "rule_id": "TM-RB-001",
            "channel": "retail",
            "scenario": "cross_border_wire",
        },
        priority=CasePriority.MEDIUM,
        line_of_business=LineOfBusiness.RETAIL_BANKING,
        evidence_title="Retail TM alert — international wire",
        evidence_content=(
            "Synthetic retail banking alert: unusual cross-border wire pattern "
            "for a consumer checking relationship."
        ),
        scenario=_ScenarioSeed(
            scenario_code="TM-RB-XBR-001",
            title="Cross-border wire — retail checking",
            trigger_summary="International wire exceeding customer velocity profile",
            trigger_facts={"origin_channel": "DIGITAL_BANKING"},
        ),
        transactions=(
            _TxnSeed(
                external_transaction_id="RETAIL-TXN-001",
                booked_offset_hours=-36,
                amount="18500.7500",
                currency="USD",
                direction="DEBIT",
                payment_channel="WIRE",
                product_category="RETAIL_CHECKING",
                counterparty_name="Foreign Beneficiary Ltd",
                counterparty_country="GB",
                channel_details={"beneficiary_bank": "SWIFTGB2L", "purpose": "family_support"},
                narrative="Outbound international wire initiated via digital banking.",
            ),
            _TxnSeed(
                external_transaction_id="RETAIL-TXN-002",
                booked_offset_hours=-96,
                amount="220.0000",
                currency="USD",
                direction="DEBIT",
                payment_channel="CARD_POS",
                product_category="RETAIL_DEBIT_CARD",
                counterparty_name="Grocery Mart",
                counterparty_country="US",
                mcc="5411",
                merchant_name="Grocery Mart",
                channel_details={"network": "VISA", "entry_mode": "CHIP"},
                narrative="POS debit — baseline domestic spend.",
            ),
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


async def _seed_case_monitoring(
    repos: AmlRepositories,
    case_id: UUID,
    preset: _SeedPreset,
    log: logging.Logger,
) -> None:
    if preset.scenario is None and not preset.transactions:
        return
    if preset.transactions and preset.scenario is None:
        raise ValueError("seed preset defines transactions but no scenario")
    if preset.scenario is None:
        return

    scen = preset.scenario
    scenario_id = await repos.case_monitoring.insert_scenario(
        case_id,
        scen.scenario_code,
        scen.title,
        trigger_summary=scen.trigger_summary,
        trigger_facts=scen.trigger_facts,
        is_primary=True,
    )
    now = datetime.now(timezone.utc)
    for txn in preset.transactions:
        booked_at = now + timedelta(hours=txn.booked_offset_hours)
        tid = await repos.case_monitoring.insert_transaction(
            case_id,
            txn.external_transaction_id,
            booked_at,
            Decimal(txn.amount),
            txn.currency,
            txn.direction,
            txn.payment_channel,
            txn.product_category,
            counterparty_name=txn.counterparty_name,
            counterparty_external_id=txn.counterparty_external_id,
            counterparty_country=txn.counterparty_country,
            channel_details=txn.channel_details,
            mcc=txn.mcc,
            merchant_name=txn.merchant_name,
            narrative=txn.narrative,
            raw_payload={"seeded": True},
        )
        await repos.case_monitoring.link_transaction_scenario(tid, scenario_id)

    log.info(
        "seed.case_monitoring.done case_id=%s scenario=%s txns=%d",
        case_id,
        scen.scenario_code,
        len(preset.transactions),
    )


async def _maybe_sync_neo4j(
    case_id: UUID,
    subject_party_id: str,
    subject_party_name: str,
    log: logging.Logger,
) -> None:
    """Best-effort: mirror `case_transactions` into Neo4j when settings allow."""
    try:
        from agents.rag_agent.config.settings import get_settings
        from neo4j import AsyncGraphDatabase

        from backend.aml.integrations.case_transactions_neo4j_sync import (
            sync_case_transactions_to_neo4j,
        )

        cfg = get_settings().neo4j
        if not cfg.configured:
            return
        aml_db = get_aml_db_client()
        await aml_db.connect()
        async with aml_db.connection() as repos:
            txns = await repos.case_monitoring.list_transactions_for_case(case_id)
        if not txns:
            return
        driver = AsyncGraphDatabase.driver(
            cfg.uri,
            auth=(cfg.user, cfg.password),
        )
        try:
            n = await sync_case_transactions_to_neo4j(
                driver,
                database=cfg.database,
                subject_party_id=subject_party_id,
                subject_party_name=subject_party_name,
                case_id=case_id,
                transactions=txns,
            )
            log.info("seed.neo4j.sync case_id=%s synced=%s", case_id, n)
        finally:
            await driver.close()
    except Exception as err:
        log.warning("seed.neo4j.sync.failed err=%s", err)


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
                line_of_business=preset.line_of_business,
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
                "line_of_business": case.line_of_business.value,
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

        await _seed_case_monitoring(repos, case.id, preset, log)

    log.info("seed.case.created case_number=%s id=%s", case.case_number, case.id)
    await _maybe_sync_neo4j(
        case.id,
        case.subject_party_id,
        case.subject_party_name,
        log,
    )
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
            line_of_business=preset.line_of_business,
            evidence_title=preset.evidence_title,
            evidence_content=preset.evidence_content,
            scenario=preset.scenario,
            transactions=preset.transactions,
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
