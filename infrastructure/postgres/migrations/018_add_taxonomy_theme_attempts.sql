BEGIN;
CREATE TABLE taxonomy_theme_inference_attempts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    taxonomy_run_id BIGINT NOT NULL REFERENCES taxonomy_runs (id) ON DELETE RESTRICT,
    neighbourhood_key TEXT NOT NULL,
    model TEXT NOT NULL CHECK (btrim(model) <> ''),
    prompt_version TEXT NOT NULL CHECK (btrim(prompt_version) <> ''),
    prompt_sha256 TEXT NOT NULL CHECK (prompt_sha256 ~ '^[0-9a-f]{64}$'),
    request_context JSONB NOT NULL CHECK (jsonb_typeof(request_context) = 'object'),
    raw_response JSONB NOT NULL CHECK (jsonb_typeof(raw_response) = 'object'),
    validation_errors TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    accepted BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (taxonomy_run_id, neighbourhood_key),
    CHECK (accepted = (cardinality(validation_errors) = 0))
);
CREATE TRIGGER taxonomy_theme_attempts_guard BEFORE INSERT OR UPDATE OR DELETE ON taxonomy_theme_inference_attempts FOR EACH ROW EXECUTE FUNCTION guard_taxonomy_run_child();
COMMIT;
