BEGIN;

CREATE TABLE taxonomy_run_jobs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    taxonomy_run_id BIGINT NOT NULL REFERENCES taxonomy_runs (id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked_at TIMESTAMPTZ,
    locked_by TEXT,
    last_error TEXT,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((status = 'processing') = (locked_at IS NOT NULL AND locked_by IS NOT NULL)),
    CHECK ((status = 'completed') = (completed_at IS NOT NULL)),
    UNIQUE (taxonomy_run_id)
);
CREATE UNIQUE INDEX taxonomy_run_jobs_one_active
    ON taxonomy_run_jobs ((TRUE)) WHERE status IN ('pending', 'processing');
CREATE INDEX idx_taxonomy_run_jobs_available
    ON taxonomy_run_jobs (available_at, id) WHERE status = 'pending';

CREATE OR REPLACE FUNCTION enqueue_taxonomy_run(candidate_run_id BIGINT)
RETURNS taxonomy_run_jobs LANGUAGE plpgsql AS $$
DECLARE job taxonomy_run_jobs;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM taxonomy_runs WHERE id = candidate_run_id AND status IN ('pending', 'failed')) THEN
        RAISE EXCEPTION 'taxonomy run is not eligible for scheduling';
    END IF;
    INSERT INTO taxonomy_run_jobs (taxonomy_run_id)
    VALUES (candidate_run_id)
    ON CONFLICT (taxonomy_run_id) DO UPDATE
      SET status = 'pending', available_at = CURRENT_TIMESTAMP, locked_at = NULL,
          locked_by = NULL, last_error = NULL, updated_at = CURRENT_TIMESTAMP
      WHERE taxonomy_run_jobs.status IN ('failed', 'cancelled')
    RETURNING * INTO job;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'taxonomy run is already scheduled or completed';
    END IF;
    RETURN job;
END;
$$;
COMMIT;
