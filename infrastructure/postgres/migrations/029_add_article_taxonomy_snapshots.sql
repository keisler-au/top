BEGIN;

-- New article associations are stable published-taxonomy snapshots.  Legacy
-- columns remain only for the controlled compatibility period and are never
-- selected for a newly created article or generation job.
ALTER TABLE article_themes ADD COLUMN stable_theme_id BIGINT REFERENCES theme_identities(id) ON DELETE RESTRICT;
ALTER TABLE article_themes ADD COLUMN theme_name_snapshot TEXT;
ALTER TABLE article_topics ADD COLUMN topic_name_snapshot TEXT;
ALTER TABLE article_topics ADD COLUMN taxonomy_run_id BIGINT REFERENCES taxonomy_runs(id) ON DELETE RESTRICT;
ALTER TABLE article_evidence ADD COLUMN taxonomy_run_id BIGINT REFERENCES taxonomy_runs(id) ON DELETE RESTRICT;
ALTER TABLE article_generation_jobs ADD COLUMN taxonomy_run_id BIGINT REFERENCES taxonomy_runs(id) ON DELETE RESTRICT;
ALTER TABLE article_generation_jobs ADD COLUMN stable_theme_id BIGINT REFERENCES theme_identities(id) ON DELETE RESTRICT;
ALTER TABLE article_generation_job_evidence ADD COLUMN taxonomy_run_id BIGINT REFERENCES taxonomy_runs(id) ON DELETE RESTRICT;

CREATE INDEX idx_article_themes_stable_theme ON article_themes(stable_theme_id, article_id) WHERE stable_theme_id IS NOT NULL;
CREATE INDEX idx_article_topics_run_topic ON article_topics(taxonomy_run_id, topic_id, article_id) WHERE taxonomy_run_id IS NOT NULL AND topic_id IS NOT NULL;

CREATE OR REPLACE FUNCTION require_article_taxonomy_snapshot() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.stable_theme_id IS NOT NULL AND (NEW.theme_name_snapshot IS NULL OR btrim(NEW.theme_name_snapshot)='') THEN RAISE EXCEPTION 'stable theme associations require a display snapshot'; END IF;
  RETURN NEW;
END; $$;
CREATE TRIGGER article_theme_snapshot_required BEFORE INSERT OR UPDATE ON article_themes FOR EACH ROW EXECUTE FUNCTION require_article_taxonomy_snapshot();
COMMIT;
