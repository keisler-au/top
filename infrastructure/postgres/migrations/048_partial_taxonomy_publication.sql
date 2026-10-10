BEGIN;

CREATE FUNCTION require_partial_taxonomy_attestation(candidate_run_id BIGINT) RETURNS VOID
LANGUAGE plpgsql AS $$
DECLARE gate taxonomy_release_attestations; current_facts JSONB;
BEGIN
 SELECT * INTO gate FROM taxonomy_release_attestations WHERE taxonomy_run_id=candidate_run_id AND gate_passed FOR SHARE;
 IF NOT FOUND OR gate.threshold_version <> 'taxonomy-release-gate-v3'
    OR gate.thresholds <> '{"minimum_canonical_topic_count":1,"require_internal_consistency":true}'::jsonb
    OR cardinality(gate.failures) <> 0 THEN
   RAISE EXCEPTION 'taxonomy publication requires a passing current-version attestation';
 END IF;
 current_facts := taxonomy_publication_facts(candidate_run_id);
 IF jsonb_array_length(current_facts->'integrity_failures') <> 0 OR NOT gate.metrics @> current_facts THEN
   RAISE EXCEPTION 'taxonomy publication facts changed or are inconsistent';
 END IF;
END; $$;

-- Share the swap lock across human and automatic callers. A waiting request
-- for a different candidate must review the newly published run before retry;
-- delivery of the same candidate remains an idempotent success.
CREATE FUNCTION lock_taxonomy_publication(candidate_run_id BIGINT) RETURNS VOID
LANGUAGE plpgsql AS $$
DECLARE observed_run_id BIGINT; current_run_id BIGINT;
BEGIN
 IF pg_try_advisory_xact_lock(hashtext('taxonomy-publication')) THEN RETURN; END IF;
 SELECT id INTO observed_run_id FROM taxonomy_runs WHERE status='published';
 PERFORM pg_advisory_xact_lock(hashtext('taxonomy-publication'));
 SELECT id INTO current_run_id FROM taxonomy_runs WHERE status='published';
 IF current_run_id IS DISTINCT FROM observed_run_id AND current_run_id IS DISTINCT FROM candidate_run_id THEN
   RAISE EXCEPTION 'concurrent taxonomy publication changed the current run';
 END IF;
END; $$;

CREATE OR REPLACE FUNCTION publish_taxonomy_run(candidate_run_id BIGINT, expected_updated_at TIMESTAMPTZ, operator_name TEXT, operator_note TEXT DEFAULT NULL)
RETURNS taxonomy_runs LANGUAGE plpgsql AS $$
DECLARE published taxonomy_runs; gate taxonomy_release_attestations;
BEGIN
    PERFORM lock_taxonomy_publication(candidate_run_id);
    IF EXISTS (SELECT 1 FROM taxonomy_runs WHERE id=candidate_run_id AND status='published') THEN
        SELECT * INTO published FROM taxonomy_runs WHERE id=candidate_run_id; RETURN published;
    END IF;
    PERFORM require_partial_taxonomy_attestation(candidate_run_id);
    SELECT * INTO gate FROM taxonomy_release_attestations WHERE taxonomy_run_id=candidate_run_id AND gate_passed FOR SHARE;
    IF NOT FOUND THEN RAISE EXCEPTION 'taxonomy publication gate is not attested'; END IF;
    SELECT * INTO published FROM taxonomy_runs WHERE id=candidate_run_id AND status='ready_for_review' AND updated_at=expected_updated_at FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'taxonomy run is no longer ready for review'; END IF;
    IF operator_name IS NULL OR btrim(operator_name)='' THEN RAISE EXCEPTION 'operator name is required'; END IF;
    IF NOT EXISTS (SELECT 1 FROM topic_revisions WHERE taxonomy_run_id=candidate_run_id) THEN RAISE EXCEPTION 'taxonomy run has no accepted topics'; END IF;
    PERFORM materialize_taxonomy_theme_revisions(candidate_run_id);
    INSERT INTO topic_aliases(topic_id,alias,normalized_alias,created_in_run_id)
      SELECT topic_id,name,normalized_name,candidate_run_id FROM topic_revisions WHERE taxonomy_run_id=candidate_run_id ON CONFLICT DO NOTHING;
    PERFORM set_config('taxonomy.automatic_publish','on',true);
    UPDATE taxonomy_runs SET status='superseded' WHERE status='published' AND id<>candidate_run_id;
    UPDATE taxonomy_runs SET status='published',decision_by=operator_name,decision_at=CURRENT_TIMESTAMP,decision_note=operator_note,published_at=CURRENT_TIMESTAMP WHERE id=candidate_run_id RETURNING * INTO published;
    INSERT INTO taxonomy_publication_decisions(taxonomy_run_id,gate_input_sha256,threshold_version,decided_by,decision_note)
      VALUES(candidate_run_id,gate.input_sha256,gate.threshold_version,operator_name,operator_note);
    RETURN published;
END;
$$;

CREATE OR REPLACE FUNCTION publish_taxonomy_run_automatically(
    candidate_run_id BIGINT, policy_version TEXT
) RETURNS taxonomy_runs LANGUAGE plpgsql AS $$
DECLARE candidate taxonomy_runs; prior taxonomy_runs; gate taxonomy_release_attestations;
BEGIN
    PERFORM lock_taxonomy_publication(candidate_run_id);
    IF policy_version IS NULL OR btrim(policy_version) = '' THEN RAISE EXCEPTION 'automation policy version is required'; END IF;
    SELECT * INTO candidate FROM taxonomy_runs WHERE id=candidate_run_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'taxonomy run not found'; END IF;
    IF candidate.status='published' THEN RETURN candidate; END IF;
    PERFORM require_partial_taxonomy_attestation(candidate_run_id);
    IF candidate.status <> 'ready_for_review' THEN RAISE EXCEPTION 'taxonomy run is not ready for automatic publication'; END IF;
    SELECT * INTO gate FROM taxonomy_release_attestations
      WHERE taxonomy_run_id=candidate_run_id AND gate_passed FOR SHARE;
    IF NOT FOUND THEN RAISE EXCEPTION 'taxonomy publication gate is not attested'; END IF;
    IF NOT EXISTS (
        SELECT 1 FROM taxonomy_automation_decisions
        WHERE taxonomy_run_id=candidate_run_id
          AND idempotency_key LIKE 'automatic:%'
          AND taxonomy_automation_decisions.policy_version=$2
          AND status IN ('snapshotted','reserved')
    ) THEN RAISE EXCEPTION 'taxonomy run has no matching automatic decision'; END IF;
    IF NOT EXISTS (SELECT 1 FROM topic_revisions WHERE taxonomy_run_id=candidate_run_id) THEN RAISE EXCEPTION 'taxonomy run has no accepted topics'; END IF;
    PERFORM materialize_taxonomy_theme_revisions(candidate_run_id);
    SELECT * INTO prior FROM taxonomy_runs WHERE status='published' FOR UPDATE;
    PERFORM set_config('taxonomy.automatic_publish','on',true);
    IF prior.id IS NOT NULL THEN UPDATE taxonomy_runs SET status='superseded' WHERE id=prior.id; END IF;
    INSERT INTO topic_aliases(topic_id,alias,normalized_alias,created_in_run_id)
      SELECT topic_id,name,normalized_name,candidate_run_id FROM topic_revisions
      WHERE taxonomy_run_id=candidate_run_id ON CONFLICT DO NOTHING;
    UPDATE taxonomy_runs SET status='published',decision_by='taxonomy-automation',
      decision_at=CURRENT_TIMESTAMP,decision_note='automatic quality-gated publication',
      published_at=CURRENT_TIMESTAMP WHERE id=candidate_run_id RETURNING * INTO candidate;
    INSERT INTO taxonomy_publication_decisions(
      taxonomy_run_id,gate_input_sha256,threshold_version,decided_by,decision_note,
      decision_kind,automation_policy_version
    ) VALUES(candidate_run_id,gate.input_sha256,gate.threshold_version,
      'taxonomy-automation','automatic quality-gated publication','automatic',policy_version)
    ON CONFLICT (taxonomy_run_id) DO NOTHING;
    RETURN candidate;
END;
$$;


CREATE OR REPLACE FUNCTION rollback_taxonomy_run(target_run_id BIGINT, operator_name TEXT, operator_note TEXT DEFAULT NULL) RETURNS taxonomy_runs LANGUAGE plpgsql AS $$
DECLARE current_run taxonomy_runs; target taxonomy_runs;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtext('taxonomy-publication'));
 SELECT * INTO current_run FROM taxonomy_runs WHERE status='published' FOR UPDATE;
 IF current_run.id=target_run_id THEN RETURN current_run; END IF;
 SELECT * INTO target FROM taxonomy_runs WHERE id=target_run_id AND status='superseded' FOR UPDATE;
 IF NOT FOUND OR current_run.id=target_run_id THEN RAISE EXCEPTION 'rollback target is not an eligible prior run'; END IF;
 IF operator_name IS NULL OR btrim(operator_name)='' THEN RAISE EXCEPTION 'operator name is required'; END IF;
 PERFORM set_config('taxonomy.rollback','on',true);
 UPDATE taxonomy_runs SET status='superseded', decision_by=operator_name, decision_at=CURRENT_TIMESTAMP, decision_note=operator_note WHERE id=current_run.id;
 UPDATE taxonomy_runs SET status='published', decision_by=operator_name, decision_at=CURRENT_TIMESTAMP, decision_note=operator_note, published_at=CURRENT_TIMESTAMP WHERE id=target_run_id RETURNING * INTO target;
 INSERT INTO taxonomy_rollback_decisions(from_run_id,to_run_id,decided_by,note) VALUES(current_run.id,target_run_id,operator_name,operator_note) ON CONFLICT DO NOTHING;
 RETURN target;
END; $$;

COMMIT;
