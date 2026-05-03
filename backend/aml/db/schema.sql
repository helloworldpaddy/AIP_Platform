-- =============================================================================
-- AML Investigation Agentic Platform — Postgres Schema
-- =============================================================================
-- Design tenets:
--   1. Traceability:  agent_runs.reasoning + audit_trail (hash-chained, append-only)
--   2. Explainability: evidence_ledger is the single source of truth for citations
--   3. Idempotency:   (case_id, agent_name, idempotency_key) is unique; resume on retry
--   4. Human-in-loop: human_gates block downstream agents until APPROVED
--   5. Immutability:  cases.locked / narratives.locked enforced by trigger
--   6. Bank-grade:    every mutating event mirrored into audit_trail with sha256 chain
--
-- Companion tables already provisioned in this repo:
--   * documents (pgvector) — Policy / Grounded-Rules RAG (see agents/rag_agent/db/schema.sql)
-- This file is additive: run AFTER the base RAG schema, in the SAME database.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid(), digest()
CREATE EXTENSION IF NOT EXISTS "vector";     -- pgvector (re-asserted; idempotent)

CREATE SCHEMA IF NOT EXISTS aml;
SET search_path TO aml, public;

-- -----------------------------------------------------------------------------
-- Enumerated types
-- -----------------------------------------------------------------------------
DO $$ BEGIN
    CREATE TYPE case_status AS ENUM (
        'OPEN', 'IN_PROGRESS', 'AWAITING_REVIEW',
        'ESCALATED', 'SUBMITTED', 'CLOSED'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE case_stage AS ENUM (
        'INTAKE',
        'INITIAL_ASSESSMENT',
        'TRANSACTION_ENRICHMENT',
        'DUE_DILIGENCE',
        'CASE_ANALYSIS',
        'COMPLETED'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE case_priority AS ENUM ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE line_of_business AS ENUM (
        'CARDS',            -- card issuing / acquiring LOB (bank-defined)
        'RETAIL_BANKING',   -- consumer / mass-market banking (deposits, lending, …)
        'SERVICES'          -- payments ops, treasury, trade, institutional services, etc.
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE agent_name AS ENUM (
        'INITIAL_ASSESSMENT',
        'TRANSACTION_ENRICHMENT',
        'DUE_DILIGENCE',
        'CASE_ANALYSIS'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE agent_run_status AS ENUM (
        'PENDING',           -- queued, not yet started
        'RUNNING',           -- in flight
        'AWAITING_REVIEW',   -- finished but blocked on a human gate
        'APPROVED',          -- analyst signed off (un-modified)
        'MODIFIED',          -- analyst edited the output (override)
        'REJECTED',          -- analyst rejected, will be re-run
        'FAILED',            -- terminal error after retries
        'COMPLETED'          -- auto-advance (no gate required)
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE evidence_type AS ENUM (
        'KYC_RECORD',
        'TRANSACTION',
        'GRAPH_RELATION',     -- Neo4j hop / link
        'EXTERNAL_SEARCH',    -- web / news
        'POLICY_RULE',        -- pgvector RAG hit
        'SANCTIONS_HIT',
        'ADVERSE_MEDIA',
        'INTERNAL_NOTE'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE classification AS ENUM ('FALSE_POSITIVE', 'ESCALATE', 'SAR');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE gate_status AS ENUM ('OPEN_REQUIRED', 'APPROVED', 'REJECTED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE actor_type AS ENUM ('AGENT', 'ANALYST', 'SYSTEM');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE audit_event_type AS ENUM (
        'CASE_CREATED',
        'CASE_STATUS_CHANGED',
        'CASE_STAGE_ADVANCED',
        'AGENT_STARTED',
        'AGENT_REASONING',
        'AGENT_COMPLETED',
        'AGENT_FAILED',
        'AGENT_RETRIED',
        'EVIDENCE_RECORDED',
        'GATE_OPENED',
        'GATE_APPROVED',
        'GATE_REJECTED',
        'HUMAN_OVERRIDE',
        'NARRATIVE_DRAFTED',
        'NARRATIVE_SUBMITTED',
        'RECORD_LOCKED'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE party_type AS ENUM ('INDIVIDUAL', 'CORPORATE', 'TRUST', 'OTHER');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- -----------------------------------------------------------------------------
-- Core: cases
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cases (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    case_number         TEXT         NOT NULL UNIQUE,             -- e.g. AML-2026-000123
    alert_type          TEXT         NOT NULL,                    -- e.g. TRANSACTION_MONITORING
    alert_payload       JSONB        NOT NULL,                    -- raw alert from upstream
    subject_party_id    TEXT         NOT NULL,                    -- the customer being investigated
    subject_party_name  TEXT         NOT NULL,
    -- Exactly one LOB per case at intake (Cards, Retail banking, or Services).
    line_of_business    line_of_business NOT NULL DEFAULT 'RETAIL_BANKING',
    status              case_status  NOT NULL DEFAULT 'OPEN',
    current_stage       case_stage   NOT NULL DEFAULT 'INTAKE',
    priority            case_priority NOT NULL DEFAULT 'MEDIUM',
    assigned_analyst_id TEXT,
    locked              BOOLEAN      NOT NULL DEFAULT FALSE,      -- set when narrative submitted
    locked_at           TIMESTAMPTZ,
    locked_by           TEXT,
    metadata            JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    created_by          TEXT         NOT NULL,
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_by          TEXT
);

CREATE INDEX IF NOT EXISTS idx_cases_status          ON cases (status);
CREATE INDEX IF NOT EXISTS idx_cases_stage           ON cases (current_stage);
CREATE INDEX IF NOT EXISTS idx_cases_assigned        ON cases (assigned_analyst_id);
CREATE INDEX IF NOT EXISTS idx_cases_created_at      ON cases (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cases_subject         ON cases (subject_party_id);
CREATE INDEX IF NOT EXISTS idx_cases_line_of_business ON cases (line_of_business);
CREATE INDEX IF NOT EXISTS idx_cases_alert_payload   ON cases USING gin (alert_payload jsonb_path_ops);

-- -----------------------------------------------------------------------------
-- Agent runs (idempotent, resumable)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_runs (
    id                 UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id            UUID             NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    agent              agent_name       NOT NULL,
    attempt            INTEGER          NOT NULL DEFAULT 1,
    -- The idempotency_key lets a client safely re-trigger an agent without creating
    -- duplicate runs.  Convention: sha256(case_id || agent || logical_input_version).
    idempotency_key    TEXT             NOT NULL,
    status             agent_run_status NOT NULL DEFAULT 'PENDING',
    input_payload      JSONB            NOT NULL DEFAULT '{}'::jsonb,
    output_payload     JSONB,                                   -- structured result
    reasoning          TEXT,                                    -- Chain-of-Thought (full)
    reasoning_summary  TEXT,                                    -- short, UI-friendly
    error              TEXT,
    model_name         TEXT,
    tokens             JSONB,                                   -- {prompt, completion, total}
    duration_ms        INTEGER,
    -- HITL override tracking
    human_modified     BOOLEAN          NOT NULL DEFAULT FALSE,
    human_modified_at  TIMESTAMPTZ,
    human_modified_by  TEXT,
    human_diff         JSONB,                                   -- jsonpatch of analyst edits
    approved_at        TIMESTAMPTZ,
    approved_by        TEXT,
    started_at         TIMESTAMPTZ,
    completed_at       TIMESTAMPTZ,
    created_at         TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    UNIQUE (case_id, agent, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_case       ON agent_runs (case_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_case_agent ON agent_runs (case_id, agent);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status     ON agent_runs (status);

-- -----------------------------------------------------------------------------
-- Evidence ledger — every fact an agent uses MUST be persisted here first
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS evidence_ledger (
    id                 UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id            UUID            NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    agent_run_id       UUID            REFERENCES agent_runs(id) ON DELETE SET NULL,
    evidence_type      evidence_type   NOT NULL,
    source_system      TEXT            NOT NULL,           -- e.g. 'core_banking', 'neo4j', 'google_search'
    source_uri         TEXT,                               -- URL / doc:// / neo4j://node/...
    title              TEXT            NOT NULL,
    content            TEXT            NOT NULL,           -- the textual evidence
    structured_data    JSONB           NOT NULL DEFAULT '{}'::jsonb,
    -- sha256 of canonical content; supports dedup and tamper detection
    content_hash       TEXT            NOT NULL,
    confidence_score   NUMERIC(4,3),                       -- 0.000 .. 1.000
    contains_pii       BOOLEAN         NOT NULL DEFAULT FALSE,
    retrieved_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by         TEXT            NOT NULL,           -- agent or analyst id
    UNIQUE (case_id, content_hash)                         -- idempotent re-ingest
);

CREATE INDEX IF NOT EXISTS idx_evidence_case        ON evidence_ledger (case_id);
CREATE INDEX IF NOT EXISTS idx_evidence_type        ON evidence_ledger (evidence_type);
CREATE INDEX IF NOT EXISTS idx_evidence_agent_run   ON evidence_ledger (agent_run_id);
CREATE INDEX IF NOT EXISTS idx_evidence_structured  ON evidence_ledger USING gin (structured_data jsonb_path_ops);

-- -----------------------------------------------------------------------------
-- Case parties — output of the Transaction Enrichment agent
-- These are the rows the analyst must "Verify" before Due Diligence may run.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS case_parties (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id             UUID         NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    party_external_id   TEXT         NOT NULL,
    party_name          TEXT         NOT NULL,
    party_type          party_type   NOT NULL DEFAULT 'OTHER',
    relationship        TEXT,                              -- e.g. 'counterparty', 'beneficiary'
    hop_distance        INTEGER      NOT NULL CHECK (hop_distance >= 0),
    risk_indicators     JSONB        NOT NULL DEFAULT '{}'::jsonb,
    source_evidence_ids UUID[]       NOT NULL DEFAULT ARRAY[]::UUID[],
    verified            BOOLEAN      NOT NULL DEFAULT FALSE,
    verified_at         TIMESTAMPTZ,
    verified_by         TEXT,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (case_id, party_external_id, hop_distance)
);

CREATE INDEX IF NOT EXISTS idx_parties_case      ON case_parties (case_id);
CREATE INDEX IF NOT EXISTS idx_parties_verified  ON case_parties (case_id, verified);

-- -----------------------------------------------------------------------------
-- Human-in-the-loop gates — block stage transitions until APPROVED
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS human_gates (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id             UUID         NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    gate_name           TEXT         NOT NULL,             -- e.g. 'PARTIES_VERIFIED'
    blocks_agent        agent_name   NOT NULL,             -- which agent it gates
    status              gate_status  NOT NULL DEFAULT 'OPEN_REQUIRED',
    opened_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    resolved_at         TIMESTAMPTZ,
    resolved_by         TEXT,
    notes               TEXT,
    UNIQUE (case_id, gate_name)
);

CREATE INDEX IF NOT EXISTS idx_gates_case_status ON human_gates (case_id, status);

-- -----------------------------------------------------------------------------
-- Narratives — final case write-up.  Versioned + lockable.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS narratives (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id         UUID            NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    version         INTEGER         NOT NULL DEFAULT 1,
    classification  classification  NOT NULL,
    rationale       TEXT            NOT NULL,
    markdown_body   TEXT            NOT NULL,                       -- with [n] footnotes
    citations       JSONB           NOT NULL DEFAULT '[]'::jsonb,   -- [{footnote:1, evidence_id:UUID}]
    submitted       BOOLEAN         NOT NULL DEFAULT FALSE,
    submitted_at    TIMESTAMPTZ,
    submitted_by    TEXT,
    locked          BOOLEAN         NOT NULL DEFAULT FALSE,
    human_modified  BOOLEAN         NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by      TEXT            NOT NULL,
    UNIQUE (case_id, version)
);

CREATE INDEX IF NOT EXISTS idx_narratives_case      ON narratives (case_id);
CREATE INDEX IF NOT EXISTS idx_narratives_submitted ON narratives (submitted);

-- -----------------------------------------------------------------------------
-- Audit trail — APPEND-ONLY, hash-chained (tamper-evident)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_trail (
    id              BIGSERIAL        PRIMARY KEY,
    case_id         UUID             NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    agent_run_id    UUID             REFERENCES agent_runs(id) ON DELETE SET NULL,
    actor_type      actor_type       NOT NULL,
    actor_id        TEXT             NOT NULL,                  -- agent name or analyst id
    event_type      audit_event_type NOT NULL,
    event_payload   JSONB            NOT NULL DEFAULT '{}'::jsonb,
    reasoning_text  TEXT,                                       -- CoT excerpts
    -- Tamper-evident hash chain.  data_hash = sha256(prev_hash || canonical(row))
    prev_hash       TEXT,
    data_hash       TEXT             NOT NULL,
    created_at      TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_case        ON audit_trail (case_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_event       ON audit_trail (event_type);
CREATE INDEX IF NOT EXISTS idx_audit_agent_run   ON audit_trail (agent_run_id);

-- -----------------------------------------------------------------------------
-- Triggers
-- -----------------------------------------------------------------------------

-- 1) updated_at maintenance
CREATE OR REPLACE FUNCTION aml.touch_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cases_updated_at ON cases;
CREATE TRIGGER trg_cases_updated_at
    BEFORE UPDATE ON cases
    FOR EACH ROW EXECUTE FUNCTION aml.touch_updated_at();

DROP TRIGGER IF EXISTS trg_agent_runs_updated_at ON agent_runs;
CREATE TRIGGER trg_agent_runs_updated_at
    BEFORE UPDATE ON agent_runs
    FOR EACH ROW EXECUTE FUNCTION aml.touch_updated_at();

-- 2) Immutability — once a case is locked, all mutations are rejected
CREATE OR REPLACE FUNCTION aml.enforce_case_lock() RETURNS trigger AS $$
BEGIN
    IF (TG_OP = 'UPDATE' AND OLD.locked = TRUE) THEN
        -- allow only the unlock-audit metadata fields to change is intentionally NOT
        -- supported: locked records are fully immutable.
        RAISE EXCEPTION 'Case % is locked; further updates are forbidden', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cases_lock_guard ON cases;
CREATE TRIGGER trg_cases_lock_guard
    BEFORE UPDATE OR DELETE ON cases
    FOR EACH ROW EXECUTE FUNCTION aml.enforce_case_lock();

-- 3) Narrative immutability — once submitted+locked, no edits or deletes
CREATE OR REPLACE FUNCTION aml.enforce_narrative_lock() RETURNS trigger AS $$
BEGIN
    IF (TG_OP IN ('UPDATE','DELETE') AND OLD.locked = TRUE) THEN
        RAISE EXCEPTION 'Narrative % is locked (submitted); further changes forbidden', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_narratives_lock_guard ON narratives;
CREATE TRIGGER trg_narratives_lock_guard
    BEFORE UPDATE OR DELETE ON narratives
    FOR EACH ROW EXECUTE FUNCTION aml.enforce_narrative_lock();

-- 4) Audit trail append-only + hash chain
CREATE OR REPLACE FUNCTION aml.audit_chain_insert() RETURNS trigger AS $$
DECLARE
    v_prev_hash TEXT;
    v_canonical TEXT;
BEGIN
    SELECT data_hash INTO v_prev_hash
      FROM aml.audit_trail
     WHERE case_id = NEW.case_id
     ORDER BY id DESC
     LIMIT 1;

    NEW.prev_hash := v_prev_hash;
    -- Canonical form: stable concatenation of the chained fields.
    v_canonical := COALESCE(v_prev_hash, '') || '|' ||
                   NEW.case_id::text || '|' ||
                   NEW.actor_type::text || '|' ||
                   NEW.actor_id || '|' ||
                   NEW.event_type::text || '|' ||
                   COALESCE(NEW.event_payload::text, '{}') || '|' ||
                   COALESCE(NEW.reasoning_text, '');
    NEW.data_hash := encode(digest(v_canonical, 'sha256'), 'hex');
    RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_chain ON audit_trail;
CREATE TRIGGER trg_audit_chain
    BEFORE INSERT ON audit_trail
    FOR EACH ROW EXECUTE FUNCTION aml.audit_chain_insert();

CREATE OR REPLACE FUNCTION aml.audit_block_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_trail is append-only (% blocked)', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_no_update ON audit_trail;
CREATE TRIGGER trg_audit_no_update
    BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_trail
    FOR EACH STATEMENT EXECUTE FUNCTION aml.audit_block_mutation();

-- -----------------------------------------------------------------------------
-- Convenience views
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_case_summary AS
SELECT
    c.id,
    c.case_number,
    c.status,
    c.current_stage,
    c.priority,
    c.line_of_business,
    c.assigned_analyst_id,
    c.subject_party_name,
    (SELECT COUNT(*) FROM agent_runs ar  WHERE ar.case_id  = c.id) AS agent_runs_count,
    (SELECT COUNT(*) FROM evidence_ledger e WHERE e.case_id  = c.id) AS evidence_count,
    (SELECT COUNT(*) FROM human_gates g
       WHERE g.case_id = c.id AND g.status = 'OPEN_REQUIRED')        AS open_gates,
    c.created_at,
    c.updated_at
FROM cases c;

-- =============================================================================
-- End of schema
-- =============================================================================
