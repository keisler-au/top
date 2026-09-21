BEGIN;

ALTER TABLE taxonomy_publication_decisions
    ADD COLUMN decision_kind TEXT NOT NULL DEFAULT 'manual'
        CHECK (decision_kind IN ('manual', 'automatic')),
    ADD COLUMN automation_policy_version TEXT;
ALTER TABLE taxonomy_publication_decisions
    ADD CONSTRAINT taxonomy_publication_decisions_actor_consistent CHECK (
        (decision_kind = 'manual' AND automation_policy_version IS NULL)
        OR (decision_kind = 'automatic' AND automation_policy_version IS NOT NULL)
    );

-- The existing protection is retained for human and rollback operations.  An
-- automatic promotion may only make its ready candidate published and retire
-- the one existing projection inside publish_taxonomy_run_automatically.
CREATE OR REPLACE FUNCTION protect_taxonomy_run() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.source_cutoff IS DISTINCT FROM OLD.source_cutoff OR NEW.source_snapshot_sha256 IS DISTINCT FROM OLD.source_snapshot_sha256 OR NEW.configuration::text IS DISTINCT FROM OLD.configuration::text OR NEW.configuration_sha256 IS DISTINCT FROM OLD.configuration_sha256 THEN RAISE EXCEPTION 'taxonomy run provenance is immutable'; END IF;
 IF current_setting('taxonomy.rollback',true)='on' THEN NEW.updated_at:=CURRENT_TIMESTAMP; RETURN NEW; END IF;
 IF current_setting('taxonomy.automatic_publish',true)='on' THEN
   IF (OLD.status='published' AND NEW.status='superseded') OR (OLD.status='ready_for_review' AND NEW.status='published') THEN NEW.updated_at:=CURRENT_TIMESTAMP; RETURN NEW; END IF;
   RAISE EXCEPTION 'invalid automatic taxonomy publication transition';
 END IF;
 IF OLD.status IN ('published','superseded','rejected') THEN RAISE EXCEPTION 'final taxonomy runs are immutable'; END IF;
 IF NOT ((OLD.status='pending' AND NEW.status IN ('pending','running','rejected','failed')) OR (OLD.status='running' AND NEW.status IN ('running','ready_for_review','failed')) OR (OLD.status='failed' AND NEW.status IN ('failed','running','rejected')) OR (OLD.status='ready_for_review' AND NEW.status IN ('ready_for_review','published','rejected'))) THEN RAISE EXCEPTION 'invalid taxonomy run state transition'; END IF;
 NEW.updated_at:=CURRENT_TIMESTAMP; RETURN NEW;
END; $$;

CREATE OR REPLACE FUNCTION publish_taxonomy_run_automatically(
    candidate_run_id BIGINT, policy_version TEXT
) RETURNS taxonomy_runs LANGUAGE plpgsql AS $$
DECLARE candidate taxonomy_runs; prior taxonomy_runs; gate taxonomy_release_attestations;
BEGIN
    IF btrim(policy_version) = '' THEN RAISE EXCEPTION 'automation policy version is required'; END IF;
    SELECT * INTO candidate FROM taxonomy_runs WHERE id=candidate_run_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'taxonomy run not found'; END IF;
    IF candidate.status='published' THEN RETURN candidate; END IF;
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
    IF FOUND THEN UPDATE taxonomy_runs SET status='superseded' WHERE id=prior.id; END IF;
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

COMMIT;
