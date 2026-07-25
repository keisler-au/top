BEGIN;

UPDATE original_inputs
SET topic = NULL
WHERE topic IS NOT NULL AND btrim(topic) = '';

UPDATE segment_inputs
SET topic = NULL
WHERE topic IS NOT NULL AND btrim(topic) = '';

ALTER TABLE original_inputs
    ADD CONSTRAINT original_inputs_topic_nonempty
        CHECK (
            topic IS NULL
            OR (btrim(topic) <> '' AND char_length(topic) <= 120)
        ),
    ADD CONSTRAINT original_inputs_completed_has_topic
        CHECK (status <> 'completed' OR topic IS NOT NULL);

ALTER TABLE segment_inputs
    ADD CONSTRAINT segment_inputs_topic_nonempty
        CHECK (
            topic IS NULL
            OR (btrim(topic) <> '' AND char_length(topic) <= 120)
        );

ALTER TABLE input_embeddings
    ADD COLUMN embedding_model TEXT;

UPDATE input_embeddings
SET embedding_model = 'legacy'
WHERE embedding_model IS NULL;

ALTER TABLE input_embeddings
    ALTER COLUMN embedding_model SET NOT NULL,
    ADD CONSTRAINT input_embeddings_model_nonempty
        CHECK (btrim(embedding_model) <> '');

ALTER TABLE themes
    ADD CONSTRAINT themes_name_length
        CHECK (char_length(name) <= 120),
    ADD CONSTRAINT themes_description_length
        CHECK (description IS NULL OR char_length(description) <= 2000);

ALTER TABLE theme_topics
    ADD CONSTRAINT theme_topics_topic_length
        CHECK (char_length(topic) <= 120);

ALTER TABLE theme_suggestions
    ADD CONSTRAINT theme_suggestions_name_length
        CHECK (char_length(proposed_name) <= 120),
    ADD CONSTRAINT theme_suggestions_description_length
        CHECK (char_length(proposed_description) <= 2000),
    ADD CONSTRAINT theme_suggestions_rationale_length
        CHECK (char_length(rationale) <= 2000);

ALTER TABLE theme_suggestion_topics
    ADD CONSTRAINT theme_suggestion_topics_topic_length
        CHECK (char_length(topic) <= 120);

CREATE INDEX idx_original_inputs_completed
    ON original_inputs (id)
    WHERE status = 'completed';

COMMIT;
