"""Neo4j-backed `GraphProvider` for the investigation graph.

The schema is defined by `docker/init-neo4j/01-constraints.cypher`:

    (:Party {party_external_id, party_name, party_type, is_pep,
             is_shell, high_risk_country, ...})
    (:Account {account_external_id, ...})
    (:Transaction {transaction_external_id, timestamp, amount, currency, ...})

Relationships between parties accrete as the data layer matures (e.g.
`(:Party)-[:WIRE_TO {txn_count, total_value, currency, last_seen}]->(:Party)`).
This provider walks N hops from the subject, filters by `last_seen`, and
collapses the result into the `hop_neighbors` payload `data_tools.py`
documents.

The `hop_distance` is interpolated directly into the Cypher (Neo4j does
not bind parameters inside variable-length path quantifiers).  Safe
because `data_tools.neo4j_hop_traversal` validates `1 <= hop <= 3` before
calling.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from neo4j import AsyncDriver, AsyncGraphDatabase

from agents.rag_agent.config.settings import get_settings

from ..models.state import CaseTransaction

log = logging.getLogger(__name__)


_HOP_QUERY_TEMPLATE = """
MATCH path = (subject:Party {{party_external_id: $subject_id}})-[*1..{hop}]-(neighbor:Party)
WHERE neighbor <> subject
WITH neighbor, relationships(path) AS rels, length(path) AS hop_count
WHERE all(rel IN rels WHERE coalesce(rel.last_seen, datetime()) >= $cutoff)
WITH neighbor, last(rels) AS last_rel, hop_count
RETURN
    neighbor.party_external_id AS party_external_id,
    coalesce(neighbor.party_name, neighbor.party_external_id) AS party_name,
    coalesce(neighbor.party_type, 'OTHER') AS party_type,
    type(last_rel) AS relationship,
    coalesce(last_rel.txn_count, 0) AS txn_count,
    coalesce(last_rel.total_value, 0.0) AS total_value,
    coalesce(last_rel.currency, 'USD') AS currency,
    {{
        is_pep: coalesce(neighbor.is_pep, false),
        is_shell: coalesce(neighbor.is_shell, false),
        high_risk_country: coalesce(neighbor.high_risk_country, false)
    }} AS risk_flags,
    hop_count
ORDER BY hop_count ASC, total_value DESC
LIMIT $limit
"""


class Neo4jGraphProvider:
    """Async `GraphProvider` backed by a single shared Neo4j driver.

    Driver lifecycle is owned by the FastAPI lifespan: `connect()` is
    called once on startup, `close()` once on shutdown.  All hops reuse
    the underlying Bolt connection pool the driver maintains.
    """

    def __init__(
        self,
        *,
        uri: str,
        user: str,
        password: str,
        database: str = "neo4j",
        connection_timeout_seconds: int = 10,
        result_limit: int = 100,
    ) -> None:
        self._uri = uri
        self._user = user
        self._password = password
        self._database = database
        self._connection_timeout = connection_timeout_seconds
        self._result_limit = result_limit
        self._driver: AsyncDriver | None = None

    async def connect(self) -> None:
        if self._driver is not None:
            return
        self._driver = AsyncGraphDatabase.driver(
            self._uri,
            auth=(self._user, self._password),
            connection_timeout=self._connection_timeout,
        )
        # Verify connectivity early so a misconfigured deployment fails
        # at startup, not on the first agent run.
        await self._driver.verify_connectivity()
        log.info("aml.neo4j.connected uri=%s database=%s", self._uri, self._database)

    async def close(self) -> None:
        if self._driver is not None:
            await self._driver.close()
            self._driver = None

    async def hop_neighbors(
        self,
        subject_party_id: str,
        hop_distance: int,
        time_window_days: int,
    ) -> list[dict[str, Any]]:
        if self._driver is None:
            raise RuntimeError("Neo4jGraphProvider not connected — call connect() first")
        if not (1 <= hop_distance <= 3):
            raise ValueError(f"hop_distance must be in [1, 3], got {hop_distance}")

        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=time_window_days)
        query = _HOP_QUERY_TEMPLATE.format(hop=int(hop_distance))

        async with self._driver.session(database=self._database) as session:
            result = await session.run(
                query,
                subject_id=subject_party_id,
                cutoff=cutoff,
                limit=self._result_limit,
            )
            records = await result.data()

        return [
            {
                "party_external_id": r["party_external_id"],
                "party_name": r["party_name"],
                "party_type": r["party_type"],
                "relationship": r.get("relationship") or "RELATED",
                "txn_count": int(r.get("txn_count") or 0),
                "total_value": float(r.get("total_value") or 0.0),
                "currency": r.get("currency") or "USD",
                "risk_flags": r.get("risk_flags") or {},
                "hop_distance": int(r.get("hop_count") or hop_distance),
            }
            for r in records
        ]

    async def sync_case_transactions(
        self,
        *,
        subject_party_id: str,
        subject_party_name: str,
        case_id: UUID,
        transactions: list[CaseTransaction],
    ) -> int:
        """Upsert monitoring ledger rows into Neo4j (see `case_transactions_neo4j_sync`)."""
        if self._driver is None:
            raise RuntimeError("Neo4jGraphProvider not connected — call connect() first")
        from .case_transactions_neo4j_sync import sync_case_transactions_to_neo4j

        return await sync_case_transactions_to_neo4j(
            self._driver,
            database=self._database,
            subject_party_id=subject_party_id,
            subject_party_name=subject_party_name,
            case_id=case_id,
            transactions=transactions,
        )


def build_neo4j_provider_if_configured() -> Neo4jGraphProvider | None:
    """Construct (but do not connect) a provider when settings are present.

    Returns `None` when `NEO4J_URI` / `NEO4J_AUTH` are unset — callers
    should leave the `GraphProvider` slot empty and let
    `data_tools._require()` raise its standard "not configured" error if
    an agent attempts a hop.
    """
    cfg = get_settings().neo4j
    if not cfg.configured:
        log.info("aml.neo4j.skip reason=not_configured")
        return None
    return Neo4jGraphProvider(
        uri=cfg.uri,  # type: ignore[arg-type] — guarded by .configured
        user=cfg.user,
        password=cfg.password,
        database=cfg.database,
        connection_timeout_seconds=cfg.connection_timeout_seconds,
    )
