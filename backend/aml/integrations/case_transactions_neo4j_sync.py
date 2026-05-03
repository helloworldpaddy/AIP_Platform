"""Materialize Postgres `aml.case_transactions` into Neo4j for hop traversal + analytics.

Creates/updates:
  * :Party for the case subject and each counterparty
  * :TRANSFERRED_TO relationships keyed by `ledger_external_id` (one per ledger row)
    with `last_seen` set from `booked_at` so `Neo4jGraphProvider.hop_neighbors` windows apply
  * :Transaction nodes linked with INITIATED / WITH_COUNTERPARTY

Idempotent: safe to re-run after seed or data fixes.
"""

from __future__ import annotations

import logging
from datetime import timezone
from typing import Any
from uuid import UUID

from neo4j import AsyncDriver

from ..models.state import CaseTransaction

log = logging.getLogger(__name__)

# Party–Party edges carry last_seen for the existing hop query; Transaction nodes
# mirror the monitoring ledger for exploration and future Cypher.
UPSERT_CYPHER = """
UNWIND $batch AS row
MERGE (s:Party {party_external_id: row.subject_party_id})
  ON CREATE SET s.party_type = 'CUSTOMER'
  SET s.party_name = row.subject_party_name
MERGE (c:Party {party_external_id: row.cp_id})
  ON CREATE SET c.party_type = 'COUNTERPARTY'
  SET c.party_name = row.cp_name,
      c.country = coalesce(row.cp_country, c.country)
MERGE (s)-[rel:TRANSFERRED_TO {ledger_external_id: row.ext_id}]->(c)
  SET rel.last_seen = datetime(row.booked_at),
      rel.total_value = toFloat(row.amount),
      rel.currency = row.currency,
      rel.txn_count = 1,
      rel.source = 'postgres_case_transactions',
      rel.direction = row.direction,
      rel.payment_channel = row.payment_channel
MERGE (t:Transaction {transaction_external_id: row.ext_id})
  SET t.timestamp = datetime(row.booked_at),
      t.amount = toFloat(row.amount),
      t.currency = row.currency,
      t.direction = row.direction,
      t.payment_channel = row.payment_channel,
      t.case_id = row.case_id,
      t.subject_party_id = row.subject_party_id,
      t.product_category = row.product_category
MERGE (s)-[:INITIATED]->(t)
MERGE (t)-[:WITH_COUNTERPARTY]->(c)
"""


def _iso(dt: Any) -> str:
    if hasattr(dt, "tzinfo") and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).isoformat()
    return dt.isoformat()


def counterparty_external_id(tx: CaseTransaction, case_id: UUID) -> str:
    ext = (tx.counterparty_external_id or "").strip()
    if ext:
        return ext
    raw = (tx.counterparty_name or "CP_UNKNOWN").replace(" ", "_")[:40]
    return f"CP:{case_id.hex[:8]}:{raw}"


def build_batch(
    *,
    subject_party_id: str,
    subject_party_name: str,
    case_id: UUID,
    transactions: list[CaseTransaction],
) -> list[dict[str, Any]]:
    batch: list[dict[str, Any]] = []
    for tx in transactions:
        batch.append(
            {
                "subject_party_id": subject_party_id,
                "subject_party_name": subject_party_name,
                "case_id": str(case_id),
                "ext_id": tx.external_transaction_id,
                "booked_at": _iso(tx.booked_at),
                "amount": str(tx.amount),
                "currency": tx.currency,
                "direction": tx.direction,
                "payment_channel": tx.payment_channel,
                "product_category": tx.product_category,
                "cp_id": counterparty_external_id(tx, case_id),
                "cp_name": tx.counterparty_name or "Counterparty",
                "cp_country": tx.counterparty_country,
            }
        )
    return batch


async def sync_case_transactions_to_neo4j(
    driver: AsyncDriver,
    *,
    database: str,
    subject_party_id: str,
    subject_party_name: str,
    case_id: UUID,
    transactions: list[CaseTransaction],
) -> int:
    """Write ledger rows to Neo4j. Returns number of rows processed."""
    if not transactions:
        return 0
    batch = build_batch(
        subject_party_id=subject_party_id,
        subject_party_name=subject_party_name,
        case_id=case_id,
        transactions=transactions,
    )
    async with driver.session(database=database) as session:
        await session.run(UPSERT_CYPHER, batch=batch)
    log.info(
        "neo4j.case_transactions.synced case_id=%s rows=%s",
        case_id,
        len(batch),
    )
    return len(batch)
