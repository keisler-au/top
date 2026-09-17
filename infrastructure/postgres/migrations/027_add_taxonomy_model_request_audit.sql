BEGIN;

-- Each external model call has an immutable request identity before it is
-- issued.  Responses are separate immutable records, so an interrupted worker
-- can safely reuse the same identity without rewriting candidate history.
CREATE TABLE taxonomy_model_requests (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    taxonomy_run_id BIGINT NOT NULL REFERENCES taxonomy_runs (id) ON DELETE RESTRICT,
    stage TEXT NOT NULL CHECK (stage IN ('topic_naming', 'theme_inference')),
    request_key TEXT NOT NULL CHECK (btrim(request_key) <> '' AND char_length(request_key) <= 500),
    model TEXT NOT NULL CHECK (btrim(model) <> ''),
    prompt_version TEXT NOT NULL CHECK (btrim(prompt_version) <> ''),
    prompt_sha256 TEXT NOT NULL CHECK (prompt_sha256 ~ '^[0-9a-f]{64}$'),
    request_context JSONB NOT NULL CHECK (jsonb_typeof(request_context) = 'object'),
    request_sha256 TEXT NOT NULL CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (taxonomy_run_id, stage, request_key)
);

CREATE TABLE taxonomy_model_responses (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    taxonomy_run_id BIGINT NOT NULL REFERENCES taxonomy_runs (id) ON DELETE RESTRICT,
    taxonomy_model_request_id BIGINT NOT NULL UNIQUE REFERENCES taxonomy_model_requests (id) ON DELETE RESTRICT,
    raw_response JSONB NOT NULL CHECK (jsonb_typeof(raw_response) = 'object'),
    validation_errors TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    accepted BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (accepted = (cardinality(validation_errors) = 0))
);

CREATE TRIGGER taxonomy_model_requests_guard
BEFORE INSERT OR UPDATE OR DELETE ON taxonomy_model_requests
FOR EACH ROW EXECUTE FUNCTION guard_taxonomy_run_child();

CREATE TRIGGER taxonomy_model_responses_guard
BEFORE INSERT OR UPDATE OR DELETE ON taxonomy_model_responses
FOR EACH ROW EXECUTE FUNCTION guard_taxonomy_run_child();

COMMIT;
