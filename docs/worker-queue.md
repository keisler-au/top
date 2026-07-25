# Worker queue

The pipeline uses PostgreSQL as a durable queue. This keeps job state and
pipeline state in the same transactional system and avoids adding a separate
broker for the current workload.

## Stage mapping

An `original_inputs` trigger enqueues work whenever an input enters a pipeline
status:

```text
new → eligibility_segmentation
ready_for_embedding → embeddings
ready_for_analysis → topics
completed → themes
```

Workers claim available jobs with `FOR UPDATE SKIP LOCKED`. Claims have
renewable leases, so interrupted jobs become available again. Processing
failures use exponential backoff and enter the `failed` dead-letter state after
the configured attempt limit.

The one-shot Compose `migrate` service applies all pending numbered files from
`infrastructure/postgres/migrations/` before workers start. It records each
success in `schema_migrations`, so restarting Compose is idempotent and a
database that is several versions behind is upgraded in filename order. Each
migration and its tracking row are committed atomically. Migration
`008_add_worker_jobs.sql` creates and backfills the queue.

## Configuration

```text
QUEUE_LEASE_SECONDS=300
QUEUE_MAX_ATTEMPTS=5
QUEUE_RETRY_BASE_SECONDS=5
QUEUE_RETRY_MAX_SECONDS=300
```

## Operations

Summarize queue state:

```bash
docker compose exec postgres psql -U postgres -d triage -c \
  "SELECT job_type, status, count(*) FROM worker_jobs GROUP BY job_type, status ORDER BY job_type, status;"
```

Inspect failed jobs:

```bash
docker compose exec postgres psql -U postgres -d triage -c \
  "SELECT id, job_type, original_input_id, attempts, last_error FROM worker_jobs WHERE status = 'failed' ORDER BY id;"
```

After correcting a failure, requeue its job:

```sql
UPDATE worker_jobs
SET status = 'pending',
    attempts = 0,
    available_at = CURRENT_TIMESTAMP,
    last_error = NULL,
    completed_at = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE id = 123 AND status = 'failed';
```

Scale a worker independently:

```bash
docker compose up --build --scale embeddings=2
```
