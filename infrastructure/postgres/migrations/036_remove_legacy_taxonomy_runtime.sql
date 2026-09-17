BEGIN;

-- BT-WP7b retires only executable incremental work.  The source tables remain
-- until BT-WP7c; their pre-retirement contents are in the immutable archive.
DELETE FROM worker_jobs WHERE job_type IN ('topics', 'themes');
ALTER TABLE worker_jobs DROP CONSTRAINT worker_jobs_type_valid;
ALTER TABLE worker_jobs ADD CONSTRAINT worker_jobs_type_valid
    CHECK (job_type IN ('eligibility_segmentation', 'embeddings'));

CREATE OR REPLACE FUNCTION enqueue_original_input_job()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE next_job_type TEXT;
BEGIN
  IF TG_OP = 'UPDATE' AND NEW.status IS NOT DISTINCT FROM OLD.status THEN RETURN NEW; END IF;
  next_job_type := CASE NEW.status
    WHEN 'new' THEN 'eligibility_segmentation'
    WHEN 'ready_for_embedding' THEN 'embeddings'
    ELSE NULL
  END;
  IF next_job_type IS NOT NULL THEN
    INSERT INTO worker_jobs(job_type, original_input_id) VALUES(next_job_type, NEW.id)
    ON CONFLICT (job_type, original_input_id) DO UPDATE SET status='pending', attempts=0,
      available_at=CURRENT_TIMESTAMP, locked_at=NULL, locked_by=NULL, last_error=NULL,
      completed_at=NULL, updated_at=CURRENT_TIMESTAMP;
  END IF;
  RETURN NEW;
END;
$$;
COMMIT;
