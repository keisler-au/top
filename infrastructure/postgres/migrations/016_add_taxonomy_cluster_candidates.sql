BEGIN;

CREATE TABLE taxonomy_cluster_candidates (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    taxonomy_run_id BIGINT NOT NULL REFERENCES taxonomy_runs (id) ON DELETE RESTRICT,
    cluster_key TEXT NOT NULL CHECK (btrim(cluster_key) <> ''),
    algorithm_label INTEGER NOT NULL CHECK (algorithm_label >= 0),
    member_count INTEGER NOT NULL CHECK (member_count >= 2),
    centroid VECTOR NOT NULL,
    diagnostics JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(diagnostics) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (taxonomy_run_id, id),
    UNIQUE (taxonomy_run_id, cluster_key),
    UNIQUE (taxonomy_run_id, algorithm_label)
);

CREATE TABLE taxonomy_cluster_memberships (
    taxonomy_run_id BIGINT NOT NULL,
    cluster_candidate_id BIGINT,
    evidence_id BIGINT NOT NULL,
    membership_confidence DOUBLE PRECISION CHECK (membership_confidence IS NULL OR membership_confidence BETWEEN 0 AND 1),
    decision TEXT NOT NULL CHECK (decision IN ('clustered', 'noise')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (taxonomy_run_id, evidence_id),
    FOREIGN KEY (taxonomy_run_id, cluster_candidate_id) REFERENCES taxonomy_cluster_candidates (taxonomy_run_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (taxonomy_run_id, evidence_id) REFERENCES taxonomy_run_evidence (taxonomy_run_id, id) ON DELETE RESTRICT,
    CHECK ((decision = 'noise') = (cluster_candidate_id IS NULL))
);
CREATE INDEX idx_taxonomy_cluster_memberships_cluster ON taxonomy_cluster_memberships (taxonomy_run_id, cluster_candidate_id) WHERE cluster_candidate_id IS NOT NULL;

CREATE TABLE taxonomy_cluster_representatives (
    taxonomy_run_id BIGINT NOT NULL,
    cluster_candidate_id BIGINT NOT NULL,
    evidence_id BIGINT NOT NULL,
    representative_order INTEGER NOT NULL CHECK (representative_order >= 0),
    selection_kind TEXT NOT NULL CHECK (selection_kind IN ('central', 'diverse')),
    PRIMARY KEY (taxonomy_run_id, cluster_candidate_id, evidence_id),
    UNIQUE (taxonomy_run_id, cluster_candidate_id, representative_order),
    FOREIGN KEY (taxonomy_run_id, cluster_candidate_id) REFERENCES taxonomy_cluster_candidates (taxonomy_run_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (taxonomy_run_id, evidence_id) REFERENCES taxonomy_run_evidence (taxonomy_run_id, id) ON DELETE RESTRICT
);

CREATE TRIGGER cluster_candidates_guard BEFORE INSERT OR UPDATE OR DELETE ON taxonomy_cluster_candidates FOR EACH ROW EXECUTE FUNCTION guard_taxonomy_run_child();
CREATE TRIGGER cluster_memberships_guard BEFORE INSERT OR UPDATE OR DELETE ON taxonomy_cluster_memberships FOR EACH ROW EXECUTE FUNCTION guard_taxonomy_run_child();
CREATE TRIGGER cluster_representatives_guard BEFORE INSERT OR UPDATE OR DELETE ON taxonomy_cluster_representatives FOR EACH ROW EXECUTE FUNCTION guard_taxonomy_run_child();

CREATE OR REPLACE FUNCTION validate_cluster_representative() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM taxonomy_cluster_memberships
        WHERE taxonomy_run_id=NEW.taxonomy_run_id
          AND cluster_candidate_id=NEW.cluster_candidate_id
          AND evidence_id=NEW.evidence_id
          AND decision='clustered'
    ) THEN RAISE EXCEPTION 'representative must be a member of its candidate cluster'; END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER cluster_representative_valid BEFORE INSERT OR UPDATE ON taxonomy_cluster_representatives FOR EACH ROW EXECUTE FUNCTION validate_cluster_representative();

COMMIT;
