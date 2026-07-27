BEGIN;

CREATE TABLE questions (
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

CREATE INDEX idx_questions_source_form
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

CREATE TRIGGER questions_immutable
BEFORE UPDATE ON questions
FOR EACH ROW
EXECUTE FUNCTION reject_question_mutation();

ALTER TABLE original_inputs
    ADD COLUMN question_id BIGINT
        REFERENCES questions (id) ON DELETE RESTRICT,
    ADD COLUMN submission_key TEXT
        CONSTRAINT original_inputs_submission_key_nonempty
        CHECK (submission_key IS NULL OR btrim(submission_key) <> '');

CREATE INDEX idx_original_inputs_question_id
    ON original_inputs (question_id)
    WHERE question_id IS NOT NULL;

CREATE INDEX idx_original_inputs_submission_key
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

CREATE TRIGGER original_inputs_question_id_immutable
BEFORE UPDATE ON original_inputs
FOR EACH ROW
EXECUTE FUNCTION reject_question_id_mutation();

ALTER TABLE input_embeddings
    ADD COLUMN embedding_representation TEXT NOT NULL DEFAULT 'answer-only'
        CONSTRAINT input_embeddings_representation_nonempty
        CHECK (btrim(embedding_representation) <> '');

ALTER TABLE themes
    ADD COLUMN merged_into_id BIGINT
        REFERENCES themes (id) ON DELETE SET NULL
        CONSTRAINT themes_not_self_merged CHECK (merged_into_id <> id);

CREATE INDEX idx_themes_merged_into
    ON themes (merged_into_id)
    WHERE merged_into_id IS NOT NULL;

ALTER TABLE theme_suggestions
    ADD COLUMN materialized_theme_id BIGINT
        REFERENCES themes (id) ON DELETE RESTRICT,
    ADD COLUMN materialized_at TIMESTAMPTZ,
    ADD CONSTRAINT theme_suggestions_materialization_consistent
        CHECK (
            (materialized_theme_id IS NULL AND materialized_at IS NULL)
            OR
            (
                materialized_theme_id IS NOT NULL
                AND materialized_at IS NOT NULL
            )
        );

CREATE INDEX idx_theme_suggestions_unmaterialized
    ON theme_suggestions (id)
    WHERE materialized_at IS NULL;

COMMIT;
