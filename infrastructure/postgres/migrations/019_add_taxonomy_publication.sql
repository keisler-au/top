BEGIN;

-- Publication is deliberately represented by the run status rather than by
-- copying candidate rows into mutable live tables.  Readers can therefore use
-- one run-scoped projection and a rejected candidate remains inert.
CREATE OR REPLACE FUNCTION publish_taxonomy_run(
    candidate_run_id BIGINT,
    expected_updated_at TIMESTAMPTZ,
    operator_name TEXT,
    operator_note TEXT DEFAULT NULL
) RETURNS taxonomy_runs
LANGUAGE plpgsql
AS $$
DECLARE published taxonomy_runs;
BEGIN
    IF btrim(operator_name) = '' THEN
        RAISE EXCEPTION 'operator name is required';
    END IF;

    SELECT * INTO published
    FROM taxonomy_runs
    WHERE id = candidate_run_id
      AND status = 'ready_for_review'
      AND updated_at = expected_updated_at
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'taxonomy run is no longer ready for review';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM topic_revisions WHERE taxonomy_run_id = candidate_run_id) THEN
        RAISE EXCEPTION 'taxonomy run has no accepted topics';
    END IF;

    -- Names published by this run become lookup aliases.  This preserves
    -- staged string URLs while all new relationships use topic_id.
    INSERT INTO topic_aliases (topic_id, alias, normalized_alias, created_in_run_id)
    SELECT topic_id, name, normalized_name, candidate_run_id
    FROM topic_revisions
    WHERE taxonomy_run_id = candidate_run_id
    ON CONFLICT (topic_id, normalized_alias) DO NOTHING;

    -- The partial unique index permits only one published run.  Retiring the
    -- old run is intentionally not implicit: rollback is an explicit action.
    UPDATE taxonomy_runs
    SET status = 'published', decision_by = operator_name,
        decision_at = CURRENT_TIMESTAMP, decision_note = operator_note,
        published_at = CURRENT_TIMESTAMP
    WHERE id = candidate_run_id
    RETURNING * INTO published;
    RETURN published;
END;
$$;

CREATE OR REPLACE FUNCTION reject_taxonomy_run(
    candidate_run_id BIGINT,
    expected_updated_at TIMESTAMPTZ,
    operator_name TEXT,
    operator_note TEXT DEFAULT NULL
) RETURNS taxonomy_runs
LANGUAGE plpgsql
AS $$
DECLARE rejected taxonomy_runs;
BEGIN
    IF btrim(operator_name) = '' THEN
        RAISE EXCEPTION 'operator name is required';
    END IF;
    UPDATE taxonomy_runs
    SET status = 'rejected', decision_by = operator_name,
        decision_at = CURRENT_TIMESTAMP, decision_note = operator_note,
        completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP)
    WHERE id = candidate_run_id
      AND status IN ('pending', 'failed', 'ready_for_review')
      AND updated_at = expected_updated_at
    RETURNING * INTO rejected;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'taxonomy run cannot be rejected in its current version or state';
    END IF;
    RETURN rejected;
END;
$$;

-- New article tags retain the durable topic identity while topic_name remains
-- the immutable display snapshot required for historical rendering.  Existing
-- string-only tags are intentionally left untouched during this compatibility
-- period.
ALTER TABLE article_topics ADD COLUMN topic_id BIGINT REFERENCES topics (id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX article_topics_topic_id_once_per_article
    ON article_topics (article_id, topic_id) WHERE topic_id IS NOT NULL;
CREATE INDEX idx_article_topics_topic_id ON article_topics (topic_id, article_id)
    WHERE topic_id IS NOT NULL;

COMMIT;
