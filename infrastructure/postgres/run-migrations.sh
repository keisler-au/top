#!/bin/sh

set -eu

MIGRATIONS_DIR=${MIGRATIONS_DIR:-/postgres/migrations}
export LC_ALL=C

psql --set ON_ERROR_STOP=1 <<'SQL'
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Bootstrap databases that predate schema_migrations. Each marker is an
-- artifact introduced by that migration (and retained by the current schema).
INSERT INTO schema_migrations (filename)
SELECT '002_add_segment_inputs.sql'
WHERE to_regclass('public.segment_inputs') IS NOT NULL
ON CONFLICT DO NOTHING;

INSERT INTO schema_migrations (filename)
SELECT '003_add_input_status.sql'
WHERE EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE
        table_schema = 'public'
        AND table_name = 'original_inputs'
        AND column_name = 'status'
)
ON CONFLICT DO NOTHING;

INSERT INTO schema_migrations (filename)
SELECT '004_add_ready_for_analysis_status.sql'
WHERE to_regclass('public.idx_original_inputs_ready_for_embedding') IS NOT NULL
ON CONFLICT DO NOTHING;

INSERT INTO schema_migrations (filename)
SELECT '005_add_completed_status.sql'
WHERE to_regclass('public.idx_original_inputs_ready_for_analysis') IS NOT NULL
ON CONFLICT DO NOTHING;

INSERT INTO schema_migrations (filename)
SELECT '006_add_theme_management.sql'
WHERE to_regclass('public.theme_suggestions') IS NOT NULL
ON CONFLICT DO NOTHING;

INSERT INTO schema_migrations (filename)
SELECT '007_align_worker_contracts.sql'
WHERE EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE
        table_schema = 'public'
        AND table_name = 'input_embeddings'
        AND column_name = 'embedding_model'
)
ON CONFLICT DO NOTHING;

INSERT INTO schema_migrations (filename)
SELECT '008_add_worker_jobs.sql'
WHERE
    to_regclass('public.worker_jobs') IS NOT NULL
    AND EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE
            tgname = 'original_inputs_enqueue_job'
            AND NOT tgisinternal
    )
ON CONFLICT DO NOTHING;
SQL

found_migration=false
for migration_path in "$MIGRATIONS_DIR"/*.sql; do
    if [ ! -f "$migration_path" ]; then
        continue
    fi
    found_migration=true
    filename=${migration_path##*/}

    {
        printf '%s\n' \
            'BEGIN;' \
            'SELECT pg_advisory_xact_lock(847319205);' \
            "SELECT NOT EXISTS (" \
            "    SELECT 1 FROM schema_migrations" \
            "    WHERE filename = :'migration_filename'" \
            ') AS migration_pending' \
            '\gset' \
            '\if :migration_pending'
        printf '\\echo Applying %s\n' "$filename"
        # The files remain independently runnable with BEGIN/COMMIT. Strip
        # only those boundary lines because this transaction also records the
        # migration atomically.
        sed \
            -e '1{/^BEGIN;$/d;}' \
            -e '${/^COMMIT;$/d;}' \
            "$migration_path"
        printf '%s\n' \
            "INSERT INTO schema_migrations (filename)" \
            "VALUES (:'migration_filename');" \
            '\else'
        printf '\\echo Skipping already-applied migration %s\n' "$filename"
        printf '%s\n' \
            '\endif' \
            'COMMIT;'
    } | psql \
        --set ON_ERROR_STOP=1 \
        --set "migration_filename=$filename"
done

if [ "$found_migration" = false ]; then
    echo "No SQL migrations found in $MIGRATIONS_DIR" >&2
    exit 1
fi
