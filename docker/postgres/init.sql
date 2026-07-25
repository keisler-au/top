CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS original_inputs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    original_text TEXT NOT NULL
        CONSTRAINT original_inputs_text_nonempty
        CHECK (btrim(original_text) <> ''),
    source TEXT NOT NULL
        CONSTRAINT original_inputs_source_nonempty
        CHECK (btrim(source) <> ''),
    eligible BOOLEAN NOT NULL DEFAULT FALSE,
    theme TEXT,
    topic TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

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
    theme TEXT,
    topic TEXT,
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
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT input_embeddings_exactly_one_target
        CHECK (num_nonnulls(original_input_id, segment_input_id) = 1),
    CONSTRAINT input_embeddings_original_input_unique
        UNIQUE (original_input_id),
    CONSTRAINT input_embeddings_segment_input_unique
        UNIQUE (segment_input_id)
);
