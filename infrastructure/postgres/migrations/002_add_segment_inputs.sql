BEGIN;

ALTER TABLE original_inputs
    RENAME COLUMN eligble TO eligible;

ALTER TABLE original_inputs
    ALTER COLUMN source SET NOT NULL,
    ADD CONSTRAINT original_inputs_text_nonempty
        CHECK (btrim(original_text) <> ''),
    ADD CONSTRAINT original_inputs_source_nonempty
        CHECK (btrim(source) <> '');

CREATE TABLE segment_inputs (
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

ALTER TABLE input_embeddings
    ALTER COLUMN original_input_id DROP NOT NULL,
    DROP CONSTRAINT input_embeddings_segment_input_id_fkey,
    ADD CONSTRAINT input_embeddings_segment_input_id_fkey
        FOREIGN KEY (segment_input_id)
        REFERENCES segment_inputs (id)
        ON DELETE CASCADE,
    ADD CONSTRAINT input_embeddings_exactly_one_target
        CHECK (num_nonnulls(original_input_id, segment_input_id) = 1),
    ADD CONSTRAINT input_embeddings_original_input_unique
        UNIQUE (original_input_id),
    ADD CONSTRAINT input_embeddings_segment_input_unique
        UNIQUE (segment_input_id);

DROP INDEX IF EXISTS idx_input_embeddings_original_input_id;

COMMIT;
