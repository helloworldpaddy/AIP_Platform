"""Services LOB SWIFT message repository (MT103 / MT202 / MT202COV)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg

from ...models.state import SwiftMessage, SwiftParticipant, SwiftPaymentLeg


class ServicesSwiftRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def list_messages_for_case(self, case_id: UUID) -> list[SwiftMessage]:
        rows = await self._conn.fetch(
            """
            SELECT id, case_id, external_message_id, message_type::text AS message_type,
                   direction::text AS direction, uetr, sender_reference, end_to_end_id,
                   transaction_reference, value_date, booked_at, instructed_amount,
                   instructed_currency, settlement_amount, settlement_currency,
                   exchange_rate, charge_bearer, remittance_information,
                   sender_to_receiver_info, regulatory_reporting, case_transaction_id,
                   related_cover_message_id, source_system
              FROM case_swift_messages
             WHERE case_id = $1
             ORDER BY booked_at DESC
            """,
            case_id,
        )
        if not rows:
            return []

        msg_ids = [r["id"] for r in rows]
        participants = await self._conn.fetch(
            """
            SELECT id, swift_message_id, sequence_order, role::text AS role,
                   entity_kind::text AS entity_kind, name, external_party_id,
                   account_number, iban, bic, lei, address_line1, address_line2,
                   address_line3, city, region, postal_code, country_code,
                   swift_field_tag
              FROM case_swift_participants
             WHERE swift_message_id = ANY($1::uuid[])
             ORDER BY swift_message_id, sequence_order
            """,
            msg_ids,
        )
        legs = await self._conn.fetch(
            """
            SELECT id, swift_message_id, leg_index, from_participant_id,
                   to_participant_id, leg_kind::text AS leg_kind,
                   relationship_label, amount, currency, notes
              FROM case_swift_payment_legs
             WHERE swift_message_id = ANY($1::uuid[])
             ORDER BY swift_message_id, leg_index
            """,
            msg_ids,
        )

        parts_by_msg: dict[UUID, list[SwiftParticipant]] = {}
        for p in participants:
            mid = UUID(str(p["swift_message_id"]))
            parts_by_msg.setdefault(mid, []).append(
                SwiftParticipant.model_validate(dict(p))
            )

        legs_by_msg: dict[UUID, list[SwiftPaymentLeg]] = {}
        for leg in legs:
            mid = UUID(str(leg["swift_message_id"]))
            legs_by_msg.setdefault(mid, []).append(
                SwiftPaymentLeg.model_validate(dict(leg))
            )

        scenario_rows = await self._conn.fetch(
            """
            SELECT l.swift_message_id, s.scenario_code
              FROM case_swift_message_scenario_links l
              JOIN case_scenarios s ON s.id = l.scenario_id
             WHERE l.swift_message_id = ANY($1::uuid[])
             ORDER BY s.scenario_code
            """,
            msg_ids,
        )
        scenarios_by_msg: dict[UUID, list[str]] = {}
        for sr in scenario_rows:
            mid = UUID(str(sr["swift_message_id"]))
            scenarios_by_msg.setdefault(mid, []).append(str(sr["scenario_code"]))

        out: list[SwiftMessage] = []
        for r in rows:
            mid = UUID(str(r["id"]))
            data = dict(r)
            data["participants"] = parts_by_msg.get(mid, [])
            data["legs"] = legs_by_msg.get(mid, [])
            data["scenario_codes"] = scenarios_by_msg.get(mid, [])
            out.append(SwiftMessage.model_validate(data))
        return out

    async def insert_message(
        self,
        case_id: UUID,
        external_message_id: str,
        message_type: str,
        booked_at: datetime,
        instructed_amount: Decimal,
        instructed_currency: str,
        direction: str = "DEBIT",
        *,
        uetr: UUID | None = None,
        sender_reference: str | None = None,
        end_to_end_id: str | None = None,
        transaction_reference: str | None = None,
        value_date: date | None = None,
        settlement_amount: Decimal | None = None,
        settlement_currency: str | None = None,
        exchange_rate: Decimal | None = None,
        charge_bearer: str | None = None,
        remittance_information: str | None = None,
        sender_to_receiver_info: str | None = None,
        regulatory_reporting: dict[str, Any] | None = None,
        case_transaction_id: UUID | None = None,
        related_cover_message_id: UUID | None = None,
        source_system: str = "SWIFT_GATEWAY",
        raw_message: dict[str, Any] | None = None,
    ) -> UUID:
        row = await self._conn.fetchrow(
            """
            INSERT INTO case_swift_messages (
                case_id, external_message_id, message_type, direction, uetr,
                sender_reference, end_to_end_id, transaction_reference, value_date,
                booked_at, instructed_amount, instructed_currency,
                settlement_amount, settlement_currency, exchange_rate,
                charge_bearer, remittance_information, sender_to_receiver_info,
                regulatory_reporting, case_transaction_id, related_cover_message_id,
                source_system, raw_message
            )
            VALUES (
                $1, $2, $3::swift_message_type, $4::transaction_direction, $5,
                $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18,
                COALESCE($19::jsonb, '{}'::jsonb), $20, $21, $22,
                COALESCE($23::jsonb, '{}'::jsonb)
            )
            RETURNING id
            """,
            case_id,
            external_message_id,
            message_type,
            direction,
            uetr,
            sender_reference,
            end_to_end_id,
            transaction_reference,
            value_date,
            booked_at,
            instructed_amount,
            instructed_currency,
            settlement_amount,
            settlement_currency,
            exchange_rate,
            charge_bearer,
            remittance_information,
            sender_to_receiver_info,
            regulatory_reporting,
            case_transaction_id,
            related_cover_message_id,
            source_system,
            raw_message,
        )
        if row is None:
            raise RuntimeError("insert_message returned no row")
        return UUID(str(row["id"]))

    async def insert_participant(
        self,
        swift_message_id: UUID,
        sequence_order: int,
        role: str,
        entity_kind: str,
        name: str,
        *,
        external_party_id: str | None = None,
        account_number: str | None = None,
        iban: str | None = None,
        bic: str | None = None,
        lei: str | None = None,
        address_line1: str | None = None,
        address_line2: str | None = None,
        address_line3: str | None = None,
        city: str | None = None,
        region: str | None = None,
        postal_code: str | None = None,
        country_code: str | None = None,
        swift_field_tag: str | None = None,
        extra_fields: dict[str, Any] | None = None,
    ) -> UUID:
        row = await self._conn.fetchrow(
            """
            INSERT INTO case_swift_participants (
                swift_message_id, sequence_order, role, entity_kind, name,
                external_party_id, account_number, iban, bic, lei,
                address_line1, address_line2, address_line3, city, region,
                postal_code, country_code, swift_field_tag, extra_fields
            )
            VALUES (
                $1, $2, $3::swift_participant_role, $4::swift_entity_kind, $5,
                $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18,
                COALESCE($19::jsonb, '{}'::jsonb)
            )
            RETURNING id
            """,
            swift_message_id,
            sequence_order,
            role,
            entity_kind,
            name,
            external_party_id,
            account_number,
            iban,
            bic,
            lei,
            address_line1,
            address_line2,
            address_line3,
            city,
            region,
            postal_code,
            country_code,
            swift_field_tag,
            extra_fields,
        )
        if row is None:
            raise RuntimeError("insert_participant returned no row")
        return UUID(str(row["id"]))

    async def insert_leg(
        self,
        swift_message_id: UUID,
        leg_index: int,
        from_participant_id: UUID,
        to_participant_id: UUID,
        leg_kind: str,
        *,
        relationship_label: str = "FUNDS_FLOW",
        amount: Decimal | None = None,
        currency: str | None = None,
        notes: str | None = None,
    ) -> UUID:
        row = await self._conn.fetchrow(
            """
            INSERT INTO case_swift_payment_legs (
                swift_message_id, leg_index, from_participant_id, to_participant_id,
                leg_kind, relationship_label, amount, currency, notes
            )
            VALUES (
                $1, $2, $3, $4, $5::swift_leg_kind, $6, $7, $8, $9
            )
            RETURNING id
            """,
            swift_message_id,
            leg_index,
            from_participant_id,
            to_participant_id,
            leg_kind,
            relationship_label,
            amount,
            currency,
            notes,
        )
        if row is None:
            raise RuntimeError("insert_leg returned no row")
        return UUID(str(row["id"]))

    async def find_message_by_external_id(
        self, case_id: UUID, external_message_id: str
    ) -> UUID | None:
        row = await self._conn.fetchrow(
            """
            SELECT id FROM case_swift_messages
             WHERE case_id = $1 AND external_message_id = $2
            """,
            case_id,
            external_message_id,
        )
        return UUID(str(row["id"])) if row else None

    async def link_message_scenario(
        self,
        swift_message_id: UUID,
        scenario_id: UUID,
        *,
        link_role: str = "SUPPORTS",
        notes: str | None = None,
    ) -> None:
        await self._conn.execute(
            """
            INSERT INTO case_swift_message_scenario_links (
                swift_message_id, scenario_id, link_role, notes
            )
            VALUES ($1, $2, $3, $4)
            ON CONFLICT DO NOTHING
            """,
            swift_message_id,
            scenario_id,
            link_role,
            notes,
        )
