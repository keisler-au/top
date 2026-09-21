BEGIN;

-- Reconcile candidates stranded by the old stage-only failure path. Preserve
-- immutable stage output, model audits, and release attestations; never retry
-- or publish as a side effect of upgrading.
UPDATE taxonomy_runs run SET status='failed', error_summary='candidate_failed'
WHERE run.status IN ('pending','running') AND EXISTS (
    SELECT 1 FROM taxonomy_run_stages stage
    WHERE stage.taxonomy_run_id=run.id AND stage.status IN ('failed','cancelled')
);
UPDATE taxonomy_run_jobs job SET status='failed', locked_at=NULL, locked_by=NULL,
    last_error='candidate_failed', updated_at=CURRENT_TIMESTAMP
WHERE job.status IN ('pending','processing') AND EXISTS (
    SELECT 1 FROM taxonomy_runs run WHERE run.id=job.taxonomy_run_id AND run.status='failed'
);

CREATE OR REPLACE FUNCTION enqueue_taxonomy_run(candidate_run_id BIGINT)
RETURNS taxonomy_run_jobs LANGUAGE plpgsql AS $$
DECLARE job taxonomy_run_jobs;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM taxonomy_runs WHERE id=candidate_run_id AND status IN ('pending','failed') FOR UPDATE) THEN
        RAISE EXCEPTION 'taxonomy run is not eligible for scheduling';
    END IF;
    IF EXISTS (SELECT 1 FROM taxonomy_run_stages WHERE taxonomy_run_id=candidate_run_id AND status='cancelled') THEN
        RAISE EXCEPTION 'cancelled taxonomy stages require a new candidate';
    END IF;
    INSERT INTO taxonomy_run_jobs(taxonomy_run_id) VALUES(candidate_run_id)
    ON CONFLICT (taxonomy_run_id) DO UPDATE
        SET status='pending', available_at=CURRENT_TIMESTAMP, locked_at=NULL,
            locked_by=NULL, last_error=NULL, updated_at=CURRENT_TIMESTAMP
        WHERE taxonomy_run_jobs.status IN ('failed','cancelled')
    RETURNING * INTO job;
    IF NOT FOUND THEN RAISE EXCEPTION 'taxonomy run is already scheduled or completed'; END IF;
    UPDATE taxonomy_run_stages SET status='pending', error_class=NULL,
        lease_owner=NULL, lease_expires_at=NULL, heartbeat_at=NULL,
        available_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
    WHERE taxonomy_run_id=candidate_run_id AND status='failed';
    RETURN job;
END;
$$;
COMMIT;
