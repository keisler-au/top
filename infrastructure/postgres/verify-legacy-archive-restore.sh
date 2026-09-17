#!/bin/sh
# Verify a complete custom-format PostgreSQL backup in an isolated database.
# The script intentionally checks batch runs and the archive together.
set -eu

archive_file=${1:?usage: verify-legacy-archive-restore.sh BACKUP_FILE SOURCE_DATABASE RESTORE_DATABASE}
source_database=${2:?usage: verify-legacy-archive-restore.sh BACKUP_FILE SOURCE_DATABASE RESTORE_DATABASE}
restore_database=${3:?usage: verify-legacy-archive-restore.sh BACKUP_FILE SOURCE_DATABASE RESTORE_DATABASE}

source_manifest=$(psql -XAt -d "$source_database" -c "SELECT archive_sha256 || ':' || table_hashes::text FROM taxonomy_legacy_archive.exports ORDER BY id DESC LIMIT 1")
source_batch_runs=$(psql -XAt -d "$source_database" -c "SELECT count(*) FROM taxonomy_runs")
source_rollout_reports=$(psql -XAt -d "$source_database" -c "SELECT count(*) FROM taxonomy_legacy_archive.rollout_reports")
dropdb --if-exists "$restore_database"
createdb "$restore_database"
pg_restore --exit-on-error --clean --if-exists -d "$restore_database" "$archive_file"
restored_manifest=$(psql -XAt -d "$restore_database" -c "SELECT archive_sha256 || ':' || table_hashes::text FROM taxonomy_legacy_archive.exports ORDER BY id DESC LIMIT 1")
restored_batch_runs=$(psql -XAt -d "$restore_database" -c "SELECT count(*) FROM taxonomy_runs")
restored_rollout_reports=$(psql -XAt -d "$restore_database" -c "SELECT count(*) FROM taxonomy_legacy_archive.rollout_reports")
[ "$source_manifest" = "$restored_manifest" ]
[ "$source_batch_runs" = "$restored_batch_runs" ]
[ "$source_rollout_reports" = "$restored_rollout_reports" ]
psql -XAt -d "$restore_database" -c "SELECT count(*) FROM taxonomy_legacy_archive.segment_topics st JOIN taxonomy_legacy_archive.input_topics it ON it.original_input_id=st.original_input_id" >/dev/null
