BEGIN;

CREATE TABLE operations_rate_limit_windows (
    scope TEXT NOT NULL CHECK (scope IN ('operations_read', 'taxonomy_mutation')),
    actor_sha256 TEXT NOT NULL CHECK (actor_sha256 ~ '^[0-9a-f]{64}$'),
    window_started_at TIMESTAMPTZ NOT NULL,
    request_count INTEGER NOT NULL CHECK (request_count > 0),
    PRIMARY KEY (scope, actor_sha256, window_started_at)
);

CREATE INDEX idx_operations_rate_limit_windows_expiry
    ON operations_rate_limit_windows (window_started_at);

CREATE OR REPLACE FUNCTION consume_operations_rate_limit(
    limit_scope TEXT,
    actor_hash TEXT,
    window_seconds INTEGER,
    maximum_requests INTEGER
) RETURNS INTEGER LANGUAGE plpgsql AS $$
DECLARE window_start TIMESTAMPTZ; consumed INTEGER;
BEGIN
    IF window_seconds < 1 OR maximum_requests < 1 THEN
        RAISE EXCEPTION 'invalid operations rate-limit configuration';
    END IF;
    window_start := date_trunc('second', CURRENT_TIMESTAMP)
        - ((extract(epoch FROM CURRENT_TIMESTAMP)::BIGINT % window_seconds) * INTERVAL '1 second');
    INSERT INTO operations_rate_limit_windows(scope, actor_sha256, window_started_at, request_count)
    VALUES (limit_scope, actor_hash, window_start, 1)
    ON CONFLICT (scope, actor_sha256, window_started_at)
    DO UPDATE SET request_count = operations_rate_limit_windows.request_count + 1
    RETURNING request_count INTO consumed;
    DELETE FROM operations_rate_limit_windows
    WHERE window_started_at < CURRENT_TIMESTAMP - INTERVAL '2 days';
    RETURN consumed;
END;
$$;

COMMIT;
