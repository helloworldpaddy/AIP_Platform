-- Refresh aml.v_case_summary after cases.line_of_business (or related schema) changes.
-- Safe to run anytime: CREATE OR REPLACE VIEW is idempotent.
-- Usage (Docker): docker exec -i aml-postgres psql -U raguser -d ragdb -v ON_ERROR_STOP=1 < backend/aml/db/patches/refresh_v_case_summary.sql

SET search_path TO aml, public;

-- Replacing an older definition without line_of_business: REPLACE alone may fail
-- ("cannot change name of view column"). Drop then create.
DROP VIEW IF EXISTS v_case_summary CASCADE;

CREATE VIEW v_case_summary AS
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
