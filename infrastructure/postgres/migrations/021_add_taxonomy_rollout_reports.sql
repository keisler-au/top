BEGIN;

CREATE TABLE taxonomy_rollout_reports (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    taxonomy_run_id BIGINT NOT NULL UNIQUE REFERENCES taxonomy_runs (id) ON DELETE RESTRICT,
    legacy_metrics JSONB NOT NULL CHECK (jsonb_typeof(legacy_metrics) = 'object'),
    candidate_metrics JSONB NOT NULL CHECK (jsonb_typeof(candidate_metrics) = 'object'),
    mappings JSONB NOT NULL CHECK (jsonb_typeof(mappings) = 'object'),
    generated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    signed_off_by TEXT CHECK (signed_off_by IS NULL OR btrim(signed_off_by) <> ''),
    signed_off_at TIMESTAMPTZ,
    sign_off_note TEXT,
    CHECK ((signed_off_by IS NULL) = (signed_off_at IS NULL))
);

CREATE OR REPLACE FUNCTION require_taxonomy_rollout_signoff() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status = 'published' AND NOT EXISTS (
        SELECT 1 FROM taxonomy_rollout_reports reports
        WHERE reports.taxonomy_run_id = NEW.id AND reports.signed_off_at IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'taxonomy run requires a signed-off rollout report before publication';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER taxonomy_runs_require_rollout_signoff
BEFORE UPDATE OF status ON taxonomy_runs FOR EACH ROW
WHEN (NEW.status = 'published') EXECUTE FUNCTION require_taxonomy_rollout_signoff();
COMMIT;
