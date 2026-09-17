BEGIN;

-- A snapshot creator records its idempotency key and the exact vector shape it
-- admitted.  Older hand-created candidate runs remain readable with NULL
-- snapshot metadata; all runs created through the supported service populate
-- every field below.
ALTER TABLE taxonomy_runs
    ADD COLUMN idempotency_key TEXT
        CHECK (idempotency_key IS NULL OR btrim(idempotency_key) <> ''),
    ADD COLUMN snapshot_evidence_count INTEGER
        CHECK (snapshot_evidence_count IS NULL OR snapshot_evidence_count > 0),
    ADD COLUMN embedding_dimension INTEGER
        CHECK (embedding_dimension IS NULL OR embedding_dimension > 0);

CREATE UNIQUE INDEX taxonomy_runs_idempotency_key_unique
    ON taxonomy_runs (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

-- Replace the original function so snapshot provenance has the same immutable
-- protection as the source and configuration hashes.
CREATE OR REPLACE FUNCTION protect_taxonomy_run() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.source_cutoff IS DISTINCT FROM OLD.source_cutoff
       OR NEW.source_snapshot_sha256 IS DISTINCT FROM OLD.source_snapshot_sha256
       OR NEW.configuration IS DISTINCT FROM OLD.configuration
       OR NEW.configuration_sha256 IS DISTINCT FROM OLD.configuration_sha256
       OR NEW.embedding_model IS DISTINCT FROM OLD.embedding_model
       OR NEW.embedding_representation IS DISTINCT FROM OLD.embedding_representation
       OR NEW.clustering_model IS DISTINCT FROM OLD.clustering_model
       OR NEW.topic_model IS DISTINCT FROM OLD.topic_model
       OR NEW.theme_model IS DISTINCT FROM OLD.theme_model
       OR NEW.topic_prompt_version IS DISTINCT FROM OLD.topic_prompt_version
       OR NEW.theme_prompt_version IS DISTINCT FROM OLD.theme_prompt_version
       OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
       OR NEW.snapshot_evidence_count IS DISTINCT FROM OLD.snapshot_evidence_count
       OR NEW.embedding_dimension IS DISTINCT FROM OLD.embedding_dimension THEN
        RAISE EXCEPTION 'taxonomy run provenance is immutable';
    END IF;
    IF OLD.status = 'published' OR OLD.status = 'rejected' THEN
        RAISE EXCEPTION 'final taxonomy runs are immutable';
    END IF;
    IF NOT (
        (OLD.status = 'pending' AND NEW.status IN ('pending', 'running', 'rejected', 'failed')) OR
        (OLD.status = 'running' AND NEW.status IN ('running', 'ready_for_review', 'failed')) OR
        (OLD.status = 'failed' AND NEW.status IN ('failed', 'running', 'rejected')) OR
        (OLD.status = 'ready_for_review' AND NEW.status IN ('ready_for_review', 'published', 'rejected'))
    ) THEN
        RAISE EXCEPTION 'invalid taxonomy run state transition: % to %', OLD.status, NEW.status;
    END IF;
    NEW.updated_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

COMMIT;
