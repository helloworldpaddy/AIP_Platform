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
-- 3) Payment diversity (Retail, Cards, Services, product-specific attributes)
--    is modeled as:
--      * payment_channel  — how value moved (POS, e-com, card auth, wire, …)
--      * product_category — coarse retail / card / services taxonomy
--      * channel_details  — JSONB for rail-specific fields (MCC, entry mode,
--        merchant id, card product, biller id, invoice ref, etc.)
--
-- Relationship sketch
-- -------------------
--   cases 1──* case_scenarios
--   cases 1──* case_transactions
--   case_scenarios *──* case_transactions  (optional link table; a txn may
--     support several scenarios or none if loaded for context only)
-- =============================================================================

SET search_path TO aml, public;

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
        -- Retail (goods / face-to-face or merchant-present not strictly card)
        'RETAIL_POS',           -- brick & mortar POS
        'RETAIL_ECOM',          -- merchant e-commerce checkout
        'RETAIL_MOTO',          -- mail order / telephone order
        -- Cards (payment card rails)
        'CARD_ATM',
        'CARD_POS_CHIP',        -- EMV chip at POS
        'CARD_POS_CONTACTLESS',
        'CARD_ECOM',            -- CNP card not split further
        'CARD_P2P',             -- card-based push to consumer
        -- Account / service rails (non-card retail)
        'SERVICE_WIRE',
        'SERVICE_ACH',
        'SERVICE_SEPA',
        'SERVICE_RTP',          -- faster / instant payments
        'SERVICE_BILL_PAY',     -- biller / aggregator
        'SERVICE_MOBILE_MONEY',
        'SERVICE_CRYPTO_FIAT',  -- on/off ramp if you track it
        'OTHER'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE product_category AS ENUM (
        -- Retail-oriented
        'RETAIL_HARDLINES',
        'RETAIL_SOFTLINES',
        'RETAIL_GROCERY',
        'RETAIL_DIGITAL_GOODS',
        'RETAIL_MRP_GOODS',     -- e.g. importer / wholesaler SKUs
        -- Card-oriented (product/program level)
        'CARD_CONSUMER_CREDIT',
        'CARD_CONSUMER_DEBIT',
        'CARD_COMMERCIAL',
        'CARD_PREPAID',
        -- Services & non-goods
        'SERVICES_PROFESSIONAL',
        'SERVICES_FREIGHT',
        'SERVICES_UTILITIES',
        'SERVICES_SAAS',
        'SERVICES_FX_REMITTANCE',
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
    domain          TEXT NOT NULL,  -- e.g. 'RETAIL', 'CARDS', 'SERVICES', 'CROSS_BORDER'
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
-- Many-to-many: which transactions substantiate which scenarios (optional but useful)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS case_transaction_scenario_links (
    transaction_id  UUID NOT NULL REFERENCES case_transactions(id) ON DELETE CASCADE,
    scenario_id     UUID NOT NULL REFERENCES case_scenarios(id) ON DELETE CASCADE,
    link_role       TEXT NOT NULL DEFAULT 'SUPPORTS',
    weight          NUMERIC(5,4),
    notes           TEXT,
    PRIMARY KEY (transaction_id, scenario_id)
);

CREATE INDEX IF NOT EXISTS idx_txn_scenario_scenario ON case_transaction_scenario_links (scenario_id);

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
-- RETAIL_POS / RETAIL_ECOM:
--   {"store_id":"S-1001","register_id":"3","mcc":"5311","sku_family":"apparel",
--    "channel":"ECOM","device_id":"term-7788"}
--
-- CARD_* :
--   {"network":"VISA","card_product":"SIGNATURE","entry_mode":"CHIP",
--    "auth_code":"123456","arn":"...","last4":"4242","3ds":"Y"}
--
-- SERVICE_WIRE / ACH / BILL_PAY:
--   {"imad":"...","beneficiary_bank":"XXX","purpose_code":"TRADE",
--    "biller_id":"UTILCO","invoice_ref":"INV-9","iban_hint":"**1234"}

-- =============================================================================
-- End of additive schema
-- =============================================================================
