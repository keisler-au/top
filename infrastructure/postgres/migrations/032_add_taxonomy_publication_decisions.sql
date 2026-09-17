BEGIN;

CREATE TABLE taxonomy_publication_decisions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    taxonomy_run_id BIGINT NOT NULL UNIQUE REFERENCES taxonomy_runs(id) ON DELETE RESTRICT,
    gate_input_sha256 TEXT NOT NULL CHECK (gate_input_sha256 ~ '^[0-9a-f]{64}$'),
    threshold_version TEXT NOT NULL CHECK (btrim(threshold_version) <> ''),
    decided_by TEXT NOT NULL CHECK (btrim(decided_by) <> ''),
    decided_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    decision_note TEXT
);
CREATE OR REPLACE FUNCTION reject_taxonomy_publication_decision_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'taxonomy publication decisions are immutable'; END; $$;
CREATE TRIGGER taxonomy_publication_decisions_immutable BEFORE UPDATE OR DELETE
ON taxonomy_publication_decisions FOR EACH ROW EXECUTE FUNCTION reject_taxonomy_publication_decision_mutation();

CREATE OR REPLACE FUNCTION publish_taxonomy_run(candidate_run_id BIGINT, expected_updated_at TIMESTAMPTZ, operator_name TEXT, operator_note TEXT DEFAULT NULL)
RETURNS taxonomy_runs LANGUAGE plpgsql AS $$
DECLARE published taxonomy_runs; gate taxonomy_release_attestations;
BEGIN
    SELECT * INTO gate FROM taxonomy_release_attestations WHERE taxonomy_run_id=candidate_run_id AND gate_passed FOR SHARE;
    IF NOT FOUND THEN RAISE EXCEPTION 'taxonomy publication gate is not attested'; END IF;
    SELECT * INTO published FROM taxonomy_runs WHERE id=candidate_run_id AND status='ready_for_review' AND updated_at=expected_updated_at FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'taxonomy run is no longer ready for review'; END IF;
    IF btrim(operator_name)='' THEN RAISE EXCEPTION 'operator name is required'; END IF;
    IF NOT EXISTS (SELECT 1 FROM topic_revisions WHERE taxonomy_run_id=candidate_run_id) THEN RAISE EXCEPTION 'taxonomy run has no accepted topics'; END IF;
    PERFORM materialize_taxonomy_theme_revisions(candidate_run_id);
    INSERT INTO topic_aliases(topic_id,alias,normalized_alias,created_in_run_id)
      SELECT topic_id,name,normalized_name,candidate_run_id FROM topic_revisions WHERE taxonomy_run_id=candidate_run_id ON CONFLICT DO NOTHING;
    UPDATE taxonomy_runs SET status='published',decision_by=operator_name,decision_at=CURRENT_TIMESTAMP,decision_note=operator_note,published_at=CURRENT_TIMESTAMP WHERE id=candidate_run_id RETURNING * INTO published;
    INSERT INTO taxonomy_publication_decisions(taxonomy_run_id,gate_input_sha256,threshold_version,decided_by,decision_note)
      VALUES(candidate_run_id,gate.input_sha256,gate.threshold_version,operator_name,operator_note);
    RETURN published;
END;
$$;
COMMIT;
