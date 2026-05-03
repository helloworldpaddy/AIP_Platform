-- =============================================================================
-- AML: monitoring scenarios + case transactions (additive design)
-- =============================================================================
-- Run after backend/aml/db/schema.sql in the same database (schema aml).
--
-- Design intent
-- -------------
-- 1) One case may explain one or many monitoring scenarios (rules / typologies)
--    that fired or are under review — not just a single alert_payload blob.
-- 2) A normalized transaction ledger hangs off the case so agents and analysts
--    can reconcile amounts, counterparties, rails, and product context.
-- 3) Payment diversity across the bank’s product set is modeled as:
--      * payment_channel  — banking rail / delivery channel (branch, ATM, digital,
--        card, wire, ACH, …). Not “retail” as in e-commerce merchants.
--      * product_category — banking product line (retail banking = consumer/customer
--        segment products: checking, savings, debit/credit card, mortgage, etc.;
--        plus commercial / wealth where relevant).
--      * channel_details  — JSONB for rail-specific fields (MCC for card spend at
--        a merchant, entry mode, IMAD/ACH addenda, biller id, etc.).
-- 4) Transactions and scenarios are many-to-many: link rows in
--    case_transaction_scenario_links (see below).
-- 5) Each case is opened under a single Line of Business (LOB) at intake:
--    CARDS, RETAIL_BANKING, or SERVICES — see `aml.cases.line_of_business` in
--    schema.sql. Scenario and transaction typing should stay consistent with
--    that LOB (a case is not multi-LOB).
--
-- Relationship sketch
-- -------------------
--   cases 1──* case_scenarios
--   cases 1──* case_transactions
--   case_scenarios *──* case_transactions  via case_transaction_scenario_links
--     (many-to-many, both directions):
--       * One transaction may substantiate or explain MULTIPLE scenarios
--         (e.g. same wire hits velocity + high-risk corridor rules).
--       * One scenario may be supported by MULTIPLE transactions
--         (aggregate alert across a pattern of txns).
--     A transaction can also exist with ZERO links (context-only / pre-linking).
--
-- PostgreSQL note: if you already created these ENUM types with older labels
-- (merchant/e-commerce “retail”), Postgres will not replace them on re-run.
-- New environments get the definitions below; existing DBs need a deliberate
-- migration (new type + column alter, or rebuild) before relying on new values.
-- =============================================================================

SET search_path TO aml, public;

-- -----------------------------------------------------------------------------
-- Backfill: cases.line_of_business (if DB was created before column existed)
-- -----------------------------------------------------------------------------
DO $$ BEGIN
    CREATE TYPE line_of_business AS ENUM (
        'CARDS',
        'RETAIL_BANKING',
        'SERVICES'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE aml.cases
    ADD COLUMN IF NOT EXISTS line_of_business line_of_business
    NOT NULL DEFAULT 'RETAIL_BANKING';

CREATE INDEX IF NOT EXISTS idx_cases_line_of_business ON aml.cases (line_of_business);

-- -----------------------------------------------------------------------------
-- Enumerations
-- -----------------------------------------------------------------------------
DO $$ BEGIN
    CREATE TYPE monitoring_scenario_status AS ENUM (
        'ALLEGED',      -- raised by TM / rules engine
        'UNDER_REVIEW',
        'CONFIRMED',
        'DISMISSED',
        'SUPERSEDED'    -- replaced by a newer scenario row / rule version
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE payment_channel AS ENUM (
        -- Service / delivery channel for a retail-banking or other customer (not merchant “retail”)
        'BRANCH',                 -- teller or platform-assisted in branch
        'ATM',                    -- cash dispense, deposit, balance inquiry
        'DIGITAL_BANKING',        -- online / mobile bank: internal xfer, A2A, scheduled xfer
        'CALL_CENTER',            -- telephone banking–initiated payment / xfer
        'CARD_POS',               -- debit/credit purchase at physical terminal (customer card)
        'CARD_CONTACTLESS',       -- tap-to-pay
        'CARD_NOT_PRESENT',       -- e-com, mail, phone — card auth without chip/tap
        'P2P_PUSH',               -- e.g. Zelle, bank RTP to consumer, push-to-wallet
        'WIRE',                   -- Fedwire / SWIFT-style bank wire
        'ACH',                    -- ACH credit or debit
        'SEPA',                   -- EU ACH-equivalent if applicable
        'RTP_INSTANT',            -- instant / real-time payment rail (non-card)
        'BILL_PAY',               -- bank bill-pay / biller-direct
        'CHECK',                  -- paper / image check
        'MOBILE_WALLET_BANK',     -- bank-branded wallet / super-app rail
        'CRYPTO_FIAT_BRIDGE',     -- on/off ramp if the bank books it
        'OTHER'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE product_category AS ENUM (
        -- Retail banking (consumer / mass-market customer) — deposit & lending products
        'RETAIL_CHECKING',
        'RETAIL_SAVINGS',
        'RETAIL_MONEY_MARKET',
        'RETAIL_CERTIFICATE_DEPOSIT',
        'RETAIL_DEBIT_CARD',
        'RETAIL_CREDIT_CARD',
        'RETAIL_MORTGAGE',
        'RETAIL_HOME_EQUITY',
        'RETAIL_AUTO_LOAN',
        'RETAIL_PERSONAL_LOAN',
        'RETAIL_LINE_OF_CREDIT',
        'RETAIL_OVERDRAFT_LINE',
        -- Non–retail-banking segments (same rails, different product set)
        'SMALL_BUSINESS',
        'COMMERCIAL',
        'WEALTH_PRIVATE',
        -- Cross-cutting / ancillary
        'FX_REMITTANCE',
        'SAFE_DEPOSIT_OR_MISC',
        'UNKNOWN'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE transaction_direction AS ENUM (
        'DEBIT',    -- out of subject / customer view
        'CREDIT'    -- into subject
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- -----------------------------------------------------------------------------
-- Optional catalog of scenario codes (seed-friendly; cases may also use ad-hoc codes)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS monitoring_scenario_catalog (
    scenario_code   TEXT PRIMARY KEY,
    domain          TEXT NOT NULL,  -- e.g. 'RETAIL_BANKING', 'CARDS', 'PAYMENTS', 'CROSS_BORDER'
    title           TEXT NOT NULL,
    description     TEXT,
    typical_rules   TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scenario_catalog_domain
    ON monitoring_scenario_catalog (domain);

-- -----------------------------------------------------------------------------
-- Scenarios attached to a case (one row per fired / reviewed typology)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS case_scenarios (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id             UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    scenario_code       TEXT NOT NULL,
    scenario_version    TEXT,
    title               TEXT,
    status              monitoring_scenario_status NOT NULL DEFAULT 'ALLEGED',
    -- Which engine / rule pack produced this allegation
    source_system       TEXT NOT NULL DEFAULT 'TRANSACTION_MONITORING',
    rule_ids            TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    risk_score          NUMERIC(6,3),
    trigger_summary     TEXT,
    trigger_facts       JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- e.g. {"window_days": 45, "aggregate_usd": 890000, "velocity": "HIGH"}
    is_primary          BOOLEAN NOT NULL DEFAULT FALSE,
    superseded_by_id    UUID REFERENCES case_scenarios(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_case_scenarios_case_code_version
    ON case_scenarios (case_id, scenario_code, (COALESCE(scenario_version, '')));

CREATE INDEX IF NOT EXISTS idx_case_scenarios_case ON case_scenarios (case_id);
CREATE INDEX IF NOT EXISTS idx_case_scenarios_status ON case_scenarios (case_id, status);
CREATE INDEX IF NOT EXISTS idx_case_scenarios_code ON case_scenarios (scenario_code);
CREATE INDEX IF NOT EXISTS idx_case_scenarios_facts ON case_scenarios USING gin (trigger_facts jsonb_path_ops);

CREATE OR REPLACE FUNCTION aml.touch_case_scenarios_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_case_scenarios_updated_at ON case_scenarios;
CREATE TRIGGER trg_case_scenarios_updated_at
    BEFORE UPDATE ON case_scenarios
    FOR EACH ROW EXECUTE FUNCTION aml.touch_case_scenarios_updated_at();

-- -----------------------------------------------------------------------------
-- Transactions ledger for the case
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS case_transactions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id                 UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    -- Stable id from core banking / card / wire system (unique per case)
    external_transaction_id TEXT NOT NULL,
    booked_at               TIMESTAMPTZ NOT NULL,
    amount                  NUMERIC(20,4) NOT NULL,
    currency                CHAR(3) NOT NULL,
    direction               transaction_direction NOT NULL,
    payment_channel         payment_channel NOT NULL,
    product_category        product_category NOT NULL DEFAULT 'UNKNOWN',
    -- Subject-centric party ids/names (align with cases.subject_party_id or case_parties)
    counterparty_name       TEXT,
    counterparty_external_id TEXT,
    counterparty_country    CHAR(2),
    -- Polymorphic payload: see comment block at end of file for examples
    channel_details         JSONB NOT NULL DEFAULT '{}'::jsonb,
    mcc                     TEXT,
    merchant_name           TEXT,
    narrative               TEXT,
    raw_payload             JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (case_id, external_transaction_id)
);

CREATE INDEX IF NOT EXISTS idx_case_txn_case_booked ON case_transactions (case_id, booked_at DESC);
CREATE INDEX IF NOT EXISTS idx_case_txn_channel ON case_transactions (case_id, payment_channel);
CREATE INDEX IF NOT EXISTS idx_case_txn_product ON case_transactions (case_id, product_category);
CREATE INDEX IF NOT EXISTS idx_case_txn_counterparty ON case_transactions (counterparty_external_id);
CREATE INDEX IF NOT EXISTS idx_case_txn_details ON case_transactions USING gin (channel_details jsonb_path_ops);

-- -----------------------------------------------------------------------------
-- Many-to-many: transactions <-> scenarios
-- -----------------------------------------------------------------------------
-- One row per (transaction, scenario) pair. Composite PK prevents duplicates.
-- link_role / weight / notes optional: e.g. PRIMARY_DRIVER vs CORROBORATING,
-- or a normalized contribution score for model explainability.
CREATE TABLE IF NOT EXISTS case_transaction_scenario_links (
    transaction_id  UUID NOT NULL REFERENCES case_transactions(id) ON DELETE CASCADE,
    scenario_id     UUID NOT NULL REFERENCES case_scenarios(id) ON DELETE CASCADE,
    link_role       TEXT NOT NULL DEFAULT 'SUPPORTS',
    weight          NUMERIC(5,4),
    notes           TEXT,
    PRIMARY KEY (transaction_id, scenario_id)
);

-- Scenario-centric lookups: “all transactions tied to this scenario”
CREATE INDEX IF NOT EXISTS idx_txn_scenario_scenario ON case_transaction_scenario_links (scenario_id);
-- Transaction-centric lookups: covered by PRIMARY KEY (transaction_id, scenario_id)

CREATE OR REPLACE FUNCTION aml.enforce_txn_scenario_same_case() RETURNS trigger AS $$
DECLARE
    txn_case UUID;
    scen_case UUID;
BEGIN
    SELECT case_id INTO txn_case FROM aml.case_transactions WHERE id = NEW.transaction_id;
    SELECT case_id INTO scen_case FROM aml.case_scenarios WHERE id = NEW.scenario_id;
    IF txn_case IS DISTINCT FROM scen_case THEN
        RAISE EXCEPTION 'transaction % and scenario % must belong to the same case',
            NEW.transaction_id, NEW.scenario_id USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_txn_scenario_same_case ON case_transaction_scenario_links;
CREATE TRIGGER trg_txn_scenario_same_case
    BEFORE INSERT OR UPDATE ON case_transaction_scenario_links
    FOR EACH ROW EXECUTE FUNCTION aml.enforce_txn_scenario_same_case();

-- -----------------------------------------------------------------------------
-- FK from catalog to case_scenarios is optional; scenario_code is loose coupling
-- -----------------------------------------------------------------------------
-- Example channel_details shapes (documentary — not enforced by DB):
--
-- DIGITAL_BANKING (retail customer moving money in the mobile app):
--   {"session_id":"...","device_id":"...","beneficiary_id":"...","xfer_type":"INTERNAL"}
--
-- CARD_POS / CARD_NOT_PRESENT (retail customer card; MCC describes merchant, not “retail sector”):
--   {"network":"VISA","card_product":"CONSUMER_DEBIT","entry_mode":"CHIP",
--    "mcc":"5411","merchant_name":"...","arn":"...","last4":"4242","3ds":"Y"}
--
-- WIRE / ACH / BILL_PAY:
--   {"imad":"...","beneficiary_bank":"XXX","purpose_code":"TRADE",
--    "ach_sec_code":"CCD","biller_id":"UTILCO","invoice_ref":"INV-9","iban_hint":"**1234"}

-- =============================================================================
-- End of additive schema
-- =============================================================================
