"""Case-level monitoring scenarios and transaction ledger (aml.case_* tables)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg

from ...models.state import CaseTransaction


class CaseMonitoringRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def list_transactions_for_case(self, case_id: UUID) -> list[CaseTransaction]:
        rows = await self._conn.fetch(
            """
            SELECT id, case_id, external_transaction_id, booked_at, amount, currency,
                   direction::text AS direction,
                   payment_channel::text AS payment_channel,
                   product_category::text AS product_category,
                   counterparty_name, counterparty_external_id, counterparty_country, narrative
              FROM case_transactions
             WHERE case_id = $1
             ORDER BY booked_at DESC
            """,
            case_id,
        )
        return [CaseTransaction.model_validate(dict(r)) for r in rows]

    async def insert_scenario(
        self,
        case_id: UUID,
        scenario_code: str,
        title: str,
        *,
        trigger_summary: str | None = None,
        trigger_facts: dict[str, Any] | None = None,
        is_primary: bool = True,
    ) -> UUID:
        row = await self._conn.fetchrow(
            """
            INSERT INTO case_scenarios (
                case_id, scenario_code, title, status, source_system,
                trigger_summary, trigger_facts, is_primary
            )
            VALUES (
                $1, $2, $3, 'ALLEGED'::monitoring_scenario_status,
                'TRANSACTION_MONITORING', $4, COALESCE($5::jsonb, '{}'::jsonb), $6
            )
            RETURNING id
            """,
            case_id,
            scenario_code,
            title,
            trigger_summary,
            trigger_facts,
            is_primary,
        )
        if row is None:
            raise RuntimeError("insert_scenario returned no row")
        return UUID(str(row["id"]))

    async def insert_transaction(
        self,
        case_id: UUID,
        external_transaction_id: str,
        booked_at: datetime,
        amount: Decimal,
        currency: str,
        direction: str,
        payment_channel: str,
        product_category: str,
        *,
        counterparty_name: str | None = None,
        counterparty_external_id: str | None = None,
        counterparty_country: str | None = None,
        channel_details: dict[str, Any] | None = None,
        mcc: str | None = None,
        merchant_name: str | None = None,
        narrative: str | None = None,
        raw_payload: dict[str, Any] | None = None,
    ) -> UUID:
        row = await self._conn.fetchrow(
            """
            INSERT INTO case_transactions (
                case_id, external_transaction_id, booked_at, amount, currency,
                direction, payment_channel, product_category,
                counterparty_name, counterparty_external_id, counterparty_country,
                channel_details, mcc, merchant_name, narrative, raw_payload
            )
            VALUES (
                $1, $2, $3, $4, $5,
                $6::transaction_direction,
                $7::payment_channel,
                $8::product_category,
                $9, $10, $11,
                COALESCE($12::jsonb, '{}'::jsonb),
                $13, $14, $15,
                COALESCE($16::jsonb, '{}'::jsonb)
            )
            RETURNING id
            """,
            case_id,
            external_transaction_id,
            booked_at,
            amount,
            currency,
            direction,
            payment_channel,
            product_category,
            counterparty_name,
            counterparty_external_id,
            counterparty_country,
            channel_details,
            mcc,
            merchant_name,
            narrative,
            raw_payload,
        )
        if row is None:
            raise RuntimeError("insert_transaction returned no row")
        return UUID(str(row["id"]))

    async def link_transaction_scenario(
        self,
        transaction_id: UUID,
        scenario_id: UUID,
        *,
        link_role: str = "SUPPORTS",
    ) -> None:
        await self._conn.execute(
            """
            INSERT INTO case_transaction_scenario_links (transaction_id, scenario_id, link_role)
            VALUES ($1, $2, $3)
            """,
            transaction_id,
            scenario_id,
            link_role,
        )
