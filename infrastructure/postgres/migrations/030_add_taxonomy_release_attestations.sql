BEGIN;

CREATE TABLE taxonomy_release_attestations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    taxonomy_run_id BIGINT NOT NULL UNIQUE REFERENCES taxonomy_runs(id) ON DELETE RESTRICT,
    metrics JSONB NOT NULL CHECK (jsonb_typeof(metrics) = 'object'),
    thresholds JSONB NOT NULL CHECK (jsonb_typeof(thresholds) = 'object'),
    threshold_version TEXT NOT NULL CHECK (btrim(threshold_version) <> ''),
    gate_passed BOOLEAN NOT NULL,
    failures TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    input_sha256 TEXT NOT NULL CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_taxonomy_release_attestations_gate
    ON taxonomy_release_attestations(taxonomy_run_id, gate_passed);

CREATE OR REPLACE FUNCTION reject_taxonomy_release_attestation_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'taxonomy release attestations are immutable'; END;
$$;
CREATE TRIGGER taxonomy_release_attestations_immutable
BEFORE UPDATE OR DELETE ON taxonomy_release_attestations
FOR EACH ROW EXECUTE FUNCTION reject_taxonomy_release_attestation_mutation();

-- The database gate prevents direct SQL callers from bypassing the
-- server-computed attestation. Deployment-default-off remains an API/runtime
-- setting because PostgreSQL does not receive process environment variables.
CREATE OR REPLACE FUNCTION publish_taxonomy_run(
    candidate_run_id BIGINT,
    expected_updated_at TIMESTAMPTZ,
    operator_name TEXT,
    operator_note TEXT DEFAULT NULL
) RETURNS taxonomy_runs LANGUAGE plpgsql AS $$
DECLARE published taxonomy_runs;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM taxonomy_release_attestations
        WHERE taxonomy_run_id = candidate_run_id AND gate_passed
    ) THEN RAISE EXCEPTION 'taxonomy publication gate is not attested'; END IF;
    PERFORM materialize_taxonomy_theme_revisions(candidate_run_id);
    SELECT * INTO published FROM taxonomy_runs
    WHERE id = candidate_run_id AND status = 'ready_for_review'
      AND updated_at = expected_updated_at FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'taxonomy run is no longer ready for review'; END IF;
    IF btrim(operator_name) = '' THEN RAISE EXCEPTION 'operator name is required'; END IF;
    IF NOT EXISTS (SELECT 1 FROM topic_revisions WHERE taxonomy_run_id = candidate_run_id) THEN RAISE EXCEPTION 'taxonomy run has no accepted topics'; END IF;
    INSERT INTO topic_aliases(topic_id, alias, normalized_alias, created_in_run_id)
    SELECT topic_id, name, normalized_name, candidate_run_id FROM topic_revisions
    WHERE taxonomy_run_id = candidate_run_id ON CONFLICT DO NOTHING;
    UPDATE taxonomy_runs SET status='published', decision_by=operator_name,
        decision_at=CURRENT_TIMESTAMP, decision_note=operator_note,
        published_at=CURRENT_TIMESTAMP WHERE id=candidate_run_id RETURNING * INTO published;
    RETURN published;
END;
$$;
COMMIT;
