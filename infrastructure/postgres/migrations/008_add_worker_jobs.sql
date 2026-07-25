BEGIN;

CREATE TABLE IF NOT EXISTS worker_jobs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_type TEXT NOT NULL
        CONSTRAINT worker_jobs_type_valid
        CHECK (
            job_type IN (
                'eligibility_segmentation',
                'embeddings',
                'topics',
                'themes'
            )
        ),
    original_input_id BIGINT NOT NULL
        REFERENCES original_inputs (id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending'
        CONSTRAINT worker_jobs_status_valid
        CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0
        CONSTRAINT worker_jobs_attempts_nonnegative
        CHECK (attempts >= 0),
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked_at TIMESTAMPTZ,
    locked_by TEXT,
    last_error TEXT,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT worker_jobs_input_stage_unique
        UNIQUE (job_type, original_input_id),
    CONSTRAINT worker_jobs_lock_consistent
        CHECK (
            (status = 'processing')
            = (locked_at IS NOT NULL AND locked_by IS NOT NULL)
        )
);

CREATE INDEX IF NOT EXISTS idx_worker_jobs_available
    ON worker_jobs (job_type, available_at, id)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_worker_jobs_expired
    ON worker_jobs (job_type, locked_at, id)
    WHERE status = 'processing';

CREATE OR REPLACE FUNCTION enqueue_original_input_job()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    next_job_type TEXT;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF NEW.status IS NOT DISTINCT FROM OLD.status THEN
            RETURN NEW;
        END IF;
    END IF;

    next_job_type := CASE NEW.status
        WHEN 'new' THEN 'eligibility_segmentation'
        WHEN 'ready_for_embedding' THEN 'embeddings'
        WHEN 'ready_for_analysis' THEN 'topics'
        WHEN 'completed' THEN 'themes'
        ELSE NULL
    END;

    IF next_job_type IS NOT NULL THEN
        INSERT INTO worker_jobs (job_type, original_input_id)
        VALUES (next_job_type, NEW.id)
        ON CONFLICT (job_type, original_input_id) DO UPDATE
        SET
            status = 'pending',
            attempts = 0,
            available_at = CURRENT_TIMESTAMP,
            locked_at = NULL,
            locked_by = NULL,
            last_error = NULL,
            completed_at = NULL,
            updated_at = CURRENT_TIMESTAMP;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS original_inputs_enqueue_job ON original_inputs;

CREATE TRIGGER original_inputs_enqueue_job
AFTER INSERT OR UPDATE OF status ON original_inputs
FOR EACH ROW
EXECUTE FUNCTION enqueue_original_input_job();

INSERT INTO worker_jobs (job_type, original_input_id)
SELECT
    CASE status
        WHEN 'new' THEN 'eligibility_segmentation'
        WHEN 'ready_for_embedding' THEN 'embeddings'
        WHEN 'ready_for_analysis' THEN 'topics'
        WHEN 'completed' THEN 'themes'
    END,
    id
FROM original_inputs
WHERE status IN (
    'new',
    'ready_for_embedding',
    'ready_for_analysis',
    'completed'
)
ON CONFLICT (job_type, original_input_id) DO NOTHING;

COMMIT;
