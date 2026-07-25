BEGIN;

CREATE TABLE themes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL
        CONSTRAINT themes_name_nonempty CHECK (btrim(name) <> ''),
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX idx_themes_name_case_insensitive
    ON themes (lower(name));

CREATE TABLE theme_topics (
    theme_id BIGINT NOT NULL
        REFERENCES themes (id) ON DELETE CASCADE,
    topic TEXT NOT NULL
        CONSTRAINT theme_topics_topic_nonempty CHECK (btrim(topic) <> ''),
    PRIMARY KEY (theme_id, topic)
);

CREATE UNIQUE INDEX idx_theme_topics_case_insensitive
    ON theme_topics (theme_id, lower(topic));

CREATE TABLE theme_suggestions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    action TEXT NOT NULL
        CONSTRAINT theme_suggestions_action_valid
        CHECK (action IN ('reuse', 'new', 'merge', 'update')),
    proposed_name TEXT NOT NULL
        CONSTRAINT theme_suggestions_name_nonempty
        CHECK (btrim(proposed_name) <> ''),
    proposed_description TEXT NOT NULL
        CONSTRAINT theme_suggestions_description_nonempty
        CHECK (btrim(proposed_description) <> ''),
    rationale TEXT NOT NULL
        CONSTRAINT theme_suggestions_rationale_nonempty
        CHECK (btrim(rationale) <> ''),
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

CREATE TABLE theme_suggestion_existing_themes (
    suggestion_id BIGINT NOT NULL
        REFERENCES theme_suggestions (id) ON DELETE CASCADE,
    theme_id BIGINT NOT NULL
        REFERENCES themes (id) ON DELETE RESTRICT,
    PRIMARY KEY (suggestion_id, theme_id)
);

CREATE TABLE theme_suggestion_topics (
    suggestion_id BIGINT NOT NULL
        REFERENCES theme_suggestions (id) ON DELETE CASCADE,
    topic TEXT NOT NULL
        CONSTRAINT theme_suggestion_topics_topic_nonempty
        CHECK (btrim(topic) <> ''),
    PRIMARY KEY (suggestion_id, topic)
);

CREATE TABLE theme_suggestion_evidence (
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

INSERT INTO themes (name)
SELECT DISTINCT btrim(theme)
FROM (
    SELECT theme FROM original_inputs
    UNION ALL
    SELECT theme FROM segment_inputs
) AS existing_themes
WHERE theme IS NOT NULL AND btrim(theme) <> ''
ON CONFLICT DO NOTHING;

INSERT INTO theme_topics (theme_id, topic)
SELECT DISTINCT themes.id, btrim(tagged.topic)
FROM (
    SELECT theme, topic FROM original_inputs
    UNION ALL
    SELECT theme, topic FROM segment_inputs
) AS tagged
JOIN themes ON lower(themes.name) = lower(btrim(tagged.theme))
WHERE
    tagged.theme IS NOT NULL
    AND btrim(tagged.theme) <> ''
    AND tagged.topic IS NOT NULL
    AND btrim(tagged.topic) <> ''
ON CONFLICT DO NOTHING;

ALTER TABLE original_inputs
    DROP COLUMN theme;

ALTER TABLE segment_inputs
    DROP COLUMN theme;

COMMIT;
