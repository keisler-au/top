BEGIN;

-- This schema is an immutable audit snapshot, not a second live taxonomy.
-- Keep original legacy identifiers so an auditor can follow historical links
-- after BT-WP7c removes the mutable source tables.
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;
ALTER EXTENSION pgcrypto SET SCHEMA public;
CREATE SCHEMA IF NOT EXISTS taxonomy_legacy_archive;
REVOKE ALL ON SCHEMA taxonomy_legacy_archive FROM PUBLIC;

CREATE TABLE taxonomy_legacy_archive.exports (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    format_version TEXT NOT NULL CHECK (format_version = 'taxonomy-legacy-archive-v1'),
    exported_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_cutoff TIMESTAMPTZ NOT NULL,
    table_counts JSONB NOT NULL,
    table_hashes JSONB NOT NULL,
    archive_sha256 TEXT NOT NULL CHECK (archive_sha256 ~ '^[0-9a-f]{64}$'),
    UNIQUE (format_version)
);

CREATE TABLE taxonomy_legacy_archive.input_topics (
    original_input_id BIGINT PRIMARY KEY, topic TEXT NOT NULL,
    original_created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE taxonomy_legacy_archive.segment_topics (
    segment_input_id BIGINT PRIMARY KEY, original_input_id BIGINT NOT NULL,
    topic TEXT NOT NULL, segment_created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE taxonomy_legacy_archive.themes (
    theme_id BIGINT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
    merged_into_id BIGINT, created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE taxonomy_legacy_archive.theme_topics (
    theme_id BIGINT NOT NULL, topic TEXT NOT NULL, PRIMARY KEY (theme_id, topic)
);
CREATE TABLE taxonomy_legacy_archive.theme_suggestions (
    suggestion_id BIGINT PRIMARY KEY, action TEXT NOT NULL, proposed_name TEXT NOT NULL,
    proposed_description TEXT NOT NULL, rationale TEXT NOT NULL, group_fingerprint TEXT NOT NULL,
    materialized_theme_id BIGINT, materialized_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE taxonomy_legacy_archive.suggestion_existing_themes (
    suggestion_id BIGINT NOT NULL, theme_id BIGINT NOT NULL,
    PRIMARY KEY (suggestion_id, theme_id)
);
CREATE TABLE taxonomy_legacy_archive.suggestion_topics (
    suggestion_id BIGINT NOT NULL, topic TEXT NOT NULL, PRIMARY KEY (suggestion_id, topic)
);
CREATE TABLE taxonomy_legacy_archive.suggestion_evidence (
    suggestion_evidence_id BIGINT PRIMARY KEY, suggestion_id BIGINT NOT NULL,
    original_input_id BIGINT, segment_input_id BIGINT,
    CHECK (num_nonnulls(original_input_id, segment_input_id) = 1)
);
-- Request/response payloads are intentionally not copied: they are not
-- needed to interpret a historical classification and must not escape through
-- the bounded audit export.
CREATE TABLE taxonomy_legacy_archive.assignment_attempts (
    assignment_attempt_id BIGINT PRIMARY KEY, assignment_run_id UUID NOT NULL,
    original_input_id BIGINT NOT NULL, attempt_number INTEGER NOT NULL,
    model TEXT NOT NULL, prompt_version TEXT NOT NULL, prompt_sha256 TEXT NOT NULL,
    validation_errors TEXT[] NOT NULL, accepted BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE OR REPLACE FUNCTION taxonomy_legacy_archive.table_sha256(table_name TEXT)
RETURNS TEXT LANGUAGE plpgsql STABLE AS $$
DECLARE digest_value TEXT;
BEGIN
    EXECUTE format(
        'SELECT encode(public.digest(COALESCE(string_agg(row_json::text, E''\\n'' ORDER BY row_json::text), ''''), ''sha256''), ''hex'')
           FROM (SELECT to_jsonb(t) AS row_json FROM taxonomy_legacy_archive.%I AS t) rows',
        table_name
    ) INTO digest_value;
    RETURN digest_value;
END;
$$;

INSERT INTO taxonomy_legacy_archive.input_topics
SELECT id, topic, created_at FROM original_inputs WHERE topic IS NOT NULL;
INSERT INTO taxonomy_legacy_archive.segment_topics
SELECT id, original_input_id, topic, created_at FROM segment_inputs WHERE topic IS NOT NULL;
INSERT INTO taxonomy_legacy_archive.themes
SELECT id, name, description, merged_into_id, created_at, updated_at FROM themes;
INSERT INTO taxonomy_legacy_archive.theme_topics SELECT theme_id, topic FROM theme_topics;
INSERT INTO taxonomy_legacy_archive.theme_suggestions
SELECT id, action, proposed_name, proposed_description, rationale, group_fingerprint,
       materialized_theme_id, materialized_at, created_at FROM theme_suggestions;
INSERT INTO taxonomy_legacy_archive.suggestion_existing_themes
SELECT suggestion_id, theme_id FROM theme_suggestion_existing_themes;
INSERT INTO taxonomy_legacy_archive.suggestion_topics SELECT suggestion_id, topic FROM theme_suggestion_topics;
INSERT INTO taxonomy_legacy_archive.suggestion_evidence
SELECT id, suggestion_id, original_input_id, segment_input_id FROM theme_suggestion_evidence;
INSERT INTO taxonomy_legacy_archive.assignment_attempts
SELECT id, assignment_run_id, original_input_id, attempt_number, model, prompt_version,
       prompt_sha256, validation_errors, accepted, created_at FROM topic_assignment_attempts;

DO $$
BEGIN
  IF (SELECT count(*) FROM original_inputs WHERE topic IS NOT NULL) <> (SELECT count(*) FROM taxonomy_legacy_archive.input_topics)
     OR (SELECT count(*) FROM segment_inputs WHERE topic IS NOT NULL) <> (SELECT count(*) FROM taxonomy_legacy_archive.segment_topics)
     OR (SELECT count(*) FROM themes) <> (SELECT count(*) FROM taxonomy_legacy_archive.themes)
     OR (SELECT count(*) FROM theme_topics) <> (SELECT count(*) FROM taxonomy_legacy_archive.theme_topics)
     OR (SELECT count(*) FROM theme_suggestions) <> (SELECT count(*) FROM taxonomy_legacy_archive.theme_suggestions)
     OR (SELECT count(*) FROM theme_suggestion_existing_themes) <> (SELECT count(*) FROM taxonomy_legacy_archive.suggestion_existing_themes)
     OR (SELECT count(*) FROM theme_suggestion_topics) <> (SELECT count(*) FROM taxonomy_legacy_archive.suggestion_topics)
     OR (SELECT count(*) FROM theme_suggestion_evidence) <> (SELECT count(*) FROM taxonomy_legacy_archive.suggestion_evidence)
     OR (SELECT count(*) FROM topic_assignment_attempts) <> (SELECT count(*) FROM taxonomy_legacy_archive.assignment_attempts)
  THEN RAISE EXCEPTION 'legacy archive row-count validation failed'; END IF;
END;
$$;

WITH hashes AS (
    SELECT jsonb_build_object(
        'input_topics', taxonomy_legacy_archive.table_sha256('input_topics'),
        'segment_topics', taxonomy_legacy_archive.table_sha256('segment_topics'),
        'themes', taxonomy_legacy_archive.table_sha256('themes'),
        'theme_topics', taxonomy_legacy_archive.table_sha256('theme_topics'),
        'theme_suggestions', taxonomy_legacy_archive.table_sha256('theme_suggestions'),
        'suggestion_existing_themes', taxonomy_legacy_archive.table_sha256('suggestion_existing_themes'),
        'suggestion_topics', taxonomy_legacy_archive.table_sha256('suggestion_topics'),
        'suggestion_evidence', taxonomy_legacy_archive.table_sha256('suggestion_evidence'),
        'assignment_attempts', taxonomy_legacy_archive.table_sha256('assignment_attempts')
    ) AS value
), counts AS (
    SELECT jsonb_build_object(
        'input_topics', (SELECT count(*) FROM taxonomy_legacy_archive.input_topics),
        'segment_topics', (SELECT count(*) FROM taxonomy_legacy_archive.segment_topics),
        'themes', (SELECT count(*) FROM taxonomy_legacy_archive.themes),
        'theme_topics', (SELECT count(*) FROM taxonomy_legacy_archive.theme_topics),
        'theme_suggestions', (SELECT count(*) FROM taxonomy_legacy_archive.theme_suggestions),
        'suggestion_existing_themes', (SELECT count(*) FROM taxonomy_legacy_archive.suggestion_existing_themes),
        'suggestion_topics', (SELECT count(*) FROM taxonomy_legacy_archive.suggestion_topics),
        'suggestion_evidence', (SELECT count(*) FROM taxonomy_legacy_archive.suggestion_evidence),
        'assignment_attempts', (SELECT count(*) FROM taxonomy_legacy_archive.assignment_attempts)
    ) AS value
)
INSERT INTO taxonomy_legacy_archive.exports(format_version, source_cutoff, table_counts, table_hashes, archive_sha256)
SELECT 'taxonomy-legacy-archive-v1', CURRENT_TIMESTAMP, counts.value, hashes.value,
       encode(public.digest((counts.value::text || E'\n' || hashes.value::text), 'sha256'), 'hex')
FROM counts, hashes;

CREATE OR REPLACE FUNCTION taxonomy_legacy_archive.reject_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'taxonomy legacy archive is immutable'; END;
$$;
CREATE OR REPLACE FUNCTION taxonomy_legacy_archive.install_immutability()
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE table_name TEXT;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['exports','input_topics','segment_topics','themes','theme_topics','theme_suggestions','suggestion_existing_themes','suggestion_topics','suggestion_evidence','assignment_attempts']
  LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON taxonomy_legacy_archive.%I FOR EACH STATEMENT EXECUTE FUNCTION taxonomy_legacy_archive.reject_mutation()', table_name || '_immutable', table_name);
  END LOOP;
END;
$$;
SELECT taxonomy_legacy_archive.install_immutability();
DROP FUNCTION taxonomy_legacy_archive.install_immutability();

REVOKE ALL ON ALL TABLES IN SCHEMA taxonomy_legacy_archive FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA taxonomy_legacy_archive FROM PUBLIC;
COMMIT;
