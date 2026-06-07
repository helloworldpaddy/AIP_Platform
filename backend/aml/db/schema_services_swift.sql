-- =============================================================================
-- AML: Services LOB — SWIFT payment messages (MT103 / MT202 / MT202COV)
-- =============================================================================
-- Run after schema.sql and schema_case_scenarios_transactions.sql.
--
-- Models a complete cross-border payment as:
--   * one header row per SWIFT message (customer credit or institution cover)
--   * ordered participants (parties + institutions) with BIC, account, address
--   * directed payment legs (party↔party, party↔institution, institution↔institution)
--
-- Optional link to aml.case_transactions via case_transaction_id for TM ledger join.
--
-- Services LOB cases typically carry many SWIFT messages (MT103 customer credits,
-- MT202 institution transfers, MT202COV cover payments) under one investigation.
-- Each message can substantiate one or more monitoring scenarios — see
-- case_swift_message_scenario_links (mirrors case_transaction_scenario_links).
-- =============================================================================

SET search_path TO aml, public;

-- -----------------------------------------------------------------------------
-- Enumerations
-- -----------------------------------------------------------------------------
DO $$ BEGIN
    CREATE TYPE swift_message_type AS ENUM (
        'MT103',      -- Single Customer Credit Transfer
        'MT202',      -- General Financial Institution Transfer
        'MT202COV'    -- Cover Payment (202 with sequence B)
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE swift_entity_kind AS ENUM (
        'PARTY',        -- non-bank customer / corporate / individual
        'INSTITUTION'   -- bank / NBFI with BIC
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE swift_participant_role AS ENUM (
        -- MT103 / MT202 field-aligned roles
        'ORDERING_CUSTOMER',           -- :50K:/:50F rate payer
        'SENDER_INSTITUTION',          -- :51A: (optional)
        'ORDERING_INSTITUTION',        -- :52A:/:52D:
        'SENDER_CORRESPONDENT',        -- :53A:/:53B:/:53D:
        'RECEIVER_CORRESPONDENT',      -- :54A:/:54B:/:54D:
        'THIRD_REIMBURSEMENT',         -- :55A:
        'INTERMEDIARY',                -- :56A:/:56C:/:56D:
        'ACCOUNT_WITH_INSTITUTION',    -- :57A:/:57B:/:57C:/:57D:
        'BENEFICIARY_INSTITUTION',     -- :58A:/:58D: (when beneficiary is a bank)
        'BENEFICIARY_CUSTOMER',        -- :59:/:59A:/:59F:
        'REIMBURSING_INSTITUTION',     -- MT202 specific
        'BENEFICIARY_INSTITUTION_MT202' -- MT202 field 58
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE swift_leg_kind AS ENUM (
        'PARTY_TO_PARTY',
        'PARTY_TO_INSTITUTION',
        'INSTITUTION_TO_PARTY',
        'INSTITUTION_TO_INSTITUTION'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- -----------------------------------------------------------------------------
-- Message header (one row per SWIFT message)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS case_swift_messages (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id                 UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    -- Stable id from payments hub / SWIFT gateway (unique per case)
    external_message_id     TEXT NOT NULL,
    message_type            swift_message_type NOT NULL,
    direction               transaction_direction NOT NULL DEFAULT 'DEBIT',
  -- ISO 20022 / SWIFT gpi
    uetr                    UUID,
    sender_reference        TEXT,
    end_to_end_id           TEXT,
    transaction_reference   TEXT,
    -- Amounts & dates
    value_date              DATE,
    booked_at               TIMESTAMPTZ NOT NULL,
    instructed_amount       NUMERIC(20,4) NOT NULL,
    instructed_currency     CHAR(3) NOT NULL,
    settlement_amount       NUMERIC(20,4),
    settlement_currency     CHAR(3),
    exchange_rate           NUMERIC(18,8),
    charge_bearer           TEXT,  -- OUR / SHA / BEN
    -- Narrative & compliance
    remittance_information  TEXT,
    sender_to_receiver_info TEXT,
    regulatory_reporting    JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Optional join to simplified TM ledger row
    case_transaction_id     UUID REFERENCES case_transactions(id) ON DELETE SET NULL,
    related_cover_message_id UUID REFERENCES case_swift_messages(id) ON DELETE SET NULL,
    source_system           TEXT NOT NULL DEFAULT 'SWIFT_GATEWAY',
    raw_message             JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (case_id, external_message_id)
);

CREATE INDEX IF NOT EXISTS idx_swift_msg_case ON case_swift_messages (case_id, booked_at DESC);
CREATE INDEX IF NOT EXISTS idx_swift_msg_type ON case_swift_messages (case_id, message_type);
CREATE INDEX IF NOT EXISTS idx_swift_msg_uetr ON case_swift_messages (uetr) WHERE uetr IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_swift_msg_txn ON case_swift_messages (case_transaction_id);

-- -----------------------------------------------------------------------------
-- Participants (ordered actors in the payment chain)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS case_swift_participants (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    swift_message_id        UUID NOT NULL REFERENCES case_swift_messages(id) ON DELETE CASCADE,
    sequence_order          SMALLINT NOT NULL,
    role                    swift_participant_role NOT NULL,
    entity_kind             swift_entity_kind NOT NULL,
    -- Identity
    name                    TEXT NOT NULL,
    external_party_id       TEXT,
    account_number          TEXT,
    iban                    TEXT,
    bic                     TEXT,
    lei                     TEXT,
    -- Postal address (beneficiary / ordering customer detail)
    address_line1           TEXT,
    address_line2           TEXT,
    address_line3           TEXT,
    city                    TEXT,
    region                  TEXT,
    postal_code             TEXT,
    country_code            CHAR(2),
    -- SWIFT field tag hint for traceability, e.g. '50K', '52A', '56A', '59'
    swift_field_tag         TEXT,
    extra_fields            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (swift_message_id, sequence_order),
    UNIQUE (swift_message_id, role)
);

CREATE INDEX IF NOT EXISTS idx_swift_part_msg ON case_swift_participants (swift_message_id);
CREATE INDEX IF NOT EXISTS idx_swift_part_bic ON case_swift_participants (bic) WHERE bic IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_swift_part_ext ON case_swift_participants (external_party_id)
    WHERE external_party_id IS NOT NULL;

-- -----------------------------------------------------------------------------
-- Payment legs (directed hops between participants)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS case_swift_payment_legs (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    swift_message_id        UUID NOT NULL REFERENCES case_swift_messages(id) ON DELETE CASCADE,
    leg_index               SMALLINT NOT NULL,
    from_participant_id     UUID NOT NULL REFERENCES case_swift_participants(id) ON DELETE CASCADE,
    to_participant_id       UUID NOT NULL REFERENCES case_swift_participants(id) ON DELETE CASCADE,
    leg_kind                swift_leg_kind NOT NULL,
    relationship_label      TEXT NOT NULL DEFAULT 'FUNDS_FLOW',
    amount                  NUMERIC(20,4),
    currency                CHAR(3),
    notes                   TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (swift_message_id, leg_index),
    CHECK (from_participant_id <> to_participant_id)
);

CREATE INDEX IF NOT EXISTS idx_swift_leg_msg ON case_swift_payment_legs (swift_message_id);
CREATE INDEX IF NOT EXISTS idx_swift_leg_from ON case_swift_payment_legs (from_participant_id);
CREATE INDEX IF NOT EXISTS idx_swift_leg_to ON case_swift_payment_legs (to_participant_id);

-- -----------------------------------------------------------------------------
-- Many-to-many: SWIFT messages <-> monitoring scenarios (TM typologies)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS case_swift_message_scenario_links (
    swift_message_id  UUID NOT NULL REFERENCES case_swift_messages(id) ON DELETE CASCADE,
    scenario_id       UUID NOT NULL REFERENCES case_scenarios(id) ON DELETE CASCADE,
    link_role         TEXT NOT NULL DEFAULT 'SUPPORTS',
    weight            NUMERIC(5,4),
    notes             TEXT,
    PRIMARY KEY (swift_message_id, scenario_id)
);

CREATE INDEX IF NOT EXISTS idx_swift_msg_scenario_scenario
    ON case_swift_message_scenario_links (scenario_id);

CREATE OR REPLACE FUNCTION aml.enforce_swift_scenario_same_case() RETURNS trigger AS $$
DECLARE
    msg_case UUID;
    scen_case UUID;
BEGIN
    SELECT case_id INTO msg_case FROM aml.case_swift_messages WHERE id = NEW.swift_message_id;
    SELECT case_id INTO scen_case FROM aml.case_scenarios WHERE id = NEW.scenario_id;
    IF msg_case IS DISTINCT FROM scen_case THEN
        RAISE EXCEPTION 'swift message % and scenario % must belong to the same case',
            NEW.swift_message_id, NEW.scenario_id USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_swift_scenario_same_case ON case_swift_message_scenario_links;
CREATE TRIGGER trg_swift_scenario_same_case
    BEFORE INSERT OR UPDATE ON case_swift_message_scenario_links
    FOR EACH ROW EXECUTE FUNCTION aml.enforce_swift_scenario_same_case();

-- =============================================================================
-- End of services SWIFT schema
-- =============================================================================
