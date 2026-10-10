# Operations

## Runtime and migrations

The default Compose stack runs PostgreSQL with pgvector, Ollama, a migration job,
the API, eligibility/segmentation and embedding workers, the candidate
taxonomy scheduler, article generation, admin dashboard and Google Sheets poller.
`compose.override.yaml` is automatically merged for local development.

```bash
docker compose up
docker compose down
```

`public-web` is the public host-published web service, bound to
`${PUBLIC_PORT:-8080}`. It serves only the allowlisted public editorial routes,
discovery documents, self-hosted assets, and `/healthz`; `/_site` and all
administrative/API paths remain unavailable. `admin-web` starts locally by
default, bound only to `127.0.0.1:${ADMIN_PORT:-8081}`. Internal API, database
and model ports remain unpublished. The public edge remains separate.

### Local updates and production mode

Compose 2.24.4 or newer is required for the override profile resets. On the
initial switch from existing images, use `docker compose up --build` once.
Subsequent `docker compose up` (or `up -d`) reuses images. Python source is
mounted read-only: Uvicorn reloads the API, and watchfiles restarts each worker
after edits. An interrupted claim may wait until its existing lease expires
before retry; ownership guards still prevent stale writes. The admin watcher
recompiles TS/CSS/HTML into staging and publishes only successful builds.
Refresh the browser; compilation failures retain the last valid page. Polling
handles bind-mounted changes on Linux and Docker Desktop.

Dependencies/Dockerfile changes require `docker compose build api admin-web`
then `docker compose up`; all six backend services share the API development
image. Changes to environment settings require `docker compose up` to recreate
affected services. Development watcher/server tooling may require a restart.
Public static assets are mounted too; browser/shared caching still applies.
Changes to nginx configuration require `docker compose restart public-web`.
SQL changes require the existing migration/backup workflow and do not hot reload.

Production mode explicitly bypasses the local override: `docker compose -f
compose.yaml up -d --build`. Add `--profile admin` and/or `--profile google-sheets`
before `up` when those services are wanted in production. It retains immutable
image sources and optional profiles. Named database/model volumes are unchanged.
[ADR-0005](decisions/0005-default-local-development.md) records this default.
Verify backend reloads without application data using
`python3 scripts/verify-development.py` after building the development image.

### Public-edge recovery

The public edge is stateless. Check its health and nginx startup output with
`docker compose ps public-web` and `docker compose logs public-web`. Rebuild
only that service with `docker compose up --build --force-recreate public-web`
when its image or static assets need recovery. Do not add broad proxying or
publish `admin-web` as a substitute. Set `PUBLIC_SITE_ORIGIN` to the deployed
absolute HTTP(S) origin (without path/query/fragment/credentials), plus
`PUBLIC_SITE_NAME` and optional `PUBLIC_SITE_DESCRIPTION`; invalid settings
prevent API startup. These values control canonical/sitemap/Open Graph/JSON-LD
URLs. HTML and discovery responses have a five-minute shared cache; only
content-hashed assets are immutable. Public errors are generic and the edge
enforces its self-host-only, scriptless CSP and restrictive browser policies.

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
remain protected recovery tools. Normal Compose operation automatically creates
an immutable candidate when eligible embeddings meet the versioned policy. The
`taxonomy-scheduler` claims the separate `taxonomy_run_jobs` stages using
renewable leases and publishes only a passing automatic candidate. Its health check verifies
that the durable stage schema is reachable after migrations complete.

```text
TAXONOMY_POLL_INTERVAL=10
TAXONOMY_LEASE_SECONDS=900
TAXONOMY_MAX_ATTEMPTS=3
TAXONOMY_RETRY_BASE_SECONDS=5
TAXONOMY_RETRY_MAX_SECONDS=300
TAXONOMY_SCHEDULER_CONFIGURATION_VERSION=taxonomy-scheduler-v1
TAXONOMY_AUTOMATION_ENABLED=true
TAXONOMY_AUTOMATION_POLICY_VERSION=taxonomy-automation-v3
TAXONOMY_AUTOMATION_MINIMUM_EVIDENCE=2
TAXONOMY_AUTOMATION_QUIET_SECONDS=30
TAXONOMY_EMBEDDING_REPRESENTATION=question-answer
```

Set `TAXONOMY_AUTOMATION_ENABLED=false` to pause new automatic snapshots and
promotion without withdrawing an existing publication. `GET /operations/summary`
reports only bounded automation state, policy version, and failure code.
The automatic policy uses `partial-topic-policy/v1`: question-answer vectors,
immutable question scopes, `min_cluster_size=2`, and `min_samples=1`; minimum
evidence must be at least two. Each cluster records calibrated cohesion,
separation, membership and density-persistence diagnostics. Only passing
clusters can reach topic naming. Their evidence packet contains every distinct
original up to 40, or 30 central plus up to 10 farthest-first diverse examples,
within 32,768 serialized bytes. Replacements snapshot all eligible canonical
evidence through the new cutoff and recluster it. The prior publication stays
served until a passing replacement completes the database gate.

Topic naming uses prompt version `partial-topic-naming/v1`. The model returns
a bounded name and description plus the packet's exact ordered evidence IDs.
Deterministic validation checks only structure, identifier match, bounds, and
normalized-name uniqueness; it does not compare words to decide meaning. A
structurally invalid response is retained and retried once, for at most two
immutable attempts per cluster. Transport failures continue through the
scheduler's bounded stage retry. Model calls occur without a database
transaction; the current stage lease is checked before the response, attempt,
and provisional-topic rows are saved atomically. Oversized audit JSON becomes
bounded metadata with the original byte count and SHA-256 rather than entering
logs.

Migration 044 makes `original_inputs.question_id` non-null. It deliberately
fails before changing the schema when any historical input lacks question
context. Audit and resolve those rows from authoritative source records; never
invent wording. The migration also backfills explicit `legacy-unrecorded`
preparation provenance for already processed, question-linked inputs and
segments, preserves older frozen cluster plans, and adds the versioned PTR-1
cluster diagnostics. Deploy migration 044 with matching API, evidence-worker,
and scheduler images. Stop if the audit fails; no partial migration commits.

Migration 045 adds immutable `taxonomy_provisional_topics`, each linked to an
accepted naming attempt and its source cluster. Apply it with the matching
scheduler and set
`TAXONOMY_TOPIC_PROMPT_VERSION=partial-topic-naming/v1`; scheduler health fails
closed without its migration marker. It does not rewrite published topics or
historical naming attempts. On a failed deployment, stop the new scheduler and
keep serving the prior publication; restore the pre-migration backup if schema
rollback is required.

Migration 046 inserts `topic_reconciliation` after provisional naming and
before theme inference, and adds `taxonomy_topic_reconciliation_decisions`
and `taxonomy_canonical_topic_antecedents`. Canonical memberships must derive
from their antecedent cluster memberships. Existing terminal runs retain their
historical topics and receive a matching terminal stage record; active runs
receive a pending stage. No historical topics are rewritten or backfilled with
invented antecedents. The migration takes table locks to replace stage checks;
stop the scheduler before applying it and start matching images afterward.
`init.sql` and scheduler health both include its marker. This checkout also
includes migrations 047/048 with PTR-4/PTR-5 disposable verification; live
deployment still requires its own backup and migration evidence.

The versioned reconciliation policy and prompt are
`cross-question-topic-reconciliation/v1`. Centroid cosine >=0.82 or name-term
similarity >=0.50 shortlists cross-question neighbors. Each packet has at most
12 topics, one per question, with at most two whole representative answers
per topic and a 32,768-byte compact UTF-8 JSON bound. Oversized metadata fails
closed; answers that do not fit are omitted whole. These are comparison bounds,
not semantic merge rules. Isolated topics get durable no-merge decisions without
model calls. Transport failures have at most three immutable request attempts;
invalid structural or contradictory decisions require diagnosis and a new
candidate, rather than replacing the stored decision on retry.

Model requests occur outside transactions. Response/decision persistence
checks the stage lease, and canonical identity, antecedents, evidence union,
representatives and lineage commit in one short transaction. Crash replay uses
stored decisions; competing responses use only the first committed winner.
On failure, retain the prior publication, stop the new scheduler, and inspect
protected audit records. Schema rollback requires a pre-migration backup;
publication rollback uses the existing explicit run transition. Migration 046
has disposable fresh/populated verification, not live deployment evidence.

Migration 042 records decision membership mode, bounded snapshot retries,
and scheduler heartbeat/evaluation-failure state. Existing reserved
post-cutoff decisions replay with their historical selector; new decisions
use cumulative membership. Snapshot creation or decision-link errors retry
at most three times with backoff, then report `snapshot_error` until evidence
or policy changes. Other automation evaluation errors stop after three
attempts for one policy version and report `automation_error`. Correct the
cause and advance `TAXONOMY_AUTOMATION_POLICY_VERSION` to reset that terminal
counter. An expired scheduler heartbeat reports unavailable status to
first-run readers. None of these transitions changes frozen runs or failed
attestations.

Migration 043 corrects the operations API's fixed rate-limit window key: it
uses the same whole-window floor for every concurrent request. It preserves
existing counters and operator authentication. Apply 042 and 043 with the
matching application image before relying on the new TR-2 diagnostics.

### Automatic-taxonomy acceptance

The disposable full-journey stack exercises the production Google Sheets
reader/import processor and HTTP input sink, direct API input, both evidence
workers, real Ollama embeddings, all eight durable taxonomy stages, automatic
publication, topic-targeted generation, editorial approval and the public edge.
Only the external Sheets values/auth transport and structured chat outputs are
fixtures; live Google credentials are not used. The lifecycle check measures
service wiring and durable behaviour, rather than chat-model sampling.
The durable stage sequence is `snapshot → clustering → topic_naming →
topic_reconciliation → theme_inference → theme_reconciliation → quality →
ready_for_publication`:

- Partial publication merges equivalent cross-question provisional topics,
  retains uncovered evidence and publishes with zero themes.
- A full-coverage successor retains distinct related concepts and infers a theme.
- Ineligible input remains stored without a vector; eligible Sheets/API answers
  receive published-run arrays. A zero-theme topic generates a reviewable article.
- A rejected-label successor keeps the prior publication served and does not
  loop on unchanged evidence. Generated article evidence and topic tags retain
  the job's frozen run. Replayed automatic publication and explicit
  rollback preserve approved public content; private routes remain denied.

Start with a fresh journey database:

```bash
docker compose -f compose.taxonomy-journey.yaml up -d --build --wait
docker compose -f compose.taxonomy-journey.yaml --profile acceptance run --rm journey
docker compose -f compose.taxonomy-journey.yaml --profile acceptance down
```

The stack uses a tmpfs database and its own Ollama model-cache volume. The final
command discards only the disposable database and containers and retains the
model cache. It never mounts the application PostgreSQL volume. PostgreSQL test
health checks use TCP so the initialization-only local socket cannot release
migration/API consumers early. The structured-chat mode control is test-only,
internal to this isolated stack and absent from production images/routes.

`TAXONOMY_POLL_INTERVAL` is the candidate-stage scheduling cadence. Only one
pending or processing `taxonomy_run_jobs` row is permitted by the database;
the scheduler processes that durable candidate and automatically publishes it
only after a passing release attestation. Compose
allows two minutes for an in-flight leased stage to finish and release its
connection on shutdown. The scheduler health probe fails closed when the
durable-stage migration marker is missing, pgvector is unavailable, the
database cannot be reached, or the runtime role lacks the tables needed to
claim scheduled work.

## Taxonomy release gate

The quality stage is the sole writer of a release decision. Current source
uses `taxonomy-release-gate-v3`: at least one canonical topic with evidence and
internally consistent, completed processing is required. Coverage percentage,
noise rate, rejected naming attempts and zero themes do not block a useful
candidate. The existing local deployment still uses gate v2 until the new
migration and matching runtime are deployed.

Migration 047 adds the shared computed owner
`taxonomy_publication_facts(run_id)`. It reports total frozen evidence,
`evidence_with_topic_count` (any canonical membership) and
`evidence_without_topic_count` (no canonical membership); each frozen item
counts once. `question_count` counts immutable question IDs and
`submission_count` counts known `(source, form_key, submission_key)` identities.
Inputs without a submission key do not invent a submission. Canonical topic
count is distinct from accepted/rejected naming-attempt counts; retries remain
separate audit attempts. The attestation also retains cluster, noise, candidate
and reconciled theme counts and diagnostic rates.

The facts function checks completed predecessor stages, complete cluster
membership, nonempty topic support, exact antecedent evidence unions, accepted
naming/provisional provenance, complete model request/response traces, theme
provenance and exact canonical topic links. Its bounded failures include
`processing_unfinished`, `snapshot_incomplete`, `canonical_topics_missing`,
`topic_membership_inconsistent`, `antecedent_membership_inconsistent`,
`topic_trace_missing`, `model_trace_missing`, `theme_trace_missing` and
`theme_membership_inconsistent`. The Python gate additionally checks coverage
arithmetic/nonnegative counts and empty snapshots with `coverage_inconsistent`
and `snapshot_empty`. The hash binds every aggregate fact, thresholds and gate
version. Raw answers and model text never enter this aggregate record.

One immutable `taxonomy_release_attestations` row per run retains metrics,
thresholds, failures and input hash. Repeated quality work returns the stored
facts, including older gate-v2 records; it never upgrades their version or
replaces a prior failure. A stale/wrong quality claim writes nothing. The
internal review API returns aggregate coverage, gate version and bounded
failures; no endpoint accepts caller-supplied release signals.

Themes use `partial-theme-inference/v1` over canonical topic revisions.
Deterministic cosine >=0.82 neighborhoods contain two to five distinct topics,
including their anchor, and at most two whole canonical representative answers
per topic within 32,768 compact UTF-8 JSON bytes. Oversized metadata fails
closed; oversized answers are omitted whole. Equivalent provisional antecedents
appear as one canonical topic. A theme must choose at least two distinct
supplied canonical IDs. One topic, isolated topics, or an explicit model
no-theme decision normally yields zero themes. Completed attempts and theme
reconciliation replay without new model calls or replacement writes.
`TAXONOMY_THEME_PROMPT_VERSION=partial-theme-inference/v1` matches source,
Compose and `.env.example`; use it for new snapshots only.

Migration 047 also aligns provisional label uniqueness with its immutable
question scope and makes `materialize_taxonomy_theme_revisions` accept zero
reconciled themes while retaining its ready-run guard and retirement lineage.
It adds no publication transition. Apply migrations after a backup with the
scheduler stopped; the uniqueness/stage tables require brief locks. Existing
runs, attestations and publication records remain unchanged. Migration 047 is
included in `init.sql` and scheduler readiness markers. Migration 048 replaces
manual and automatic publication with current-version attestation checks and
one transaction for materialization, aliases, prior-run retirement, publication
and audit. It rejects failed/old/incompatible gates and changed facts. A waiting
different-candidate swap is rejected if another swap changed publication; retry
after reviewing the new current run. Same-candidate delivery remains idempotent. A valid
zero-theme run can publish. Replays keep the original publication decision;
explicit rollback restores a superseded run, including a historical publication,
and records its own immutable decision. Apply 048 with matching API/scheduler
images after a backup and with the scheduler stopped. Existing publications and
attestations are retained; failed replacement continues serving the prior run.
On migration failure, stop the new scheduler; schema recovery requires the
pre-upgrade backup. `init.sql` and scheduler readiness include marker 048.

Replacement and rollback select one complete run for both input topic and theme
arrays. Empty associations, including a zero-theme successor, are normal; do
not repair them by writing classifications onto source input rows. Frozen run
evidence, attestations and approved article displays remain unchanged. The
existing explicit rollback owner is PostgreSQL's
`rollback_taxonomy_run(run_id, operator, note)`; there is no HTTP rollback route.
After selecting and reviewing the earlier publication, invoke that function
through the existing administrative database connection and check `/inputs`
run provenance and both arrays. Repeating the same rollback retains one audit
decision. A competing candidate rejected after another switch requires review
of the new publication before an explicit retry.

Human publication defaults to `false` in Compose and remains token-protected.
Automatic promotion needs neither token nor switch, but PostgreSQL accepts it
only for a matching durable automation policy and passing immutable attestation. Authentication and the
protected operations API are configured with the following non-empty secrets:

```text
TAXONOMY_MUTATION_TOKEN=<long-random-secret>
TAXONOMY_REVIEW_TOKEN=<long-random-secret>
OPERATIONS_RATE_LIMIT_REQUESTS=30
OPERATIONS_RATE_LIMIT_WINDOW_SECONDS=60
```

Use a distinct review token for protected operations and legacy archive reads.
These endpoints fail closed when credentials are absent. The mutation token
is required for taxonomy writes. Taxonomy run listing, detail and topic evidence
reads need no credentials and do not consume the operator rate limit.
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

Migration 041 reconciles older candidates whose terminal failed or cancelled
stage left the run and singleton job active. It marks those runs/jobs failed
without changing frozen stage results, release attestations, or publication.
After deployment, a failed release gate remains nonpublishable. The dashboard
reports the latest candidate's bounded first-run, terminal-failure, or
quality-blocked state. Protected `/operations/summary` uses that same latest
candidate status; a newer active candidate takes precedence over stale failed
history. Check the candidate and stage IDs before an explicit retry.

## Google Sheets importer

The default local `google-sheets` service reads append-only Google Form
response sheets with a read-only service account. Store credentials outside
the repository and share the spreadsheet with the service-account email.

```bash
GOOGLE_SHEETS_CREDENTIALS_FILE=/secure/google-sheets.json \
  docker compose up
```

The default credential path is `.secrets/google-sheets.json`; configure a
different path in `.env` to keep the startup command short. Missing credentials
fail the importer’s file preflight before polling starts. In explicit production
mode enable the `google-sheets` profile.

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
Use the complete custom-format backup: it contains `article_publications` and
`article_publication_themes` in addition to taxonomy runs and the immutable
legacy archive. `verify-legacy-archive-restore.sh` compares the public
projection and theme-snapshot counts as part of its isolated restore check.
Do not reconstruct public data from the current taxonomy: approval snapshots
are immutable, and taxonomy lineage changes never rewrite them.

### 2026-09-23 taxonomy recovery

The affected local PostgreSQL container did not exit because of a PostgreSQL
error. Docker recorded a stale Docker Desktop/WSL bind source for
`/docker-entrypoint-initdb.d/01-enable-pgvector.sql`; recreating the container
from the current Compose file was required. A read-only populated clone first
verified the complete 040-to-043 migration and lifecycle repair. The affected
installation was then backed up and recovered on 2026-09-24 with matching
rebuilt images; its failed attestation remains nonpassing and no taxonomy was
published. The retained physical backup is
`triage-postgres-pre-recovery-20260923`. See the exact commands, evidence, and
stop conditions in the [dated recovery verification](reviews/taxonomy-recovery-verification-2026-09-23.md).

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

Published-run readers remove `taxonomy_state` from `/inputs`; processing status
is unchanged and empty associations are normal. Dashboard counts describe
only the published run's snapshot. Protected `taxonomy_runs` operations metrics
now include its ID, with-topic/without-topic counts and nullable full/partial
coverage. Candidate processing and integrity failures use existing bounded
status codes; a published partial run remains usable during replacement.
Topic generation freezes a single database snapshot at job creation and uses
the recorded run when persisting article topic tags. No theme is required.
The completed partial-taxonomy plan records its disposable verification. The
later local development activation is recorded in [Current state](current-state.md). The admin Taxonomy review screen loads automatically without a
credential form. Its internal read APIs require no review or mutation token and
have no operator rate limit. Run review has manual refresh/retry and no polling.
Taxonomy writes, operations telemetry and legacy archive reads retain their
existing credential requirements. The public edge continues to deny admin
review pages and APIs. See [ADR-0004](decisions/0004-token-free-taxonomy-review.md).
Deploy matching API/admin images after the existing 044–048 migration/backup
procedure; PTR-6 introduces no additional migration or deployment setting.
