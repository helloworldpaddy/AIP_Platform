from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from neo4j import GraphDatabase


@dataclass(frozen=True)
class Neo4jConfig:
    uri: str
    user: str
    password: str


def _config_from_env() -> Neo4jConfig:
    uri = (os.getenv("NEO4J_URI") or "bolt://localhost:7687").strip()
    auth = (os.getenv("NEO4J_AUTH") or "neo4j/neo4jpass").strip()
    if "/" not in auth:
        raise SystemExit("NEO4J_AUTH must be in the form username/password")
    user, password = auth.split("/", 1)
    return Neo4jConfig(uri=uri, user=user, password=password)


def main() -> None:
    cfg = _config_from_env()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=30)

    subject = {
        "party_external_id": "P-DEMO-SUBJECT",
        "party_name": "Demo Subject Ltd.",
        "party_type": "CUSTOMER",
        "country": "US",
        "is_pep": False,
        "is_shell": False,
        "high_risk_country": False,
    }

    # Counterparties with different "countries" (like SWIFT / wire context).
    cps = [
        {
            "party_external_id": "P-CP-PA-001",
            "party_name": "Canal Trading S.A.",
            "party_type": "CORPORATE",
            "country": "PA",
            "is_pep": False,
            "is_shell": True,
            "high_risk_country": True,
            "rel_type": "TRANSFERRED_TO",
            "txn_count": 6,
            "total_value": 250000.0,
            "currency": "USD",
        },
        {
            "party_external_id": "P-CP-AE-002",
            "party_name": "Gulf Logistics FZE",
            "party_type": "CORPORATE",
            "country": "AE",
            "is_pep": False,
            "is_shell": False,
            "high_risk_country": False,
            "rel_type": "TRANSFERRED_TO",
            "txn_count": 3,
            "total_value": 120000.0,
            "currency": "USD",
        },
        {
            "party_external_id": "P-CP-GB-003",
            "party_name": "Thames Consulting LLP",
            "party_type": "PROFESSIONAL_SERVICES",
            "country": "GB",
            "is_pep": True,
            "is_shell": False,
            "high_risk_country": False,
            "rel_type": "TRANSFERRED_TO",
            "txn_count": 2,
            "total_value": 80000.0,
            "currency": "GBP",
        },
    ]

    # A second-hop intermediary so hop=2 returns something meaningful too.
    intermediary = {
        "party_external_id": "P-INT-001",
        "party_name": "Intermediary Holdings LLC",
        "party_type": "CORPORATE",
        "country": "VG",
        "is_pep": False,
        "is_shell": True,
        "high_risk_country": True,
    }
    hop2 = {
        "party_external_id": "P-CP-TR-004",
        "party_name": "Bosporus Imports Ltd.",
        "party_type": "CORPORATE",
        "country": "TR",
        "is_pep": False,
        "is_shell": False,
        "high_risk_country": False,
        "rel_type": "BENEFICIAL_OWNER_OF",
        "txn_count": 1,
        "total_value": 45000.0,
        "currency": "USD",
    }

    # Second scenario: focus party MRP Goods (import / supplier-payment cluster).
    mrp_subject = {
        "party_external_id": "P-MRP-GOODS",
        "party_name": "MRP Goods",
        "party_type": "CUSTOMER",
        "country": "US",
        "is_pep": False,
        "is_shell": False,
        "high_risk_country": False,
    }
    mrp_counterparties = [
        {
            "party_external_id": "P-MRP-SUP-IN",
            "party_name": "Kolkata Textile Exports Pvt Ltd",
            "party_type": "CORPORATE",
            "country": "IN",
            "is_pep": False,
            "is_shell": False,
            "high_risk_country": False,
            "rel_type": "TRANSFERRED_TO",
            "txn_count": 11,
            "total_value": 520000.0,
            "currency": "USD",
        },
        {
            "party_external_id": "P-MRP-FW-HK",
            "party_name": "Harbour Lane Freight Ltd",
            "party_type": "CORPORATE",
            "country": "HK",
            "is_pep": False,
            "is_shell": True,
            "high_risk_country": True,
            "rel_type": "TRANSFERRED_TO",
            "txn_count": 4,
            "total_value": 210000.0,
            "currency": "USD",
        },
        {
            "party_external_id": "P-MRP-TRADE-AE",
            "party_name": "Desert Gate General Trading LLC",
            "party_type": "CORPORATE",
            "country": "AE",
            "is_pep": False,
            "is_shell": False,
            "high_risk_country": False,
            "rel_type": "TRANSFERRED_TO",
            "txn_count": 5,
            "total_value": 160000.0,
            "currency": "USD",
        },
    ]

    cypher = """
    MERGE (s:Party {party_external_id: $subject.party_external_id})
      SET s.party_name = $subject.party_name,
          s.party_type = $subject.party_type,
          s.country = $subject.country,
          s.is_pep = $subject.is_pep,
          s.is_shell = $subject.is_shell,
          s.high_risk_country = $subject.high_risk_country

    WITH s
    UNWIND $counterparties AS cp
    MERGE (c:Party {party_external_id: cp.party_external_id})
      SET c.party_name = cp.party_name,
          c.party_type = cp.party_type,
          c.country = cp.country,
          c.is_pep = cp.is_pep,
          c.is_shell = cp.is_shell,
          c.high_risk_country = cp.high_risk_country
    WITH s, c, cp
    CALL apoc.create.relationship(s, cp.rel_type, {
        last_seen: datetime(cp.last_seen),
        txn_count: cp.txn_count,
        total_value: cp.total_value,
        currency: cp.currency
    }, c) YIELD rel
    RETURN count(rel) AS relationships_created;
    """

    # Prepare relationship timestamps as ISO strings that Neo4j datetime() parses.
    cps_payload = []
    for cp in cps:
        cp = dict(cp)
        cp["last_seen"] = (cutoff + timedelta(days=7)).isoformat()
        cps_payload.append(cp)

    cypher2 = """
    MERGE (s:Party {party_external_id: $subject_id})
    MERGE (i:Party {party_external_id: $int.party_external_id})
      SET i.party_name = $int.party_name,
          i.party_type = $int.party_type,
          i.country = $int.country,
          i.is_pep = $int.is_pep,
          i.is_shell = $int.is_shell,
          i.high_risk_country = $int.high_risk_country
    MERGE (h:Party {party_external_id: $hop2.party_external_id})
      SET h.party_name = $hop2.party_name,
          h.party_type = $hop2.party_type,
          h.country = $hop2.country,
          h.is_pep = $hop2.is_pep,
          h.is_shell = $hop2.is_shell,
          h.high_risk_country = $hop2.high_risk_country
    WITH s, i, h
    CALL apoc.create.relationship(s, 'TRANSFERRED_TO', {
        last_seen: datetime($last_seen),
        txn_count: 1,
        total_value: 60000.0,
        currency: 'USD'
    }, i) YIELD rel AS r1
    WITH i, h, r1
    CALL apoc.create.relationship(i, $hop2.rel_type, {
        last_seen: datetime($last_seen),
        txn_count: $hop2.txn_count,
        total_value: $hop2.total_value,
        currency: $hop2.currency
    }, h) YIELD rel AS r2
    RETURN count(r1) + count(r2) AS relationships_created;
    """

    mrp_cps_payload = []
    for cp in mrp_counterparties:
        cp = dict(cp)
        cp["last_seen"] = (cutoff + timedelta(days=5)).isoformat()
        mrp_cps_payload.append(cp)

    driver = GraphDatabase.driver(cfg.uri, auth=(cfg.user, cfg.password))
    try:
        with driver.session() as session:
            n1 = session.run(
                cypher, subject=subject, counterparties=cps_payload
            ).single()["relationships_created"]
            n2 = session.run(
                cypher2,
                subject_id=subject["party_external_id"],
                int=intermediary,
                hop2=hop2,
                last_seen=(cutoff + timedelta(days=10)).isoformat(),
            ).single()["relationships_created"]
            n3 = session.run(
                cypher, subject=mrp_subject, counterparties=mrp_cps_payload
            ).single()["relationships_created"]
            parties = session.run("MATCH (p:Party) RETURN count(p) AS n").single()["n"]
            rels = session.run("MATCH ()-[r]->() RETURN count(r) AS n").single()["n"]
    finally:
        driver.close()

    print(
        f"Seeded Neo4j: parties={parties} relationships={rels} "
        f"(+{n1}+{n2} demo, +{n3} mrp-goods)"
    )


if __name__ == "__main__":
    main()

