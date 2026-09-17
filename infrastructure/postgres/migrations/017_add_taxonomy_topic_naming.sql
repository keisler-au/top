BEGIN;

CREATE TABLE taxonomy_topic_naming_attempts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    taxonomy_run_id BIGINT NOT NULL REFERENCES taxonomy_runs (id) ON DELETE RESTRICT,
    cluster_candidate_id BIGINT NOT NULL REFERENCES taxonomy_cluster_candidates (id) ON DELETE RESTRICT,
    attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
    model TEXT NOT NULL CHECK (btrim(model) <> ''),
    prompt_version TEXT NOT NULL CHECK (btrim(prompt_version) <> ''),
    prompt_sha256 TEXT NOT NULL CHECK (prompt_sha256 ~ '^[0-9a-f]{64}$'),
    request_context JSONB NOT NULL CHECK (jsonb_typeof(request_context) = 'object'),
    raw_response JSONB NOT NULL CHECK (jsonb_typeof(raw_response) = 'object'),
    validation_errors TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    accepted BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (taxonomy_run_id, cluster_candidate_id, attempt_number),
    CHECK (accepted = (cardinality(validation_errors) = 0))
);

CREATE TABLE topic_continuity_proposals (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    taxonomy_run_id BIGINT NOT NULL,
    topic_revision_id BIGINT NOT NULL,
    prior_topic_id BIGINT NOT NULL REFERENCES topics (id) ON DELETE RESTRICT,
    proposed_relationship TEXT NOT NULL CHECK (proposed_relationship IN ('continuation', 'rename', 'split', 'merge')),
    centroid_similarity DOUBLE PRECISION CHECK (centroid_similarity BETWEEN -1 AND 1),
    evidence_overlap DOUBLE PRECISION CHECK (evidence_overlap BETWEEN 0 AND 1),
    status TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'accepted', 'rejected')),
    rationale TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (taxonomy_run_id, topic_revision_id, prior_topic_id),
    FOREIGN KEY (taxonomy_run_id, topic_revision_id) REFERENCES topic_revisions (taxonomy_run_id, id) ON DELETE RESTRICT
);

CREATE TRIGGER topic_naming_attempts_guard BEFORE INSERT OR UPDATE OR DELETE ON taxonomy_topic_naming_attempts FOR EACH ROW EXECUTE FUNCTION guard_taxonomy_run_child();
CREATE TRIGGER topic_continuity_proposals_guard BEFORE INSERT OR UPDATE OR DELETE ON topic_continuity_proposals FOR EACH ROW EXECUTE FUNCTION guard_taxonomy_run_child();

COMMIT;
