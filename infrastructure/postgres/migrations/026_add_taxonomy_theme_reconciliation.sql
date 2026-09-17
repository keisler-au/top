BEGIN;

-- Reconciliation is a distinct immutable layer over raw model candidates.
-- It consolidates equivalent candidates without modifying their model output.
CREATE TABLE taxonomy_reconciled_themes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    taxonomy_run_id BIGINT NOT NULL REFERENCES taxonomy_runs (id) ON DELETE RESTRICT,
    canonical_candidate_theme_id BIGINT NOT NULL,
    normalized_name TEXT NOT NULL CHECK (btrim(normalized_name) <> ''),
    topic_set_sha256 TEXT NOT NULL CHECK (topic_set_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (taxonomy_run_id, id),
    UNIQUE (taxonomy_run_id, canonical_candidate_theme_id),
    UNIQUE (taxonomy_run_id, normalized_name, topic_set_sha256),
    FOREIGN KEY (taxonomy_run_id, canonical_candidate_theme_id)
        REFERENCES taxonomy_candidate_themes (taxonomy_run_id, id) ON DELETE RESTRICT
);

CREATE TABLE taxonomy_reconciled_theme_antecedents (
    taxonomy_run_id BIGINT NOT NULL,
    reconciled_theme_id BIGINT NOT NULL,
    candidate_theme_id BIGINT NOT NULL,
    relationship TEXT NOT NULL CHECK (relationship IN ('canonical', 'consolidated_duplicate')),
    PRIMARY KEY (taxonomy_run_id, reconciled_theme_id, candidate_theme_id),
    FOREIGN KEY (taxonomy_run_id, reconciled_theme_id)
        REFERENCES taxonomy_reconciled_themes (taxonomy_run_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (taxonomy_run_id, candidate_theme_id)
        REFERENCES taxonomy_candidate_themes (taxonomy_run_id, id) ON DELETE RESTRICT
);

CREATE TRIGGER reconciled_themes_guard
BEFORE INSERT OR UPDATE OR DELETE ON taxonomy_reconciled_themes
FOR EACH ROW EXECUTE FUNCTION guard_taxonomy_run_child();
CREATE TRIGGER reconciled_theme_antecedents_guard
BEFORE INSERT OR UPDATE OR DELETE ON taxonomy_reconciled_theme_antecedents
FOR EACH ROW EXECUTE FUNCTION guard_taxonomy_run_child();

COMMIT;
