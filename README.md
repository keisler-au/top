This system stores original comments, prepares embeddings, and builds an
immutable, run-scoped taxonomy with a local LLM.

# Project Context

## Objective

Build a local system that captures user inputs, identifies distinct points
within them, creates semantic embeddings, and publishes one reviewed batch
taxonomy across multiple inputs.

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
→ immutable batch snapshot
→ automatic snapshot, leased taxonomy stages, and quality-gated publication
→ evidence-grounded article generation
→ explicit editorial approval
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

### Taxonomy scheduler and article generation

The taxonomy scheduler automatically snapshots eligible evidence, processes
frozen run stages (clustering, topic naming, theme inference, reconciliation,
and quality) under durable leases, and publishes only a gate-qualified run. It
never uses per-input topic/theme jobs. The article-generation worker:

Processes durable generation jobs independently of the evidence pipeline.

* Freeze canonical evidence and a versioned, validated HTML template when a
  job is created.
* Ask the LLM for strictly validated structured JSON rather than HTML.
* Reject citations and taxonomy tags outside the frozen job scope.
* Escape and sanitize rendered output, then create a `ready_for_review`
  article with immutable revision provenance.
* Lease, retry, and dead-letter jobs so work survives worker restarts.

## Key distinction

```text
Topic = what an input or segment is about
Theme = what multiple related inputs are collectively saying
```

Question context is normalized in the immutable `questions` table. The
identity `(source, form_key, question_key, question_version)` preserves the
exact question wording used to interpret an answer. Contextual answers embed
the question and answer together; generic inputs retain answer-only behavior.

Topics and themes are run-scoped revisions with durable stable identities.
The sole published run is the source for all taxonomy readers and generation.
Before first publication, the dashboard reports the newest candidate's
processing, terminal failure, or failed quality gate with bounded status codes.
Automatic replacement candidates in current source recluster all eligible
canonical evidence, including generic and contextual answers embedded by one
model and dimension. The current source and migrations 041–043 have fresh,
populated-upgrade, and production-shaped Compose acceptance evidence. The
affected local installation was recovered with the documented backup-first
procedure on 2026-09-24; its failed first candidate remains quality-blocked and
nonpublishable.

## Design principles

* Keep the database minimal.
* Preserve original text.
* Store segments separately from inputs.
* Store full-input and segment embeddings in PostgreSQL.
* Use statuses only to control evidence preparation; taxonomy work is run-scoped.
* Avoid tightly coupling workers.
* Start with sequential or scheduled workers.
* Use the PostgreSQL-backed queue for durable retries and worker scaling.
* Preserve batch taxonomy identity and lineage across published runs.

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
│   ├── admin/                # opt-in, loopback-only administrative dashboard
│   └── public/               # dependency-free internet-facing nginx edge
├── infrastructure/postgres/
├── docs/
└── compose.yaml
```

See the [documentation guide](docs/README.md) for architecture, API,
operations, and the active batch-taxonomy production plan.

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

### Input retrieval

`GET /inputs` supports form, question, and submission retrieval. Question and
submission filters are scoped by both `source` and `form_key`; omitting
`question_version` returns every version of the selected question. Results
include resolved question context and a taxonomy projection from exactly one
published run. `topics` and `themes` contain stable IDs plus display snapshots;
the retired string `topic` field is never returned. `taxonomy_state` is
`classified`, `pending_classification` for evidence after the published cutoff,
or `taxonomy_unavailable` before the first publication.

The endpoint uses deterministic `id` ordering with `offset`/`limit`
pagination. The default limit is 50, the maximum limit is 100, and offset is
bounded at 100,000. This deliberately simple pagination model matches the
system's low-throughput workload.

See [Operations](docs/operations.md) for bounded diagnostic queries and queue
recovery guidance.

The disposable automatic-taxonomy journey includes both evidence workers, a
real Ollama embedding service, and the scheduler:

```bash
docker compose -f compose.taxonomy-journey.yaml up -d --build --wait
docker compose -f compose.taxonomy-journey.yaml --profile acceptance run --rm journey
docker compose -f compose.taxonomy-journey.yaml --profile acceptance down -v
```

## Run the production stack with Docker Compose

The Compose stack includes PostgreSQL, Ollama, the FastAPI API, two
evidence-preparation workers, the taxonomy scheduler, and article generation.
Start the full stack with:

```bash
docker compose up --build
```

The default external service is `public-web`, bound to
`http://localhost:${PUBLIC_PORT:-8080}`. It exposes only the public editorial
routes, health, and self-hosted assets; it never exposes the internal `/_site`
renderer or administrative APIs. Set `PUBLIC_SITE_ORIGIN` to the public
absolute `http(s)` origin (no path, query, fragment, or credentials),
`PUBLIC_SITE_NAME`, and optional `PUBLIC_SITE_DESCRIPTION` for canonical,
Open Graph, JSON-LD, sitemap, and robots output. Those values are deployment
configuration, never inferred from a request Host header.

The administrative dashboard is an opt-in local-only profile. Start it with
`docker compose --profile admin up --build`; it is available at
`http://127.0.0.1:8081` by default and proxies its internal `/api/*` requests
to FastAPI. PostgreSQL, Ollama, and the API remain on the internal Compose
network. Set `ADMIN_PORT` to choose a different loopback port.

If the public edge is unhealthy, inspect it with
`docker compose logs public-web`, then recreate only that stateless service
with `docker compose up --build --force-recreate public-web`. Do not expose
`admin-web` as a recovery substitute: it intentionally proxies internal API
routes and remains loopback-only.

On first startup, the `ollama-init` service downloads the default
`qwen3:4b-instruct` chat model and `nomic-embed-text` embedding model before the workers
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

Stop the stack with `docker compose down`; the PostgreSQL data and downloaded
Ollama models remain in their named volumes. Add `-v` only when intentionally
discarding all local database data and downloaded models.

Compose environment variables can override the defaults, for example:

```bash
PUBLIC_PORT=8082 LLM_MODEL=qwen3:4b-instruct docker compose up --build
```

The main runtime settings are `POSTGRES_DB`, `POSTGRES_USER`,
`POSTGRES_PASSWORD`, `LLM_MODEL`, `OLLAMA_EMBEDDING_MODEL`, `LLM_API_KEY`, and
the public-site settings and worker queue settings documented below. Keep secrets in `.env` (which is
ignored by Git) or your deployment secret store; never put credentials in the
Compose file. `LLM_API_KEY` is only needed for a compatible external model
endpoint.

Legacy taxonomy history is retained in the immutable
`taxonomy_legacy_archive` schema from migration `034`. It is included in the
normal PostgreSQL backup/restore procedure; use the protected archive audit
API and its checksum manifest for inspection rather than querying it from
taxonomy readers.

For local dashboard development, run `npm ci && npm run dev` in `frontend/admin/` and
run the API separately on port 8000. The development server proxies `/api` to
that local API; Compose dashboard traffic goes through the `admin-web` service.
The public edge has no browser API client or admin API access.

### Backup and restore

Back up the PostgreSQL database before upgrading images or applying operational
changes:

```bash
docker compose exec -T postgres pg_dump -U postgres -d triage -Fc > triage.backup
```

Restore into a stopped application stack after confirming the target database:

```bash
docker compose up -d postgres
docker compose exec -T postgres dropdb -U postgres --if-exists triage
docker compose exec -T postgres createdb -U postgres triage
docker compose exec -T postgres pg_restore -U postgres -d triage --clean --if-exists < triage.backup
docker compose up -d
```

Restore the complete database only: `article_publications` and their
revision-scoped `article_publication_themes` snapshots are restored alongside
the batch taxonomy and legacy archive. Returning an approved article to draft
or archiving it withdraws it; reapproval restores its permanent URL with a new
immutable snapshot. Taxonomy changes never rewrite published article snapshots.

The Google Sheets importer is optional and starts only with the
`google-sheets` profile. Mount a service-account JSON file through
`GOOGLE_SHEETS_CREDENTIALS_FILE`, then run:

```bash
docker compose --profile google-sheets up --build
```

### Operations summary and logs

`GET /api/operations/summary` reports bounded counters and ages for the
evidence queue, batch taxonomy runs, article generation, form polling, and
recent approvals. It deliberately returns no source responses, generated
articles, errors, prompts, credentials, or model headers. API, worker, and
importer logs are JSON records containing event metadata, request path, status,
duration, and safe exception type only.

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
```

`ready_for_analysis` means that evidence is available for a future immutable
batch snapshot; it does not enqueue a retired incremental taxonomy worker.

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
