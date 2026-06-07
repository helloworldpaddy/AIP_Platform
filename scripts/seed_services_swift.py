"""Load SWIFT message rows into aml.case_swift_* for an existing or new case.

Usage:
    python scripts/seed_services_swift.py
    python scripts/seed_services_swift.py --case-number AML-SERVICES-SWIFT-2026-001
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from backend.aml.db.client import AmlRepositories, get_aml_db_client  # noqa: E402
from scripts.services_swift_seed_data import (  # noqa: E402
    SwiftMessageSeed,
    services_swift_demo_messages,
)


async def _txn_id_by_external(
    repos: AmlRepositories, case_id: UUID, external_id: str
) -> UUID | None:
    row = await repos.connection.fetchrow(
        """
        SELECT id FROM case_transactions
         WHERE case_id = $1 AND external_transaction_id = $2
        """,
        case_id,
        external_id,
    )
    return UUID(str(row["id"])) if row else None


async def _ensure_monitoring_scenarios(
    repos: AmlRepositories,
    case_id: UUID,
    log: logging.Logger,
) -> None:
    from scripts.services_swift_seed_data import services_swift_monitoring_scenarios  # noqa: E402

    for scen in services_swift_monitoring_scenarios():
        existing = await repos.case_monitoring.find_scenario_id(
            case_id, scen.scenario_code
        )
        if existing is not None:
            continue
        await repos.case_monitoring.insert_scenario(
            case_id,
            scen.scenario_code,
            scen.title,
            trigger_summary=scen.trigger_summary,
            trigger_facts=scen.trigger_facts,
            is_primary=scen.is_primary,
        )
        log.info("seed.swift.scenario_created code=%s", scen.scenario_code)


async def _link_message_scenarios(
    repos: AmlRepositories,
    case_id: UUID,
    msg_id: UUID,
    scenario_codes: tuple[str, ...],
    log: logging.Logger,
) -> None:
    for code in scenario_codes:
        scenario_id = await repos.case_monitoring.find_scenario_id(case_id, code)
        if scenario_id is None:
            log.warning(
                "seed.swift.scenario_missing code=%s case_id=%s", code, case_id
            )
            continue
        await repos.services_swift.link_message_scenario(msg_id, scenario_id)


async def seed_swift_messages(
    repos: AmlRepositories,
    case_id: UUID,
    messages: tuple[SwiftMessageSeed, ...],
    log: logging.Logger,
) -> int:
    await _ensure_monitoring_scenarios(repos, case_id, log)
    now = datetime.now(timezone.utc)
    inserted = 0
    cover_ids: dict[str, UUID] = {}

    for msg in messages:
        existing = await repos.services_swift.find_message_by_external_id(
            case_id, msg.external_message_id
        )
        if existing is not None:
            cover_ids[msg.external_message_id] = existing
            await _link_message_scenarios(
                repos, case_id, existing, msg.scenario_codes, log
            )
            log.info(
                "seed.swift.exists external_id=%s id=%s",
                msg.external_message_id,
                existing,
            )
            continue

        case_txn_id: UUID | None = None
        if msg.linked_transaction_external_id:
            case_txn_id = await _txn_id_by_external(
                repos, case_id, msg.linked_transaction_external_id
            )

        related_cover: UUID | None = None
        if msg.related_cover_external_id:
            related_cover = cover_ids.get(msg.related_cover_external_id)
            if related_cover is None:
                related_cover = await repos.services_swift.find_message_by_external_id(
                    case_id, msg.related_cover_external_id
                )

        booked_at = now + timedelta(hours=msg.booked_offset_hours)
        uetr = UUID(msg.uetr) if msg.uetr else None

        msg_id = await repos.services_swift.insert_message(
            case_id,
            msg.external_message_id,
            msg.message_type,
            booked_at,
            Decimal(msg.amount),
            msg.currency,
            uetr=uetr,
            sender_reference=msg.sender_reference,
            end_to_end_id=msg.end_to_end_id,
            value_date=booked_at.date(),
            charge_bearer=msg.charge_bearer,
            remittance_information=msg.remittance_information,
            sender_to_receiver_info=msg.sender_to_receiver_info,
            case_transaction_id=case_txn_id,
            related_cover_message_id=related_cover,
            raw_message={"seeded": True, "demo": True},
        )
        cover_ids[msg.external_message_id] = msg_id

        seq_to_pid: dict[int, UUID] = {}
        for p in msg.participants:
            pid = await repos.services_swift.insert_participant(
                msg_id,
                p.sequence_order,
                p.role,
                p.entity_kind,
                p.name,
                external_party_id=p.external_party_id,
                account_number=p.account_number,
                iban=p.iban,
                bic=p.bic,
                address_line1=p.address_line1,
                address_line2=p.address_line2,
                city=p.city,
                postal_code=p.postal_code,
                country_code=p.country_code,
                swift_field_tag=p.swift_field_tag,
                extra_fields=p.extra_fields,
            )
            seq_to_pid[p.sequence_order] = pid

        for leg in msg.legs:
            await repos.services_swift.insert_leg(
                msg_id,
                leg.leg_index,
                seq_to_pid[leg.from_sequence],
                seq_to_pid[leg.to_sequence],
                leg.leg_kind,
                relationship_label=leg.relationship_label,
                amount=Decimal(msg.amount),
                currency=msg.currency,
                notes=leg.notes,
            )

        await _link_message_scenarios(
            repos, case_id, msg_id, msg.scenario_codes, log
        )

        inserted += 1
        log.info(
            "seed.swift.created external_id=%s type=%s participants=%d legs=%d",
            msg.external_message_id,
            msg.message_type,
            len(msg.participants),
            len(msg.legs),
        )

    return inserted


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case-number",
        default="AML-SERVICES-SWIFT-2026-001",
        help="Case to attach SWIFT messages to.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log = logging.getLogger("seed_services_swift")

    db = get_aml_db_client()
    await db.connect()
    try:
        async with db.transaction() as repos:
            case = await repos.cases.get_by_number(args.case_number)
            if case is None:
                raise SystemExit(f"Case not found: {args.case_number}")
            n = await seed_swift_messages(
                repos, case.id, services_swift_demo_messages(), log
            )
    finally:
        await db.close()

    print(f"Seeded {n} SWIFT message(s) for case_number={args.case_number}")


if __name__ == "__main__":
    asyncio.run(main())
