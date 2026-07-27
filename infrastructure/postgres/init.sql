-- Fresh-install snapshot of the current schema. Incremental migrations in
-- infrastructure/postgres/migrations/ are the source of truth for upgrades.
-- When a migration changes the base schema, keep this snapshot and the seeded
-- schema_migrations entries in sync.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS questions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source TEXT NOT NULL
        CONSTRAINT questions_source_nonempty CHECK (btrim(source) <> ''),
    form_key TEXT NOT NULL
        CONSTRAINT questions_form_key_nonempty CHECK (btrim(form_key) <> ''),
    question_key TEXT NOT NULL
        CONSTRAINT questions_question_key_nonempty
        CHECK (btrim(question_key) <> ''),
    question_version INTEGER NOT NULL DEFAULT 1
        CONSTRAINT questions_version_positive CHECK (question_version >= 1),
    question_text TEXT NOT NULL
        CONSTRAINT questions_text_nonempty CHECK (btrim(question_text) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT questions_identity_unique
        UNIQUE (source, form_key, question_key, question_version)
);

CREATE INDEX IF NOT EXISTS idx_questions_source_form
    ON questions (source, form_key);

CREATE OR REPLACE FUNCTION reject_question_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'questions rows are immutable; insert a new question_version instead';
END;
$$;

DROP TRIGGER IF EXISTS questions_immutable ON questions;

CREATE TRIGGER questions_immutable
BEFORE UPDATE ON questions
FOR EACH ROW
EXECUTE FUNCTION reject_question_mutation();

CREATE TABLE IF NOT EXISTS original_inputs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    original_text TEXT NOT NULL
        CONSTRAINT original_inputs_text_nonempty
        CHECK (btrim(original_text) <> ''),
    source TEXT NOT NULL
        CONSTRAINT original_inputs_source_nonempty
        CHECK (btrim(source) <> ''),
    status TEXT NOT NULL DEFAULT 'new'
        CONSTRAINT original_inputs_status_valid
        CHECK (
            status IN (
                'new',
                'ineligible',
                'ready_for_embedding',
                'ready_for_analysis',
                'completed'
            )
        ),
    topic TEXT
        CONSTRAINT original_inputs_topic_nonempty
        CHECK (
            topic IS NULL
            OR (btrim(topic) <> '' AND char_length(topic) <= 120)
        ),
    question_id BIGINT
        REFERENCES questions (id) ON DELETE RESTRICT,
    submission_key TEXT
        CONSTRAINT original_inputs_submission_key_nonempty
        CHECK (submission_key IS NULL OR btrim(submission_key) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT original_inputs_completed_has_topic
        CHECK (status <> 'completed' OR topic IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_original_inputs_new
    ON original_inputs (id)
    WHERE status = 'new';

CREATE INDEX IF NOT EXISTS idx_original_inputs_ready_for_embedding
    ON original_inputs (id)
    WHERE status = 'ready_for_embedding';

CREATE INDEX IF NOT EXISTS idx_original_inputs_ready_for_analysis
    ON original_inputs (id)
    WHERE status = 'ready_for_analysis';

CREATE INDEX IF NOT EXISTS idx_original_inputs_completed
    ON original_inputs (id)
    WHERE status = 'completed';

CREATE INDEX IF NOT EXISTS idx_original_inputs_question_id
    ON original_inputs (question_id)
    WHERE question_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_original_inputs_submission_key
    ON original_inputs (submission_key)
    WHERE submission_key IS NOT NULL;

CREATE OR REPLACE FUNCTION reject_question_id_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.question_id IS DISTINCT FROM NEW.question_id THEN
        RAISE EXCEPTION 'original_inputs.question_id is immutable once set';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS original_inputs_question_id_immutable
    ON original_inputs;

CREATE TRIGGER original_inputs_question_id_immutable
BEFORE UPDATE ON original_inputs
FOR EACH ROW
EXECUTE FUNCTION reject_question_id_mutation();

CREATE TABLE IF NOT EXISTS segment_inputs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    original_input_id BIGINT NOT NULL
        REFERENCES original_inputs (id) ON DELETE CASCADE,
    segment_order INTEGER NOT NULL
        CONSTRAINT segment_inputs_index_nonnegative
        CHECK (segment_order >= 0),
    segment_text TEXT NOT NULL
        CONSTRAINT segment_inputs_text_nonempty
        CHECK (btrim(segment_text) <> ''),
    topic TEXT
        CONSTRAINT segment_inputs_topic_nonempty
        CHECK (
            topic IS NULL
            OR (btrim(topic) <> '' AND char_length(topic) <= 120)
        ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT segment_inputs_original_position_unique
        UNIQUE (original_input_id, segment_order)
);

CREATE TABLE IF NOT EXISTS input_embeddings (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    original_input_id BIGINT
        REFERENCES original_inputs (id) ON DELETE CASCADE,
    segment_input_id BIGINT
        REFERENCES segment_inputs (id) ON DELETE CASCADE,
    embedding VECTOR NOT NULL,
    embedding_model TEXT NOT NULL
        CONSTRAINT input_embeddings_model_nonempty
        CHECK (btrim(embedding_model) <> ''),
    embedding_representation TEXT NOT NULL DEFAULT 'answer-only'
        CONSTRAINT input_embeddings_representation_nonempty
        CHECK (btrim(embedding_representation) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT input_embeddings_exactly_one_target
        CHECK (num_nonnulls(original_input_id, segment_input_id) = 1),
    CONSTRAINT input_embeddings_original_input_unique
        UNIQUE (original_input_id),
    CONSTRAINT input_embeddings_segment_input_unique
        UNIQUE (segment_input_id)
);

CREATE TABLE IF NOT EXISTS themes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL
        CONSTRAINT themes_name_nonempty
        CHECK (btrim(name) <> '' AND char_length(name) <= 120),
    description TEXT
        CONSTRAINT themes_description_length
        CHECK (description IS NULL OR char_length(description) <= 2000),
    merged_into_id BIGINT
        REFERENCES themes (id) ON DELETE SET NULL
        CONSTRAINT themes_not_self_merged CHECK (merged_into_id <> id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_themes_name_case_insensitive
    ON themes (lower(name));

CREATE INDEX IF NOT EXISTS idx_themes_merged_into
    ON themes (merged_into_id)
    WHERE merged_into_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS theme_topics (
    theme_id BIGINT NOT NULL
        REFERENCES themes (id) ON DELETE CASCADE,
    topic TEXT NOT NULL
        CONSTRAINT theme_topics_topic_nonempty
        CHECK (btrim(topic) <> '' AND char_length(topic) <= 120),
    PRIMARY KEY (theme_id, topic)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_theme_topics_case_insensitive
    ON theme_topics (theme_id, lower(topic));

CREATE TABLE IF NOT EXISTS theme_suggestions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    action TEXT NOT NULL
        CONSTRAINT theme_suggestions_action_valid
        CHECK (action IN ('reuse', 'new', 'merge', 'update')),
    proposed_name TEXT NOT NULL
        CONSTRAINT theme_suggestions_name_nonempty
        CHECK (
            btrim(proposed_name) <> ''
            AND char_length(proposed_name) <= 120
        ),
    proposed_description TEXT NOT NULL
        CONSTRAINT theme_suggestions_description_nonempty
        CHECK (
            btrim(proposed_description) <> ''
            AND char_length(proposed_description) <= 2000
        ),
    rationale TEXT NOT NULL
        CONSTRAINT theme_suggestions_rationale_nonempty
        CHECK (btrim(rationale) <> '' AND char_length(rationale) <= 2000),
    group_fingerprint TEXT NOT NULL UNIQUE
        CONSTRAINT theme_suggestions_fingerprint_valid
        CHECK (group_fingerprint ~ '^[0-9a-f]{64}$'),
    materialized_theme_id BIGINT
        REFERENCES themes (id) ON DELETE RESTRICT,
    materialized_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT theme_suggestions_materialization_consistent
        CHECK (
            (materialized_theme_id IS NULL AND materialized_at IS NULL)
            OR
            (
                materialized_theme_id IS NOT NULL
                AND materialized_at IS NOT NULL
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_theme_suggestions_unmaterialized
    ON theme_suggestions (id)
    WHERE materialized_at IS NULL;

CREATE TABLE IF NOT EXISTS theme_suggestion_existing_themes (
    suggestion_id BIGINT NOT NULL
        REFERENCES theme_suggestions (id) ON DELETE CASCADE,
    theme_id BIGINT NOT NULL
        REFERENCES themes (id) ON DELETE RESTRICT,
    PRIMARY KEY (suggestion_id, theme_id)
);

CREATE TABLE IF NOT EXISTS theme_suggestion_topics (
    suggestion_id BIGINT NOT NULL
        REFERENCES theme_suggestions (id) ON DELETE CASCADE,
    topic TEXT NOT NULL
        CONSTRAINT theme_suggestion_topics_topic_nonempty
        CHECK (btrim(topic) <> '' AND char_length(topic) <= 120),
    PRIMARY KEY (suggestion_id, topic)
);

CREATE TABLE IF NOT EXISTS theme_suggestion_evidence (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    suggestion_id BIGINT NOT NULL
        REFERENCES theme_suggestions (id) ON DELETE CASCADE,
    original_input_id BIGINT
        REFERENCES original_inputs (id) ON DELETE CASCADE,
    segment_input_id BIGINT
        REFERENCES segment_inputs (id) ON DELETE CASCADE,
    CONSTRAINT theme_suggestion_evidence_exactly_one_target
        CHECK (num_nonnulls(original_input_id, segment_input_id) = 1),
    CONSTRAINT theme_suggestion_evidence_original_unique
        UNIQUE (suggestion_id, original_input_id),
    CONSTRAINT theme_suggestion_evidence_segment_unique
        UNIQUE (suggestion_id, segment_input_id)
);

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

CREATE TABLE IF NOT EXISTS schema_migrations (
    filename TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO schema_migrations (filename)
VALUES
    ('002_add_segment_inputs.sql'),
    ('003_add_input_status.sql'),
    ('004_add_ready_for_analysis_status.sql'),
    ('005_add_completed_status.sql'),
    ('006_add_theme_management.sql'),
    ('007_align_worker_contracts.sql'),
    ('008_add_worker_jobs.sql'),
    ('009_remove_theme_suggestion_review.sql'),
    ('010_normalize_question_context.sql')
ON CONFLICT DO NOTHING;
