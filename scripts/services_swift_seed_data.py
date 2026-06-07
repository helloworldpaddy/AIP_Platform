"""Synthetic SWIFT MT103 / MT202COV payloads for the services-swift demo case.

Used by scripts/aml_seed.py and scripts/seed_services_swift.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SwiftScenarioSeed:
    scenario_code: str
    title: str
    trigger_summary: str | None = None
    trigger_facts: dict[str, Any] = field(default_factory=dict)
    is_primary: bool = False


@dataclass(frozen=True)
class SwiftParticipantSeed:
    sequence_order: int
    role: str
    entity_kind: str
    name: str
    external_party_id: str | None = None
    account_number: str | None = None
    iban: str | None = None
    bic: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    postal_code: str | None = None
    country_code: str | None = None
    swift_field_tag: str | None = None
    extra_fields: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SwiftLegSeed:
    leg_index: int
    from_sequence: int
    to_sequence: int
    leg_kind: str
    relationship_label: str = "FUNDS_FLOW"
    notes: str | None = None


@dataclass(frozen=True)
class SwiftMessageSeed:
    external_message_id: str
    message_type: str
    booked_offset_hours: int
    amount: str
    currency: str
    linked_transaction_external_id: str | None = None
    related_cover_external_id: str | None = None
    uetr: str | None = None
    sender_reference: str | None = None
    end_to_end_id: str | None = None
    charge_bearer: str | None = "SHA"
    remittance_information: str | None = None
    sender_to_receiver_info: str | None = None
    scenario_codes: tuple[str, ...] = ()
    participants: tuple[SwiftParticipantSeed, ...] = ()
    legs: tuple[SwiftLegSeed, ...] = ()


def services_swift_demo_messages() -> tuple[SwiftMessageSeed, ...]:
    """Three MT103 customer payments + one MT202COV cover for the DE corridor."""
    subject_id = "party.services.swift.demo.001"
    subject_name = "Northwind Trade Services GmbH"

    mt103_de = SwiftMessageSeed(
        external_message_id="SVC-SWIFT-MSG-103-001",
        message_type="MT103",
        linked_transaction_external_id="SVC-SWIFT-TXN-001",
        booked_offset_hours=-8,
        amount="425000.0000",
        currency="EUR",
        uetr="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        sender_reference="SWF-2026-0412-DE-01",
        end_to_end_id="E2E-NW-DE-8841",
        remittance_information="INV-NW-8841 / goods settlement",
        sender_to_receiver_info="/ACC/CHASUS33 intermediary routing",
        scenario_codes=("TM-COMM-SWIFT-011", "TM-COMM-SWIFT-012"),
        participants=(
            SwiftParticipantSeed(
                1,
                "ORDERING_CUSTOMER",
                "PARTY",
                subject_name,
                external_party_id=subject_id,
                iban="DE89370400440532013000",
                address_line1="Friedrichstrasse 123",
                city="Berlin",
                postal_code="10117",
                country_code="DE",
                swift_field_tag="50K",
            ),
            SwiftParticipantSeed(
                2,
                "ORDERING_INSTITUTION",
                "INSTITUTION",
                "Commerzbank AG",
                bic="COBADEFFXXX",
                country_code="DE",
                swift_field_tag="52A",
            ),
            SwiftParticipantSeed(
                3,
                "SENDER_CORRESPONDENT",
                "INSTITUTION",
                "Commerzbank AG (nostro sender)",
                bic="COBADEFFXXX",
                country_code="DE",
                swift_field_tag="53A",
            ),
            SwiftParticipantSeed(
                4,
                "INTERMEDIARY",
                "INSTITUTION",
                "JPMorgan Chase Bank N.A.",
                bic="CHASUS33XXX",
                address_line1="383 Madison Avenue",
                city="New York",
                country_code="US",
                swift_field_tag="56A",
            ),
            SwiftParticipantSeed(
                5,
                "ACCOUNT_WITH_INSTITUTION",
                "INSTITUTION",
                "Deutsche Bank AG",
                bic="DEUTDEFFXXX",
                country_code="DE",
                swift_field_tag="57A",
            ),
            SwiftParticipantSeed(
                6,
                "BENEFICIARY_CUSTOMER",
                "PARTY",
                "Rhein Components AG",
                external_party_id="cp.de.rhein.01",
                iban="DE89370400440532013999",
                address_line1="Industriepark 7",
                city="Frankfurt am Main",
                postal_code="60486",
                country_code="DE",
                swift_field_tag="59",
            ),
        ),
        legs=(
            SwiftLegSeed(1, 1, 2, "PARTY_TO_INSTITUTION", notes="Customer initiates at Commerzbank"),
            SwiftLegSeed(2, 2, 3, "INSTITUTION_TO_INSTITUTION", notes="Ordering bank sender correspondent"),
            SwiftLegSeed(3, 3, 4, "INSTITUTION_TO_INSTITUTION", notes="USD/EUR correspondent hop via CHAS"),
            SwiftLegSeed(4, 4, 5, "INSTITUTION_TO_INSTITUTION", notes="Intermediary to beneficiary bank"),
            SwiftLegSeed(5, 5, 6, "INSTITUTION_TO_PARTY", notes="Credit to ultimate beneficiary"),
        ),
    )

    mt103_sg = SwiftMessageSeed(
        external_message_id="SVC-SWIFT-MSG-103-002",
        message_type="MT103",
        linked_transaction_external_id="SVC-SWIFT-TXN-002",
        booked_offset_hours=-72,
        amount="510000.0000",
        currency="USD",
        uetr="b2c3d4e5-f6a7-8901-bcde-f12345678901",
        sender_reference="SWF-2026-0408-SG-02",
        end_to_end_id="E2E-NW-SG-2291",
        remittance_information="FREIGHT Q1 / SGSVC-2291",
        scenario_codes=("TM-COMM-SWIFT-011",),
        participants=(
            SwiftParticipantSeed(
                1,
                "ORDERING_CUSTOMER",
                "PARTY",
                subject_name,
                external_party_id=subject_id,
                country_code="DE",
                swift_field_tag="50K",
            ),
            SwiftParticipantSeed(
                2,
                "ORDERING_INSTITUTION",
                "INSTITUTION",
                "Commerzbank AG",
                bic="COBADEFFXXX",
                country_code="DE",
                swift_field_tag="52A",
            ),
            SwiftParticipantSeed(
                3,
                "INTERMEDIARY",
                "INSTITUTION",
                "JPMorgan Chase Bank N.A.",
                bic="CHASUS33XXX",
                country_code="US",
                swift_field_tag="56A",
            ),
            SwiftParticipantSeed(
                4,
                "ACCOUNT_WITH_INSTITUTION",
                "INSTITUTION",
                "DBS Bank Ltd",
                bic="DBSSSGSGXXX",
                country_code="SG",
                swift_field_tag="57A",
            ),
            SwiftParticipantSeed(
                5,
                "BENEFICIARY_CUSTOMER",
                "PARTY",
                "Harbour Logistics Pte Ltd",
                external_party_id="cp.sg.harb.02",
                address_line1="8 Marina Boulevard",
                city="Singapore",
                postal_code="018981",
                country_code="SG",
                swift_field_tag="59",
            ),
        ),
        legs=(
            SwiftLegSeed(1, 1, 2, "PARTY_TO_INSTITUTION"),
            SwiftLegSeed(2, 2, 3, "INSTITUTION_TO_INSTITUTION"),
            SwiftLegSeed(3, 3, 4, "INSTITUTION_TO_INSTITUTION"),
            SwiftLegSeed(4, 4, 5, "INSTITUTION_TO_PARTY"),
        ),
    )

    mt103_ae = SwiftMessageSeed(
        external_message_id="SVC-SWIFT-MSG-103-003",
        message_type="MT103",
        linked_transaction_external_id="SVC-SWIFT-TXN-003",
        booked_offset_hours=-168,
        amount="245000.0000",
        currency="USD",
        uetr="c3d4e5f6-a7b8-9012-cdef-123456789012",
        sender_reference="SWF-2026-0401-AE-03",
        end_to_end_id="E2E-NW-AE-SOW03",
        remittance_information="CONSULTING RETAINER / SOW-2026-03",
        scenario_codes=("TM-COMM-SWIFT-011",),
        participants=(
            SwiftParticipantSeed(
                1,
                "ORDERING_CUSTOMER",
                "PARTY",
                subject_name,
                external_party_id=subject_id,
                country_code="DE",
                swift_field_tag="50K",
            ),
            SwiftParticipantSeed(
                2,
                "ORDERING_INSTITUTION",
                "INSTITUTION",
                "Commerzbank AG",
                bic="COBADEFFXXX",
                country_code="DE",
                swift_field_tag="52A",
            ),
            SwiftParticipantSeed(
                3,
                "INTERMEDIARY",
                "INSTITUTION",
                "JPMorgan Chase Bank N.A.",
                bic="CHASUS33XXX",
                country_code="US",
                swift_field_tag="56A",
            ),
            SwiftParticipantSeed(
                4,
                "ACCOUNT_WITH_INSTITUTION",
                "INSTITUTION",
                "First Abu Dhabi Bank",
                bic="NBADAEAAXXX",
                country_code="AE",
                swift_field_tag="57A",
            ),
            SwiftParticipantSeed(
                5,
                "BENEFICIARY_CUSTOMER",
                "PARTY",
                "Gulf Procurement LLC",
                external_party_id="cp.ae.gulf.03",
                address_line1="Sheikh Zayed Road, Office 1204",
                city="Dubai",
                country_code="AE",
                swift_field_tag="59",
            ),
        ),
        legs=(
            SwiftLegSeed(1, 1, 2, "PARTY_TO_INSTITUTION"),
            SwiftLegSeed(2, 2, 3, "INSTITUTION_TO_INSTITUTION"),
            SwiftLegSeed(3, 3, 4, "INSTITUTION_TO_INSTITUTION"),
            SwiftLegSeed(4, 4, 5, "INSTITUTION_TO_PARTY"),
        ),
    )

    mt202cov = SwiftMessageSeed(
        external_message_id="SVC-SWIFT-MSG-202COV-001",
        message_type="MT202COV",
        related_cover_external_id="SVC-SWIFT-MSG-103-001",
        booked_offset_hours=-7,
        amount="425000.0000",
        currency="EUR",
        sender_reference="COV-SWF-2026-0412-DE-01",
        remittance_information="Cover for MT103 SWF-2026-0412-DE-01",
        scenario_codes=("TM-COMM-SWIFT-012",),
        participants=(
            SwiftParticipantSeed(
                1,
                "ORDERING_INSTITUTION",
                "INSTITUTION",
                "JPMorgan Chase Bank N.A.",
                bic="CHASUS33XXX",
                country_code="US",
                swift_field_tag="52A",
            ),
            SwiftParticipantSeed(
                2,
                "INTERMEDIARY",
                "INSTITUTION",
                "Deutsche Bank AG (cover routing)",
                bic="DEUTDEFFXXX",
                country_code="DE",
                swift_field_tag="56A",
            ),
            SwiftParticipantSeed(
                3,
                "ACCOUNT_WITH_INSTITUTION",
                "INSTITUTION",
                "Deutsche Bank AG",
                bic="DEUTDEFFXXX",
                country_code="DE",
                swift_field_tag="57A",
            ),
            SwiftParticipantSeed(
                4,
                "BENEFICIARY_INSTITUTION",
                "INSTITUTION",
                "Deutsche Bank AG (beneficiary institution)",
                bic="DEUTDEFFXXX",
                country_code="DE",
                swift_field_tag="58A",
            ),
        ),
        legs=(
            SwiftLegSeed(1, 1, 2, "INSTITUTION_TO_INSTITUTION", notes="Cover sent from US correspondent"),
            SwiftLegSeed(2, 2, 3, "INSTITUTION_TO_INSTITUTION", notes="Intermediary routing"),
            SwiftLegSeed(3, 3, 4, "INSTITUTION_TO_INSTITUTION", notes="Settlement at beneficiary bank"),
        ),
    )

    mt202_sg = SwiftMessageSeed(
        external_message_id="SVC-SWIFT-MSG-202-001",
        message_type="MT202",
        booked_offset_hours=-71,
        amount="510000.0000",
        currency="USD",
        sender_reference="SWF-2026-0408-SG-202",
        remittance_information="Institution settlement — SG corridor (paired with MT103)",
        scenario_codes=("TM-COMM-SWIFT-013",),
        participants=(
            SwiftParticipantSeed(
                1,
                "ORDERING_INSTITUTION",
                "INSTITUTION",
                "JPMorgan Chase Bank N.A.",
                bic="CHASUS33XXX",
                country_code="US",
                swift_field_tag="52A",
            ),
            SwiftParticipantSeed(
                2,
                "INTERMEDIARY",
                "INSTITUTION",
                "Standard Chartered Bank",
                bic="SCBLUS33XXX",
                country_code="US",
                swift_field_tag="56A",
            ),
            SwiftParticipantSeed(
                3,
                "ACCOUNT_WITH_INSTITUTION",
                "INSTITUTION",
                "DBS Bank Ltd",
                bic="DBSSSGSGXXX",
                country_code="SG",
                swift_field_tag="57A",
            ),
            SwiftParticipantSeed(
                4,
                "BENEFICIARY_INSTITUTION_MT202",
                "INSTITUTION",
                "DBS Bank Ltd (beneficiary institution)",
                bic="DBSSSGSGXXX",
                country_code="SG",
                swift_field_tag="58A",
            ),
        ),
        legs=(
            SwiftLegSeed(1, 1, 2, "INSTITUTION_TO_INSTITUTION", notes="US correspondent routing"),
            SwiftLegSeed(2, 2, 3, "INSTITUTION_TO_INSTITUTION", notes="Intermediary to account-with"),
            SwiftLegSeed(3, 3, 4, "INSTITUTION_TO_INSTITUTION", notes="Settlement at beneficiary bank"),
        ),
    )

    return (mt103_de, mt103_sg, mt103_ae, mt202cov, mt202_sg)


def services_swift_monitoring_scenarios() -> tuple[SwiftScenarioSeed, ...]:
    """AML TM typologies for Services LOB SWIFT message bundles."""
    return (
        SwiftScenarioSeed(
            scenario_code="TM-COMM-SWIFT-011",
            title="Commercial SWIFT — single intermediary, multiple beneficiaries",
            trigger_summary=(
                "Repeated use of the same intermediary BIC for unrelated "
                "cross-border beneficiaries within a short monitoring window"
            ),
            trigger_facts={
                "window_business_days": 10,
                "intermediary_bic": "CHASUS33XXX",
                "message_types": ["MT103"],
            },
            is_primary=True,
        ),
        SwiftScenarioSeed(
            scenario_code="TM-COMM-SWIFT-012",
            title="SWIFT cover — MT202COV paired with customer credit",
            trigger_summary=(
                "MT202COV cover message references MT103; sequencing under review"
            ),
            trigger_facts={"message_types": ["MT202COV", "MT103"]},
        ),
        SwiftScenarioSeed(
            scenario_code="TM-COMM-SWIFT-013",
            title="Institution chain — MT202 settlement",
            trigger_summary="MT202 institution transfer on corridor with customer credits",
            trigger_facts={"message_types": ["MT202"], "corridor": "SG"},
        ),
    )
