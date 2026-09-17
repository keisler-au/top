BEGIN;
CREATE TABLE taxonomy_quality_snapshots (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    taxonomy_run_id BIGINT NOT NULL REFERENCES taxonomy_runs (id) ON DELETE RESTRICT,
    signals JSONB NOT NULL CHECK (jsonb_typeof(signals) = 'object'),
    gate_passed BOOLEAN NOT NULL,
    failures TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_taxonomy_quality_snapshots_run_created
    ON taxonomy_quality_snapshots (taxonomy_run_id, created_at DESC);
COMMIT;
