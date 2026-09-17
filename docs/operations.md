# Operations

## Runtime and migrations

The default Compose stack runs PostgreSQL with pgvector, Ollama, a migration job,
the API, eligibility/segmentation and embedding workers, the candidate
taxonomy scheduler, and the article-generation worker.

```bash
docker compose up --build
docker compose down
```

The administrative dashboard is deliberately not part of the default topology.
Use `docker compose --profile admin up --build` to start `admin-web`, bound only
to `127.0.0.1:${ADMIN_PORT:-8081}`. The forthcoming public edge is a separate
service and must not be replaced by the admin dashboard.

The `migrate` service applies numbered SQL files from
`infrastructure/postgres/migrations/` and records them in `schema_migrations`.
It must complete before API or workers start. Use `docker compose ps` and
`docker compose logs <service>` for service state.

Relevant configuration includes `POSTGRES_*`, `LLM_MODEL`,
`OLLAMA_EMBEDDING_MODEL`, `LLM_API_KEY`, and the evidence-queue values:

```text
QUEUE_LEASE_SECONDS=300
QUEUE_MAX_ATTEMPTS=5
QUEUE_RETRY_BASE_SECONDS=5
QUEUE_RETRY_MAX_SECONDS=300
```

The evidence-preparation queue uses PostgreSQL `worker_jobs`, `FOR UPDATE
SKIP LOCKED`, renewable leases, bounded retry, and a terminal `failed` state.
It processes:

```text
new -> eligibility_segmentation -> ready_for_embedding -> embeddings
```

Migration `036_remove_legacy_taxonomy_runtime.sql` deletes retired `topics`
and `themes` jobs and constrains this queue to those two evidence stages.
`ready_for_analysis` is a snapshot-eligible evidence state, not a worker queue
transition. Batch taxonomy work is claimed only from `taxonomy_run_stages` by
`taxonomy-scheduler`; no legacy topic/theme service or runtime setting exists.

`POST /taxonomy-runs` and `python -m triage_processor.taxonomy_snapshots`
create an immutable candidate snapshot. The `taxonomy-scheduler` Compose
service claims the separate `taxonomy_run_jobs` stages using renewable leases;
it can build candidate runs but cannot publish one. Its health check verifies
that the durable stage schema is reachable after migrations complete.

```text
TAXONOMY_POLL_INTERVAL=10
TAXONOMY_LEASE_SECONDS=900
TAXONOMY_MAX_ATTEMPTS=3
TAXONOMY_RETRY_BASE_SECONDS=5
TAXONOMY_RETRY_MAX_SECONDS=300
TAXONOMY_SCHEDULER_CONFIGURATION_VERSION=taxonomy-scheduler-v1
```

`TAXONOMY_POLL_INTERVAL` is the candidate-stage scheduling cadence. Only one
pending or processing `taxonomy_run_jobs` row is permitted by the database;
the scheduler processes that durable candidate and never publishes it. Compose
allows two minutes for an in-flight leased stage to finish and release its
connection on shutdown. The scheduler health probe fails closed when the
durable-stage migration marker is missing, pgvector is unavailable, the
database cannot be reached, or the runtime role lacks the tables needed to
claim scheduled work.

## Taxonomy release gate

The quality stage is the sole writer of a release decision. Its current policy
version is `taxonomy-release-gate-v1`: snapshot completeness must be 1.0,
noise must not exceed 0.40, topic acceptance must be at least 0.80, and
duplicate-topic rate must not exceed 0.10. It records aggregate metrics,
thresholds, failures, and a hash binding those inputs in one immutable
`taxonomy_release_attestations` row per run. It never reads raw evidence into
the attestation and accepts no operator- or API-supplied quality signals.

`TAXONOMY_PUBLICATION_ENABLED` defaults to `false` in Compose. Even when an
operator enables that deployment switch, PostgreSQL rejects publication unless
the candidate has a passing immutable attestation. Authentication and the
protected operations API are configured with the following non-empty secrets:

```text
TAXONOMY_MUTATION_TOKEN=<long-random-secret>
TAXONOMY_REVIEW_TOKEN=<long-random-secret>
OPERATIONS_RATE_LIMIT_REQUESTS=30
OPERATIONS_RATE_LIMIT_WINDOW_SECONDS=60
```

Use a distinct review token whenever read-only operator access is required.
Both `/operations/*` and `/taxonomy-runs/*` fail closed when these credentials
are absent. The mutation token is required for taxonomy writes; the review
token may access aggregate operations telemetry and candidate review only.
Rate-limit counters are stored as credential hashes in PostgreSQL, never as
the secrets themselves. Rotate a token by changing its deployment secret and
restarting the API; no token value is logged or returned by the API.

Retry or cancel a terminal/queued candidate stage explicitly; neither command
can publish a run:

```bash
docker compose exec taxonomy-scheduler \
  python -m triage_processor.taxonomy_scheduler --retry-stage-id 123
docker compose exec taxonomy-scheduler \
  python -m triage_processor.taxonomy_scheduler --cancel-stage-id 123
```

## Google Sheets importer

The optional `google-sheets` Compose profile reads append-only Google Form
response sheets with a read-only service account. Store credentials outside
the repository and share the spreadsheet with the service-account email.

```bash
GOOGLE_SHEETS_CREDENTIALS_FILE=/secure/google-sheets.json \
  docker compose --profile google-sheets up --build
```

Register a form through `/form-sources` with a stable form ID, spreadsheet ID,
sheet name, optional ignored headers, and polling interval. The importer maps
each non-empty cell to one input, derives a stable question key from its
header, and uses row/column source keys for idempotency. Treat response sheets
as append-only: do not reorder, delete unread rows, or expect edits to prior
answers to be re-imported.

## Backup, recovery, and diagnostics

Back up before upgrades:

```bash
docker compose exec -T postgres pg_dump -U postgres -d triage -Fc > triage.backup
```

Restore only after confirming the exact target database and stopping the
application services. See the root README for the restore command sequence.

### Legacy taxonomy archive

Migration `034_add_taxonomy_legacy_archive.sql` freezes legacy topic strings,
themes and links, suggestions/materialization, and assignment-attempt metadata
in the append-only `taxonomy_legacy_archive` schema. Migration
`037_drop_legacy_taxonomy_schema.sql` also preserves the retired rollout
reports there before dropping their mutable source table. Its `exports` row records
versioned per-relation counts, SHA-256 checksums, and an aggregate checksum.
The application has no write path to this schema; mutation attempts fail in
PostgreSQL. The protected audit routes are bounded and intentionally omit raw
evidence, prompts, and model responses.

Retain database backups containing this schema for the same period as article
and citation provenance. To validate a restore, restore a
custom-format backup into an isolated database and compare the manifest's
`archive_sha256` and `table_hashes` with the source manifest; then query a
sample of `segment_topics`, `theme_topics`, and `suggestion_evidence` links by
their original IDs and compare the archived `rollout_reports` count. Do not restore the archive alone into a production
database: restore the complete PostgreSQL backup so batch taxonomy and article
provenance remain transactionally consistent.

Useful bounded diagnostics:

```sql
SELECT job_type, status, count(*)
FROM worker_jobs
GROUP BY job_type, status
ORDER BY job_type, status;

SELECT id, job_type, original_input_id, attempts, last_error
FROM worker_jobs
WHERE status = 'failed'
ORDER BY id;

SELECT source, form_key, question_key, question_version, count(*)
FROM questions JOIN original_inputs ON original_inputs.question_id = questions.id
GROUP BY source, form_key, question_key, question_version
ORDER BY source, form_key, question_key, question_version;
```

Use `/operations/summary` for application-facing metrics. Do not expose or log
raw evidence, LLM prompts, responses, credentials, or unrestricted database
error payloads.
