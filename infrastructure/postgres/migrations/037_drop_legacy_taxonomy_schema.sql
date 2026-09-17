BEGIN;

-- BT-WP7c: the immutable archive made in 034 is now the sole home for the
-- retired incremental taxonomy.  First preserve article display snapshots so
-- deleting the mutable source cannot alter historical article rendering.
UPDATE article_themes links
SET stable_theme_id = revisions.theme_id,
    theme_name_snapshot = revisions.name
FROM themes legacy
JOIN taxonomy_runs published ON published.status = 'published'
JOIN theme_revisions revisions
  ON revisions.taxonomy_run_id = published.id
 AND revisions.normalized_name = lower(btrim(legacy.name))
WHERE links.theme_id = legacy.id
  AND links.stable_theme_id IS NULL;

UPDATE article_themes links
SET theme_name_snapshot = COALESCE(links.theme_name_snapshot, legacy.name)
FROM themes legacy
WHERE links.theme_id = legacy.id;

UPDATE article_topics
SET topic_name_snapshot = COALESCE(topic_name_snapshot, topic_name);

ALTER TABLE article_themes DROP CONSTRAINT article_themes_pkey;
DROP TRIGGER IF EXISTS article_themes_canonical_only ON article_themes;
DROP TRIGGER IF EXISTS article_theme_snapshot_required ON article_themes;
DROP FUNCTION IF EXISTS reject_merged_article_theme();
ALTER TABLE article_themes DROP COLUMN theme_id;
ALTER TABLE article_themes ALTER COLUMN theme_name_snapshot SET NOT NULL;
ALTER TABLE article_themes ADD PRIMARY KEY (article_id, theme_name_snapshot);
CREATE UNIQUE INDEX article_themes_stable_theme_once_per_article
  ON article_themes(article_id, stable_theme_id) WHERE stable_theme_id IS NOT NULL;

ALTER TABLE article_topics ADD COLUMN id BIGINT GENERATED ALWAYS AS IDENTITY;
ALTER TABLE article_topics DROP CONSTRAINT article_topics_pkey;
ALTER TABLE article_topics DROP CONSTRAINT article_topics_key_normalized;
ALTER TABLE article_topics DROP COLUMN topic_key;
ALTER TABLE article_topics DROP COLUMN topic_name;
ALTER TABLE article_topics ALTER COLUMN topic_name_snapshot SET NOT NULL;
ALTER TABLE article_topics ADD PRIMARY KEY (id);
CREATE UNIQUE INDEX article_topics_snapshot_once_per_article
  ON article_topics(article_id, topic_name_snapshot);

-- Manual rollout/sign-off is obsolete: publication is bound to immutable
-- release attestations and publication decisions.  Retain prior records under
-- the protected archive schema before removing the mutable table and routes.
CREATE TABLE taxonomy_legacy_archive.rollout_reports (
    taxonomy_run_id BIGINT PRIMARY KEY,
    legacy_metrics JSONB NOT NULL,
    candidate_metrics JSONB NOT NULL,
    mappings JSONB NOT NULL,
    signed_off_by TEXT,
    signed_off_at TIMESTAMPTZ,
    sign_off_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO taxonomy_legacy_archive.rollout_reports(
    taxonomy_run_id, legacy_metrics, candidate_metrics, mappings,
    signed_off_by, signed_off_at, sign_off_note, created_at
)
SELECT taxonomy_run_id, legacy_metrics, candidate_metrics, mappings,
       signed_off_by, signed_off_at, sign_off_note, generated_at
FROM taxonomy_rollout_reports;
CREATE TRIGGER rollout_reports_immutable
BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON taxonomy_legacy_archive.rollout_reports
FOR EACH STATEMENT EXECUTE FUNCTION taxonomy_legacy_archive.reject_mutation();
DROP TRIGGER taxonomy_runs_require_rollout_signoff ON taxonomy_runs;
DROP FUNCTION require_taxonomy_rollout_signoff();
DROP TABLE taxonomy_rollout_reports;

-- No retained application relation may refer to mutable incremental state.
ALTER TABLE original_inputs DROP CONSTRAINT original_inputs_completed_has_topic;
ALTER TABLE original_inputs DROP COLUMN topic;
ALTER TABLE segment_inputs DROP COLUMN topic;
DROP TABLE theme_suggestion_evidence;
DROP TABLE theme_suggestion_topics;
DROP TABLE theme_suggestion_existing_themes;
DROP TABLE theme_suggestions;
DROP TABLE theme_topics;
DROP TABLE topic_assignment_attempts;
DROP TABLE themes;

COMMIT;
