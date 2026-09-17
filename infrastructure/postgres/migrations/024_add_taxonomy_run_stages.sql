BEGIN;

-- A run has one durable record for every batch stage.  Later workers claim
-- and renew leases through these rows; this foundation deliberately does not
-- infer lifecycle progress from candidate-row presence.
CREATE TABLE taxonomy_run_stages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    taxonomy_run_id BIGINT NOT NULL REFERENCES taxonomy_runs (id) ON DELETE RESTRICT,
    stage TEXT NOT NULL CHECK (stage IN (
        'snapshot', 'clustering', 'topic_naming', 'theme_inference',
        'theme_reconciliation', 'quality', 'ready_for_publication'
    )),
    attempt INTEGER NOT NULL DEFAULT 0 CHECK (attempt >= 0),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'running', 'completed', 'failed', 'cancelled'
    )),
    lease_owner TEXT CHECK (lease_owner IS NULL OR (
        btrim(lease_owner) <> '' AND char_length(lease_owner) <= 200
    )),
    lease_expires_at TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_class TEXT CHECK (error_class IS NULL OR (
        error_class ~ '^[a-z][a-z0-9_]{0,79}$'
    )),
    stage_input_sha256 TEXT CHECK (stage_input_sha256 IS NULL OR stage_input_sha256 ~ '^[0-9a-f]{64}$'),
    stage_output_sha256 TEXT CHECK (stage_output_sha256 IS NULL OR stage_output_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (taxonomy_run_id, stage),
    CHECK ((status = 'running') = (
        lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL AND heartbeat_at IS NOT NULL
    )),
    CHECK ((status = 'completed') = (completed_at IS NOT NULL)),
    CHECK ((status = 'failed') = (error_class IS NOT NULL))
);

CREATE INDEX idx_taxonomy_run_stages_claimable
    ON taxonomy_run_stages (stage, status, lease_expires_at, taxonomy_run_id)
    WHERE status IN ('pending', 'running', 'failed');

-- Candidate runs created before this migration have no trustworthy per-stage
-- history.  Preserve their terminal lifecycle safely, and make an old
-- in-progress run explicitly retryable instead of inventing a lease owner.
INSERT INTO taxonomy_run_stages (
    taxonomy_run_id, stage, attempt, status, completed_at, error_class,
    stage_output_sha256
)
SELECT
    runs.id,
    stages.stage,
    CASE
        WHEN stages.stage = 'snapshot' THEN 1
        WHEN runs.status IN ('ready_for_review', 'published', 'rejected', 'failed', 'running') THEN 1
        ELSE 0
    END,
    CASE
        WHEN stages.stage = 'snapshot' THEN 'completed'
        WHEN runs.status IN ('ready_for_review', 'published') THEN 'completed'
        WHEN runs.status = 'rejected' THEN 'cancelled'
        WHEN runs.status IN ('failed', 'running') THEN 'failed'
        ELSE 'pending'
    END,
    CASE
        WHEN stages.stage = 'snapshot' THEN COALESCE(runs.started_at, runs.created_at)
        WHEN runs.status IN ('ready_for_review', 'published') THEN COALESCE(runs.completed_at, runs.updated_at)
        ELSE NULL
    END,
    CASE WHEN stages.stage <> 'snapshot' AND runs.status IN ('failed', 'running') THEN 'legacy_state' END,
    CASE WHEN stages.stage = 'snapshot' THEN runs.source_snapshot_sha256 END
FROM taxonomy_runs AS runs
CROSS JOIN (VALUES
    ('snapshot'), ('clustering'), ('topic_naming'), ('theme_inference'),
    ('theme_reconciliation'), ('quality'), ('ready_for_publication')
) AS stages(stage)
ON CONFLICT (taxonomy_run_id, stage) DO NOTHING;

CREATE OR REPLACE FUNCTION protect_taxonomy_run_stage() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.taxonomy_run_id IS DISTINCT FROM OLD.taxonomy_run_id
       OR NEW.stage IS DISTINCT FROM OLD.stage
       OR NEW.stage_input_sha256 IS DISTINCT FROM OLD.stage_input_sha256 THEN
        RAISE EXCEPTION 'taxonomy run stage identity and input are immutable';
    END IF;
    IF OLD.status IN ('completed', 'cancelled') THEN
        RAISE EXCEPTION 'terminal taxonomy run stage is immutable';
    END IF;
    IF NOT (
        (OLD.status = 'pending' AND NEW.status IN ('pending', 'running', 'cancelled')) OR
        (OLD.status = 'running' AND NEW.status IN ('running', 'completed', 'failed', 'cancelled')) OR
        (OLD.status = 'failed' AND NEW.status IN ('failed', 'pending', 'cancelled'))
    ) THEN
        RAISE EXCEPTION 'invalid taxonomy run stage transition: % to %', OLD.status, NEW.status;
    END IF;
    IF NEW.attempt < OLD.attempt OR NEW.attempt > OLD.attempt + 1 THEN
        RAISE EXCEPTION 'taxonomy run stage attempt must advance by at most one';
    END IF;
    NEW.updated_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

CREATE TRIGGER taxonomy_run_stages_protected
BEFORE UPDATE ON taxonomy_run_stages
FOR EACH ROW EXECUTE FUNCTION protect_taxonomy_run_stage();

COMMIT;
