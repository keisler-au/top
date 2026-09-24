BEGIN;

-- Keep all requests in one fixed window. The former bigint cast rounded the
-- epoch while date_trunc rounded down, producing adjacent window keys around
-- a second boundary for concurrent requests.
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
    window_start := to_timestamp(
        floor(extract(epoch FROM CURRENT_TIMESTAMP) / window_seconds) * window_seconds
    );
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
