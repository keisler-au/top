BEGIN;

-- Candidate taxonomy state. Nothing in this migration is read by the current
-- dashboard, input, recommendation, or article paths.
CREATE TABLE taxonomy_runs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_cutoff TIMESTAMPTZ NOT NULL,
    source_snapshot_sha256 TEXT NOT NULL CHECK (source_snapshot_sha256 ~ '^[0-9a-f]{64}$'),
    configuration JSONB NOT NULL CHECK (jsonb_typeof(configuration) = 'object'),
    configuration_sha256 TEXT NOT NULL CHECK (configuration_sha256 ~ '^[0-9a-f]{64}$'),
    embedding_model TEXT NOT NULL CHECK (btrim(embedding_model) <> ''),
    embedding_representation TEXT NOT NULL CHECK (btrim(embedding_representation) <> ''),
    clustering_model TEXT NOT NULL CHECK (btrim(clustering_model) <> ''),
    topic_model TEXT NOT NULL CHECK (btrim(topic_model) <> ''),
    theme_model TEXT NOT NULL CHECK (btrim(theme_model) <> ''),
    topic_prompt_version TEXT NOT NULL CHECK (btrim(topic_prompt_version) <> ''),
    theme_prompt_version TEXT NOT NULL CHECK (btrim(theme_prompt_version) <> ''),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'ready_for_review', 'published', 'rejected', 'failed')),
    error_summary TEXT CHECK (error_summary IS NULL OR btrim(error_summary) <> ''),
    decision_by TEXT CHECK (decision_by IS NULL OR btrim(decision_by) <> ''),
    decision_at TIMESTAMPTZ,
    decision_note TEXT CHECK (decision_note IS NULL OR btrim(decision_note) <> ''),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT taxonomy_runs_decision_consistent CHECK (
        (status IN ('published', 'rejected')) = (decision_by IS NOT NULL AND decision_at IS NOT NULL)
    ),
    CONSTRAINT taxonomy_runs_failure_consistent CHECK (
        (status = 'failed') = (error_summary IS NOT NULL)
    ),
    CONSTRAINT taxonomy_runs_completion_consistent CHECK (
        (status IN ('ready_for_review', 'published', 'rejected')) = (completed_at IS NOT NULL)
    ),
    CONSTRAINT taxonomy_runs_publication_consistent CHECK (
        (status = 'published') = (published_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX taxonomy_runs_one_published ON taxonomy_runs ((TRUE)) WHERE status = 'published';
CREATE INDEX idx_taxonomy_runs_status_created ON taxonomy_runs (status, created_at DESC, id DESC);

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
       OR NEW.theme_prompt_version IS DISTINCT FROM OLD.theme_prompt_version THEN
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
CREATE TRIGGER taxonomy_runs_protected BEFORE UPDATE ON taxonomy_runs FOR EACH ROW EXECUTE FUNCTION protect_taxonomy_run();

CREATE TABLE taxonomy_run_evidence (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    taxonomy_run_id BIGINT NOT NULL REFERENCES taxonomy_runs (id) ON DELETE RESTRICT,
    original_input_id BIGINT NOT NULL REFERENCES original_inputs (id) ON DELETE RESTRICT,
    segment_input_id BIGINT REFERENCES segment_inputs (id) ON DELETE RESTRICT,
    embedding_id BIGINT NOT NULL REFERENCES input_embeddings (id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (taxonomy_run_id, id),
    UNIQUE (taxonomy_run_id, original_input_id, segment_input_id),
    UNIQUE (taxonomy_run_id, embedding_id)
);
CREATE INDEX idx_taxonomy_run_evidence_run ON taxonomy_run_evidence (taxonomy_run_id, id);

CREATE OR REPLACE FUNCTION validate_taxonomy_run_evidence() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE run_status TEXT; embedding_original BIGINT; embedding_segment BIGINT; segment_original BIGINT;
BEGIN
    SELECT status INTO run_status FROM taxonomy_runs WHERE id = NEW.taxonomy_run_id;
    IF run_status NOT IN ('pending', 'running', 'failed') THEN RAISE EXCEPTION 'cannot add evidence to final taxonomy run'; END IF;
    SELECT original_input_id, segment_input_id INTO embedding_original, embedding_segment FROM input_embeddings WHERE id = NEW.embedding_id;
    IF NEW.segment_input_id IS NULL THEN
        IF embedding_original IS DISTINCT FROM NEW.original_input_id THEN RAISE EXCEPTION 'evidence embedding does not match original input'; END IF;
        IF EXISTS (SELECT 1 FROM taxonomy_run_evidence WHERE taxonomy_run_id=NEW.taxonomy_run_id AND original_input_id=NEW.original_input_id AND segment_input_id IS NOT NULL) THEN RAISE EXCEPTION 'canonical run evidence cannot contain an original and its segments'; END IF;
    ELSE
        SELECT original_input_id INTO segment_original FROM segment_inputs WHERE id = NEW.segment_input_id;
        IF segment_original IS DISTINCT FROM NEW.original_input_id OR embedding_segment IS DISTINCT FROM NEW.segment_input_id THEN RAISE EXCEPTION 'evidence target does not match segment or embedding'; END IF;
        IF EXISTS (SELECT 1 FROM taxonomy_run_evidence WHERE taxonomy_run_id=NEW.taxonomy_run_id AND original_input_id=NEW.original_input_id AND segment_input_id IS NULL) THEN RAISE EXCEPTION 'canonical run evidence cannot contain an original and its segments'; END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER taxonomy_run_evidence_valid BEFORE INSERT OR UPDATE ON taxonomy_run_evidence FOR EACH ROW EXECUTE FUNCTION validate_taxonomy_run_evidence();
CREATE OR REPLACE FUNCTION reject_taxonomy_run_evidence_mutation() RETURNS TRIGGER LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'taxonomy run evidence is immutable'; END; $$;
CREATE TRIGGER taxonomy_run_evidence_immutable BEFORE UPDATE OR DELETE ON taxonomy_run_evidence FOR EACH ROW EXECUTE FUNCTION reject_taxonomy_run_evidence_mutation();

CREATE TABLE topics (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    retired_at TIMESTAMPTZ
);
CREATE TABLE topic_revisions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    taxonomy_run_id BIGINT NOT NULL REFERENCES taxonomy_runs (id) ON DELETE RESTRICT,
    topic_id BIGINT NOT NULL REFERENCES topics (id) ON DELETE RESTRICT,
    cluster_key TEXT NOT NULL CHECK (btrim(cluster_key) <> ''),
    name TEXT NOT NULL CHECK (btrim(name) <> '' AND char_length(name) <= 120),
    normalized_name TEXT NOT NULL CHECK (normalized_name = lower(btrim(name))),
    literal_description TEXT NOT NULL CHECK (btrim(literal_description) <> '' AND char_length(literal_description) <= 2000),
    support_count INTEGER NOT NULL CHECK (support_count >= 0),
    centroid VECTOR,
    cluster_diagnostics JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(cluster_diagnostics) = 'object'),
    continuity_decision TEXT NOT NULL CHECK (continuity_decision IN ('new', 'continuation', 'rename', 'split', 'merge', 'retired', 'unresolved')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (taxonomy_run_id, id), UNIQUE (taxonomy_run_id, topic_id), UNIQUE (taxonomy_run_id, cluster_key), UNIQUE (taxonomy_run_id, normalized_name)
);
CREATE TABLE topic_memberships (
    taxonomy_run_id BIGINT NOT NULL,
    topic_revision_id BIGINT NOT NULL,
    evidence_id BIGINT NOT NULL,
    membership_confidence DOUBLE PRECISION CHECK (membership_confidence IS NULL OR membership_confidence BETWEEN 0 AND 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (taxonomy_run_id, topic_revision_id, evidence_id),
    FOREIGN KEY (taxonomy_run_id, topic_revision_id) REFERENCES topic_revisions (taxonomy_run_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (taxonomy_run_id, evidence_id) REFERENCES taxonomy_run_evidence (taxonomy_run_id, id) ON DELETE RESTRICT
);
CREATE TABLE topic_representative_evidence (
    taxonomy_run_id BIGINT NOT NULL,
    topic_revision_id BIGINT NOT NULL,
    evidence_id BIGINT NOT NULL,
    representative_order INTEGER NOT NULL CHECK (representative_order >= 0),
    selection_kind TEXT NOT NULL CHECK (selection_kind IN ('central', 'diverse', 'manual')),
    PRIMARY KEY (taxonomy_run_id, topic_revision_id, evidence_id),
    UNIQUE (taxonomy_run_id, topic_revision_id, representative_order),
    FOREIGN KEY (taxonomy_run_id, topic_revision_id, evidence_id) REFERENCES topic_memberships (taxonomy_run_id, topic_revision_id, evidence_id) ON DELETE RESTRICT
);

CREATE TABLE topic_aliases (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic_id BIGINT NOT NULL REFERENCES topics (id) ON DELETE RESTRICT,
    alias TEXT NOT NULL CHECK (btrim(alias) <> '' AND char_length(alias) <= 120),
    normalized_alias TEXT NOT NULL CHECK (normalized_alias = lower(btrim(alias))),
    created_in_run_id BIGINT REFERENCES taxonomy_runs (id) ON DELETE RESTRICT,
    retired_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (topic_id, normalized_alias)
);
CREATE INDEX idx_topic_aliases_active_name ON topic_aliases (normalized_alias) WHERE retired_at IS NULL;
CREATE TABLE topic_lineage (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    taxonomy_run_id BIGINT NOT NULL REFERENCES taxonomy_runs (id) ON DELETE RESTRICT,
    predecessor_topic_id BIGINT REFERENCES topics (id) ON DELETE RESTRICT,
    successor_topic_id BIGINT REFERENCES topics (id) ON DELETE RESTRICT,
    relationship TEXT NOT NULL CHECK (relationship IN ('new', 'continuation', 'rename', 'split', 'merge', 'retired')),
    rationale TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((relationship = 'new' AND predecessor_topic_id IS NULL AND successor_topic_id IS NOT NULL) OR (relationship = 'retired' AND predecessor_topic_id IS NOT NULL AND successor_topic_id IS NULL) OR (relationship IN ('continuation', 'rename', 'split', 'merge') AND predecessor_topic_id IS NOT NULL AND successor_topic_id IS NOT NULL))
);

CREATE TABLE taxonomy_candidate_themes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    taxonomy_run_id BIGINT NOT NULL REFERENCES taxonomy_runs (id) ON DELETE RESTRICT,
    name TEXT NOT NULL CHECK (btrim(name) <> '' AND char_length(name) <= 120),
    description TEXT NOT NULL CHECK (btrim(description) <> '' AND char_length(description) <= 2000),
    rationale TEXT NOT NULL CHECK (btrim(rationale) <> '' AND char_length(rationale) <= 2000),
    inference_request JSONB NOT NULL CHECK (jsonb_typeof(inference_request) = 'object'),
    inference_response JSONB NOT NULL CHECK (jsonb_typeof(inference_response) = 'object'),
    validation_errors TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (taxonomy_run_id, id)
);
CREATE UNIQUE INDEX taxonomy_candidate_themes_run_name
    ON taxonomy_candidate_themes (taxonomy_run_id, lower(btrim(name)));
CREATE TABLE taxonomy_candidate_theme_topics (
    taxonomy_run_id BIGINT NOT NULL,
    candidate_theme_id BIGINT NOT NULL,
    topic_revision_id BIGINT NOT NULL,
    selected_by_model BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (taxonomy_run_id, candidate_theme_id, topic_revision_id),
    FOREIGN KEY (taxonomy_run_id, candidate_theme_id) REFERENCES taxonomy_candidate_themes (taxonomy_run_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (taxonomy_run_id, topic_revision_id) REFERENCES topic_revisions (taxonomy_run_id, id) ON DELETE RESTRICT
);

-- Candidate materialization is append-only. A completed run is a durable
-- review artifact, never a mutable draft that can silently change underneath
-- an operator.
CREATE OR REPLACE FUNCTION guard_taxonomy_run_child() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE run_id BIGINT; run_status TEXT;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        RAISE EXCEPTION 'taxonomy candidate records are immutable';
    END IF;
    run_id := NEW.taxonomy_run_id;
    SELECT status INTO run_status FROM taxonomy_runs WHERE id = run_id;
    IF run_status NOT IN ('pending', 'running', 'failed') THEN
        RAISE EXCEPTION 'cannot add candidate records to a completed taxonomy run';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER topic_revisions_guard BEFORE INSERT OR UPDATE OR DELETE ON topic_revisions FOR EACH ROW EXECUTE FUNCTION guard_taxonomy_run_child();
CREATE TRIGGER topic_memberships_guard BEFORE INSERT OR UPDATE OR DELETE ON topic_memberships FOR EACH ROW EXECUTE FUNCTION guard_taxonomy_run_child();
CREATE TRIGGER topic_representatives_guard BEFORE INSERT OR UPDATE OR DELETE ON topic_representative_evidence FOR EACH ROW EXECUTE FUNCTION guard_taxonomy_run_child();
CREATE TRIGGER topic_lineage_guard BEFORE INSERT OR UPDATE OR DELETE ON topic_lineage FOR EACH ROW EXECUTE FUNCTION guard_taxonomy_run_child();
CREATE TRIGGER candidate_themes_guard BEFORE INSERT OR UPDATE OR DELETE ON taxonomy_candidate_themes FOR EACH ROW EXECUTE FUNCTION guard_taxonomy_run_child();
CREATE TRIGGER candidate_theme_topics_guard BEFORE INSERT OR UPDATE OR DELETE ON taxonomy_candidate_theme_topics FOR EACH ROW EXECUTE FUNCTION guard_taxonomy_run_child();

COMMIT;
