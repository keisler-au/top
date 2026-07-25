CREATE EXTENSION IF NOT EXISTS vector;

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
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_themes_name_case_insensitive
    ON themes (lower(name));

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
    review_status TEXT NOT NULL DEFAULT 'pending'
        CONSTRAINT theme_suggestions_review_status_valid
        CHECK (review_status IN ('pending', 'accepted', 'rejected')),
    group_fingerprint TEXT NOT NULL UNIQUE
        CONSTRAINT theme_suggestions_fingerprint_valid
        CHECK (group_fingerprint ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMPTZ,
    CONSTRAINT theme_suggestions_reviewed_at_consistent
        CHECK (
            (review_status = 'pending' AND reviewed_at IS NULL)
            OR (review_status <> 'pending' AND reviewed_at IS NOT NULL)
        )
);

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
