BEGIN;

-- PTR-2 separates an LLM's cluster-local label from the stable canonical
-- topic identity created by cross-question reconciliation.  The source
-- cluster remains the owner of geometry, membership, and packet selection.
ALTER TABLE taxonomy_topic_naming_attempts
    ADD CONSTRAINT taxonomy_topic_naming_attempts_run_cluster_id_unique
        UNIQUE (taxonomy_run_id, cluster_candidate_id, id);

CREATE TABLE taxonomy_provisional_topics (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    taxonomy_run_id BIGINT NOT NULL REFERENCES taxonomy_runs (id) ON DELETE RESTRICT,
    cluster_candidate_id BIGINT NOT NULL,
    naming_attempt_id BIGINT NOT NULL,
    name TEXT NOT NULL CHECK (btrim(name) <> '' AND char_length(name) <= 120),
    normalized_name TEXT NOT NULL CHECK (normalized_name = lower(btrim(name))),
    description TEXT NOT NULL CHECK (btrim(description) <> '' AND char_length(description) <= 2000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (taxonomy_run_id, id),
    UNIQUE (taxonomy_run_id, cluster_candidate_id),
    UNIQUE (taxonomy_run_id, normalized_name),
    FOREIGN KEY (taxonomy_run_id, cluster_candidate_id)
        REFERENCES taxonomy_cluster_candidates (taxonomy_run_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (taxonomy_run_id, cluster_candidate_id, naming_attempt_id)
        REFERENCES taxonomy_topic_naming_attempts
            (taxonomy_run_id, cluster_candidate_id, id) ON DELETE RESTRICT
);

CREATE OR REPLACE FUNCTION validate_taxonomy_provisional_topic()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM taxonomy_topic_naming_attempts AS attempt
        WHERE attempt.id = NEW.naming_attempt_id
          AND attempt.taxonomy_run_id = NEW.taxonomy_run_id
          AND attempt.cluster_candidate_id = NEW.cluster_candidate_id
          AND attempt.accepted
    ) THEN
        RAISE EXCEPTION 'provisional topic requires an accepted naming attempt';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER taxonomy_provisional_topics_valid
BEFORE INSERT OR UPDATE ON taxonomy_provisional_topics
FOR EACH ROW EXECUTE FUNCTION validate_taxonomy_provisional_topic();

CREATE TRIGGER taxonomy_provisional_topics_guard
BEFORE INSERT OR UPDATE OR DELETE ON taxonomy_provisional_topics
FOR EACH ROW EXECUTE FUNCTION guard_taxonomy_run_child();

COMMIT;
