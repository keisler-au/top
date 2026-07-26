This system stores original comments, embeds them for similarity search, and
asks a local LLM to suggest topics and themes.

# Project Context

## Objective

Build a local system that captures user inputs, identifies distinct points within them, creates semantic embeddings, assigns topics, and identifies recurring themes across multiple inputs.

The original input remains the source of truth. LLM outputs are stored as system-generated classifications and suggestions.

## Core stack

* FastAPI for the application API
* PostgreSQL with pgvector for relational data and vector search
* Ollama for local LLM and embedding models
* Python workers for background processing

## Processing workflow

```text
Input received
→ saved unchanged in PostgreSQL
→ eligibility and segmentation
→ full-input and segment embeddings
→ similarity search
→ topic assignment
→ theme identification
```

## Worker responsibilities

### Worker 1: eligibility and segmentation

Processes new inputs.

* Determine whether the input is eligible.
* If eligible, split multi-topic inputs into meaningful segments.
* Preserve the original wording where possible.
* Save segments and mark the input ready for embedding.

### Worker 2: embeddings

Processes eligible inputs.

* Send the full input and its segments to the embedding model.
* Receive vectors from Ollama.
* Save vectors in PostgreSQL using pgvector.
* Mark the input ready for analysis.

The embedding model does not access the database directly.

### Worker 3: topic assignment

Processes embedded inputs.

* Find similar existing segments using pgvector.
* Retrieve relevant existing topics.
* Ask the LLM to reuse an existing topic or suggest a new one.
* Save topic assignments and mark the input complete.

### Worker 4: theme management

Runs from queued completion events across completed inputs.

* Group related segments using embeddings and topics.
* Retrieve relevant existing themes.
* Ask the LLM to reuse, update, merge or create themes.
* Link themes to relevant topics and supporting inputs.
* Save final suggestion records with their topics and supporting inputs.

## Key distinction

```text
Topic = what an input or segment is about
Theme = what multiple related inputs are collectively saying
```

Topics and themes are stored separately but linked because their relationship may be many-to-many.

## Design principles

* Keep the database minimal.
* Preserve original text.
* Store segments separately from inputs.
* Store full-input and segment embeddings in PostgreSQL.
* Use statuses to control processing stages.
* Avoid tightly coupling workers.
* Start with sequential or scheduled workers.
* Use the PostgreSQL-backed queue for durable retries and worker scaling.
* Prefer existing topics and themes before creating new ones.

## Repository layout

```text
.
├── backend/
│   ├── src/triage_processor/
│   │   ├── api/
│   │   ├── clients/
│   │   └── workers/
│   ├── tests/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── uv.lock
├── frontend/
├── infrastructure/postgres/
├── docs/
└── compose.yaml
```

The `frontend` directory is intentionally empty. See
[Architecture](docs/architecture.md) for the backend responsibility boundaries
and [Worker queue](docs/worker-queue.md) for queue operations.

## Backend development

Install the locked dependencies and run the tests from the backend project:

```bash
cd backend
uv sync --frozen
uv run python -m unittest discover -s tests -v
```

Run the API locally with:

```bash
cd backend
uv run uvicorn triage_processor.api.main:app --reload
```

## Run the full stack with Docker Compose

The Compose stack includes PostgreSQL, Ollama, the FastAPI API, and all four
workers. Start the full stack with:

```bash
docker compose up --build
```

On first startup, the `ollama-init` service downloads the default
`qwen3:4b` chat model and `nomic-embed-text` embedding model before the workers
start. Model downloads are stored in the persistent `ollama_models` volume, so
subsequent startups reuse them. The workers communicate with the Ollama
container directly; no host Ollama process is required.

Before the API and workers start, the one-shot `migrate` service applies every
pending SQL file in `infrastructure/postgres/migrations/` in filename order.
Applied filenames are tracked in `schema_migrations`, so the service is safe to
run repeatedly and can bring an older persistent database through multiple
migrations in one startup. Each migration and its tracking row commit in the
same transaction. Add new migrations as numbered `.sql` files; no Compose
change is needed.

The API is available at `http://localhost:8000`, PostgreSQL at
`localhost:5432`, and Ollama at `http://localhost:11434`. Stop the stack with
`docker compose down`; the PostgreSQL data and downloaded Ollama models remain
in their named volumes.

Compose environment variables can override the defaults, for example:

```bash
API_PORT=8080 LLM_MODEL=qwen3:4b docker compose up --build
```

## Worker queue

The workers use PostgreSQL as a durable queue. This fits the current workload
better than adding a separate broker: PostgreSQL is already required, the
pipeline is low-throughput and database-backed, and each stage must commit its
output before the next stage can begin.

An `original_inputs` trigger enqueues work whenever an input enters a pipeline
status:

```text
new → eligibility_segmentation
ready_for_embedding → embeddings
ready_for_analysis → topics
completed → themes
```

Workers claim jobs with `FOR UPDATE SKIP LOCKED`, so a service can be scaled
without two instances claiming the same available job. Claims have renewable
leases; an interrupted worker's job becomes claimable again after
`QUEUE_LEASE_SECONDS`. Failures are retried with exponential backoff and move
to the `failed` dead-letter state after `QUEUE_MAX_ATTEMPTS`.

Migration `008_add_worker_jobs.sql`, applied by the Compose `migrate` service,
installs the queue schema and backfills jobs for inputs that were already in
progress. Useful queue settings and their defaults are:

```text
QUEUE_LEASE_SECONDS=300
QUEUE_MAX_ATTEMPTS=5
QUEUE_RETRY_BASE_SECONDS=5
QUEUE_RETRY_MAX_SECONDS=300
```

Inspect queue state with:

```bash
docker compose exec postgres psql -U postgres -d triage -c \
  "SELECT job_type, status, count(*) FROM worker_jobs GROUP BY job_type, status ORDER BY job_type, status;"
```

Inspect failed jobs with:

```bash
docker compose exec postgres psql -U postgres -d triage -c \
  "SELECT id, job_type, original_input_id, attempts, last_error FROM worker_jobs WHERE status = 'failed' ORDER BY id;"
```

After correcting the underlying issue, requeue a failed job by ID:

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

Individual worker services can be scaled independently, for example:

```bash
docker compose up --build --scale embeddings=2
```

## Interactive manual testing

With the Compose stack running, use the interactive runner to submit sample
inputs and inspect their stored pipeline results:

```bash
python3 scripts/manual_test.py
```

Each invocation creates a unique source tag. To inspect a previous run, copy
the source shown in its menu and pass it explicitly:

```bash
python3 scripts/manual_test.py --source manual-20260726-143000
```
