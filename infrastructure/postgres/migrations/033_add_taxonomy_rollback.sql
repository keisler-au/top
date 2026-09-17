BEGIN;
ALTER TABLE taxonomy_runs DROP CONSTRAINT taxonomy_runs_status_check;
ALTER TABLE taxonomy_runs ADD CONSTRAINT taxonomy_runs_status_check CHECK (status IN ('pending','running','ready_for_review','published','superseded','rejected','failed'));
ALTER TABLE taxonomy_runs DROP CONSTRAINT taxonomy_runs_decision_consistent;
ALTER TABLE taxonomy_runs ADD CONSTRAINT taxonomy_runs_decision_consistent CHECK ((status IN ('published','superseded','rejected')) = (decision_by IS NOT NULL AND decision_at IS NOT NULL));
ALTER TABLE taxonomy_runs DROP CONSTRAINT taxonomy_runs_completion_consistent;
ALTER TABLE taxonomy_runs ADD CONSTRAINT taxonomy_runs_completion_consistent CHECK ((status IN ('ready_for_review','published','superseded','rejected')) = (completed_at IS NOT NULL));
CREATE TABLE taxonomy_rollback_decisions (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, from_run_id BIGINT NOT NULL REFERENCES taxonomy_runs(id), to_run_id BIGINT NOT NULL REFERENCES taxonomy_runs(id), decided_by TEXT NOT NULL, decided_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, note TEXT, UNIQUE(from_run_id,to_run_id), CHECK(from_run_id<>to_run_id));
CREATE OR REPLACE FUNCTION protect_taxonomy_run() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.source_cutoff IS DISTINCT FROM OLD.source_cutoff OR NEW.source_snapshot_sha256 IS DISTINCT FROM OLD.source_snapshot_sha256 OR NEW.configuration::text IS DISTINCT FROM OLD.configuration::text OR NEW.configuration_sha256 IS DISTINCT FROM OLD.configuration_sha256 THEN RAISE EXCEPTION 'taxonomy run provenance is immutable'; END IF;
 IF current_setting('taxonomy.rollback',true)='on' THEN NEW.updated_at:=CURRENT_TIMESTAMP; RETURN NEW; END IF;
 IF OLD.status IN ('published','superseded','rejected') THEN RAISE EXCEPTION 'final taxonomy runs are immutable'; END IF;
 IF NOT ((OLD.status='pending' AND NEW.status IN ('pending','running','rejected','failed')) OR (OLD.status='running' AND NEW.status IN ('running','ready_for_review','failed')) OR (OLD.status='failed' AND NEW.status IN ('failed','running','rejected')) OR (OLD.status='ready_for_review' AND NEW.status IN ('ready_for_review','published','rejected'))) THEN RAISE EXCEPTION 'invalid taxonomy run state transition'; END IF;
 NEW.updated_at:=CURRENT_TIMESTAMP; RETURN NEW;
END; $$;
CREATE OR REPLACE FUNCTION rollback_taxonomy_run(target_run_id BIGINT, operator_name TEXT, operator_note TEXT DEFAULT NULL) RETURNS taxonomy_runs LANGUAGE plpgsql AS $$
DECLARE current_run taxonomy_runs; target taxonomy_runs;
BEGIN
 SELECT * INTO current_run FROM taxonomy_runs WHERE status='published' FOR UPDATE;
 SELECT * INTO target FROM taxonomy_runs WHERE id=target_run_id AND status='superseded' FOR UPDATE;
 IF NOT FOUND OR current_run.id=target_run_id THEN RAISE EXCEPTION 'rollback target is not an eligible prior run'; END IF;
 IF btrim(operator_name)='' THEN RAISE EXCEPTION 'operator name is required'; END IF;
 PERFORM set_config('taxonomy.rollback','on',true);
 UPDATE taxonomy_runs SET status='superseded', decision_by=operator_name, decision_at=CURRENT_TIMESTAMP, decision_note=operator_note WHERE id=current_run.id;
 UPDATE taxonomy_runs SET status='published', decision_by=operator_name, decision_at=CURRENT_TIMESTAMP, decision_note=operator_note, published_at=CURRENT_TIMESTAMP WHERE id=target_run_id RETURNING * INTO target;
 INSERT INTO taxonomy_rollback_decisions(from_run_id,to_run_id,decided_by,note) VALUES(current_run.id,target_run_id,operator_name,operator_note) ON CONFLICT DO NOTHING;
 RETURN target;
END; $$;
COMMIT;
