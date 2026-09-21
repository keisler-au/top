BEGIN;

-- The checkpoint is deliberately small: it is a coordination record, not a
-- second source of taxonomy provenance.  Snapshot provenance remains owned by
-- taxonomy_runs and taxonomy_run_evidence.
CREATE TABLE taxonomy_automation_checkpoints (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    policy_version TEXT NOT NULL CHECK (btrim(policy_version) <> ''),
    last_considered_cutoff TIMESTAMPTZ,
    last_published_cutoff TIMESTAMPTZ,
    last_failure_code TEXT CHECK (last_failure_code IS NULL OR last_failure_code ~ '^[a-z][a-z0-9_]{0,79}$'),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- A decision is made before snapshot creation so a process crash can be
-- replayed with the same idempotency key.  No text, vectors, or credentials
-- belong in this audit trail.
CREATE TABLE taxonomy_automation_decisions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE CHECK (btrim(idempotency_key) <> ''),
    policy_version TEXT NOT NULL CHECK (btrim(policy_version) <> ''),
    evidence_cutoff TIMESTAMPTZ NOT NULL,
    predecessor_cutoff TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('reserved', 'snapshotted', 'failed', 'manual')),
    failure_code TEXT CHECK (failure_code IS NULL OR failure_code ~ '^[a-z][a-z0-9_]{0,79}$'),
    taxonomy_run_id BIGINT UNIQUE REFERENCES taxonomy_runs(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX taxonomy_automation_decisions_pending
    ON taxonomy_automation_decisions (status, evidence_cutoff DESC);

CREATE OR REPLACE FUNCTION protect_taxonomy_automation_decision() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
       OR NEW.policy_version IS DISTINCT FROM OLD.policy_version
       OR NEW.evidence_cutoff IS DISTINCT FROM OLD.evidence_cutoff
       OR NEW.predecessor_cutoff IS DISTINCT FROM OLD.predecessor_cutoff THEN
        RAISE EXCEPTION 'taxonomy automation decision identity is immutable';
    END IF;
    IF OLD.status = 'manual' AND NEW.status IS DISTINCT FROM OLD.status THEN
        RAISE EXCEPTION 'terminal taxonomy automation decision is immutable';
    END IF;
    NEW.updated_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;
CREATE TRIGGER taxonomy_automation_decisions_protected
BEFORE UPDATE ON taxonomy_automation_decisions
FOR EACH ROW EXECUTE FUNCTION protect_taxonomy_automation_decision();

COMMIT;
