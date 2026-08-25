BEGIN;

CREATE TABLE articles (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL
        CONSTRAINT articles_title_nonempty
        CHECK (btrim(title) <> '' AND char_length(title) <= 500),
    status TEXT NOT NULL DEFAULT 'draft'
        CONSTRAINT articles_status_valid
        CHECK (status IN ('draft', 'ready_for_review', 'approved', 'archived')),
    current_revision_id BIGINT,
    generation_metadata JSONB,
    approved_at TIMESTAMPTZ,
    archived_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT articles_lifecycle_timestamps_consistent CHECK (
        (status = 'approved') = (approved_at IS NOT NULL)
        AND (status = 'archived') = (archived_at IS NOT NULL)
    )
);

CREATE TABLE article_revisions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    article_id BIGINT NOT NULL
        REFERENCES articles (id) ON DELETE CASCADE,
    revision_number INTEGER NOT NULL
        CONSTRAINT article_revisions_number_positive CHECK (revision_number >= 1),
    title TEXT NOT NULL
        CONSTRAINT article_revisions_title_nonempty
        CHECK (btrim(title) <> '' AND char_length(title) <= 500),
    structured_content JSONB NOT NULL
        CONSTRAINT article_revisions_content_object
        CHECK (jsonb_typeof(structured_content) = 'object'),
    rendered_html TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT article_revisions_article_number_unique
        UNIQUE (article_id, revision_number),
    CONSTRAINT article_revisions_article_id_id_unique
        UNIQUE (article_id, id)
);

ALTER TABLE articles
    ADD CONSTRAINT articles_current_revision_fk
    FOREIGN KEY (id, current_revision_id)
    REFERENCES article_revisions (article_id, id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE INDEX idx_articles_status_updated
    ON articles (status, updated_at DESC, id DESC);

CREATE INDEX idx_article_revisions_article
    ON article_revisions (article_id, revision_number DESC);

CREATE OR REPLACE FUNCTION reject_article_revision_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'article revisions are immutable; create a new revision';
END;
$$;

CREATE TRIGGER article_revisions_immutable
BEFORE UPDATE OR DELETE ON article_revisions
FOR EACH ROW
EXECUTE FUNCTION reject_article_revision_mutation();

CREATE TABLE article_themes (
    article_id BIGINT NOT NULL
        REFERENCES articles (id) ON DELETE CASCADE,
    theme_id BIGINT NOT NULL
        REFERENCES themes (id) ON DELETE RESTRICT,
    PRIMARY KEY (article_id, theme_id)
);

CREATE TABLE article_topics (
    article_id BIGINT NOT NULL
        REFERENCES articles (id) ON DELETE CASCADE,
    topic_key TEXT NOT NULL
        CONSTRAINT article_topics_key_nonempty CHECK (btrim(topic_key) <> ''),
    topic_name TEXT NOT NULL
        CONSTRAINT article_topics_name_nonempty
        CHECK (btrim(topic_name) <> '' AND char_length(topic_name) <= 120),
    PRIMARY KEY (article_id, topic_key),
    CONSTRAINT article_topics_key_normalized
        CHECK (topic_key = lower(btrim(topic_name)))
);

CREATE OR REPLACE FUNCTION reject_merged_article_theme()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM themes
        WHERE id = NEW.theme_id AND merged_into_id IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'articles may only link canonical live themes';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER article_themes_canonical_only
BEFORE INSERT OR UPDATE ON article_themes
FOR EACH ROW
EXECUTE FUNCTION reject_merged_article_theme();

CREATE INDEX idx_article_themes_theme ON article_themes (theme_id, article_id);
CREATE INDEX idx_article_topics_topic ON article_topics (topic_key, article_id);

CREATE TABLE article_evidence (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    revision_id BIGINT NOT NULL
        REFERENCES article_revisions (id) ON DELETE CASCADE,
    original_input_id BIGINT
        REFERENCES original_inputs (id) ON DELETE RESTRICT,
    segment_input_id BIGINT
        REFERENCES segment_inputs (id) ON DELETE RESTRICT,
    evidence_order INTEGER NOT NULL
        CONSTRAINT article_evidence_order_nonnegative CHECK (evidence_order >= 0),
    citation_id TEXT,
    topic_key TEXT NOT NULL
        CONSTRAINT article_evidence_topic_nonempty CHECK (btrim(topic_key) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT article_evidence_exactly_one_target
        CHECK (num_nonnulls(original_input_id, segment_input_id) = 1),
    CONSTRAINT article_evidence_revision_order_unique
        UNIQUE (revision_id, evidence_order),
    CONSTRAINT article_evidence_revision_original_unique
        UNIQUE (revision_id, original_input_id),
    CONSTRAINT article_evidence_revision_segment_unique
        UNIQUE (revision_id, segment_input_id)
);

CREATE INDEX idx_article_evidence_revision
    ON article_evidence (revision_id, evidence_order);

CREATE TABLE article_audit (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    article_id BIGINT NOT NULL
        REFERENCES articles (id) ON DELETE CASCADE,
    revision_id BIGINT
        REFERENCES article_revisions (id) ON DELETE RESTRICT,
    action TEXT NOT NULL
        CONSTRAINT article_audit_action_valid
        CHECK (action IN (
            'created',
            'revised',
            'submitted',
            'approved',
            'returned_to_draft',
            'archived'
        )),
    actor TEXT,
    note TEXT
        CONSTRAINT article_audit_note_length
        CHECK (note IS NULL OR char_length(note) <= 2000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_article_audit_article
    ON article_audit (article_id, created_at DESC, id DESC);

COMMIT;
