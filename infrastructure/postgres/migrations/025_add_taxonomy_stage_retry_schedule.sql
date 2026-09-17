BEGIN;

ALTER TABLE taxonomy_run_stages
    ADD COLUMN available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;

DROP INDEX idx_taxonomy_run_stages_claimable;
CREATE INDEX idx_taxonomy_run_stages_claimable
    ON taxonomy_run_stages (stage, available_at, lease_expires_at, taxonomy_run_id)
    WHERE status IN ('pending', 'running');

-- A recoverable failure releases its lease back to pending.  Keep the other
-- transition and immutable-identity protections introduced in migration 024.
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
        (OLD.status = 'running' AND NEW.status IN ('running', 'pending', 'completed', 'failed', 'cancelled')) OR
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

COMMIT;
