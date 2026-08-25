BEGIN;

CREATE TABLE IF NOT EXISTS topic_assignment_attempts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    assignment_run_id UUID NOT NULL,
    original_input_id BIGINT NOT NULL
        REFERENCES original_inputs (id) ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL
        CONSTRAINT topic_assignment_attempts_number_positive
        CHECK (attempt_number >= 1),
    model TEXT NOT NULL
        CONSTRAINT topic_assignment_attempts_model_nonempty
        CHECK (btrim(model) <> ''),
    prompt_version TEXT NOT NULL
        CONSTRAINT topic_assignment_attempts_prompt_version_nonempty
        CHECK (btrim(prompt_version) <> ''),
    prompt_sha256 TEXT NOT NULL
        CONSTRAINT topic_assignment_attempts_prompt_sha256_valid
        CHECK (prompt_sha256 ~ '^[0-9a-f]{64}$'),
    request_context JSONB NOT NULL,
    raw_response JSONB NOT NULL,
    validation_errors TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    accepted BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT topic_assignment_attempts_run_attempt_unique
        UNIQUE (assignment_run_id, attempt_number),
    CONSTRAINT topic_assignment_attempts_acceptance_consistent
        CHECK (accepted = (cardinality(validation_errors) = 0))
);

CREATE INDEX IF NOT EXISTS idx_topic_assignment_attempts_input
    ON topic_assignment_attempts (original_input_id, created_at DESC);

COMMIT;
