# Taxonomy recovery verification — 2026-09-23

Status: repository/disposable verification completed 2026-09-23; the affected
local installation was recovered with explicit approval on 2026-09-24. Starting revision:
`1b7a6c7fa9774f24cfa93abcbad010623060da57` plus the preserved TR-1/TR-2/TR-3
working tree recorded in the archived delivery plan.

## Observed failure cause

`docker inspect triage-organisation-processor-postgres-1` records exit code 127
and this OCI runtime error:

```text
error mounting ... to /docker-entrypoint-initdb.d/01-enable-pgvector.sql:
not a directory: Are you trying to mount a directory onto a file (or vice-versa)?
```

The stopped container refers to an obsolete Docker Desktop/WSL bind-mount
source under `/run/desktop/mnt/host/wsl/docker-desktop-bind-mounts/...`. Its
retained PostgreSQL log shows ordinary checkpoints and no database crash at the
end. The database named volume remains present. Recreating the container from
the current Compose file resolves the bind source; merely starting the old
container cannot.

## Verification performed

The original named volume was mounted read-only and copied to the disposable
volume `triage-tr3-recovery-copy-20260923`. The original was never mounted
writable. Before migration, the clone contained migrations through 040, run 1
was `running`, its singleton job was `pending`, and its
`ready_for_publication` stage was failed at attempt 3 with `valueerror`. Its
immutable release attestation failed `topic_acceptance_rate_low` and had input
hash `cb83d357c05a33117c57fec6ea684a8bd31c60194e16f280bd01f016f825359f`.

A custom-format `pg_dump` of the clone was 474,948 bytes with SHA-256
`be52af0c6588052040f8c4ac43fa58cde8ade41d32dcd8a6d87fab5a7e3fb3f9`;
`pg_restore --list` read all 541 TOC entries. The ordered migration runner then
applied 041, 042, and 043. Afterwards:

- run 1 and its singleton job were `failed` with bounded
  `candidate_failed` state;
- the failed attestation, failure reason, and input hash were unchanged;
- there were zero published runs, so the failed candidate was not promoted;
- the old automation decision retained `post_cutoff` membership for replay;
- the current scheduler image's `--healthcheck` accepted the upgraded schema.

The clone, its container, and the temporary dump were removed after validation.
The separate production-shaped journey used fresh tmpfs PostgreSQL, a real
Ollama `nomic-embed-text` endpoint, both evidence workers, the scheduler, and a
deterministic structured-chat fixture. Six inputs produced six persisted
embeddings, one cumulative six-row successor, seven completed stages, a passing
immutable attestation, and one automatic publication without an operator
mutation. Chat is deterministic in this check, so it proves protocol wiring and
lifecycle integration rather than the quality of a particular chat-model build.

## Affected-installation recovery result

On 2026-09-24 the database consumers were stopped and the original volume was
copied read-only to retained physical backup volume
`triage-postgres-pre-recovery-20260923`. A live custom-format logical backup was
also readable: 474,948 bytes, SHA-256
`dad64887e783397ea77b4a6e90360044320f4b48f363b08d59ba00f9c3ae4669`.
The current backend images were built, PostgreSQL was recreated from the valid
current mounts, and migrations 041–043 were applied before consumers restarted.

Live post-migration state matched the clone: run/job 1 are failed, the failed
attestation and hash are unchanged, and published count is zero. PostgreSQL,
API, scheduler, both evidence workers, article generation, Ollama, admin, and
public edge started; scheduler health passed; the admin proxy returns bounded
`taxonomy_quality_blocked`. Deployed image IDs were recorded by `docker compose
images`. Operator tokens are unconfigured, so the protected operations endpoint
correctly remains unavailable and was not used as acceptance evidence. The
temporary logical copy was removed after verification; the retained physical
backup remains until a normal post-recovery backup is independently verified.

## Recovery runbook for the affected installation

Do not proceed if the exact target project, volume, checkout, or backup target
cannot be established. These commands are for the Compose project and named
volume recorded above; substitute neither a different project nor an
unresolved variable.

1. Record the checkout and dirty state, verify the current mount sources are a
   file and directory, render Compose, and retain the stopped-container error:

   ```bash
   git rev-parse HEAD
   git status --short
   test -f infrastructure/postgres/init.sql
   test -d infrastructure/postgres/migrations
   docker compose config
   docker inspect triage-organisation-processor-postgres-1
   docker volume inspect triage-organisation-processor_postgres_data
   ```

2. Stop database consumers before making PostgreSQL available again. Create a
   physical backup volume while the source volume is stopped, mount the source
   read-only, and keep this backup until post-recovery validation and the next
   normal backup both succeed:

   ```bash
   docker compose stop api eligibility-segmentation embeddings taxonomy-scheduler article-generation
   docker volume create triage-postgres-pre-recovery-20260923
   docker run --rm \
     -v triage-organisation-processor_postgres_data:/source:ro \
     -v triage-postgres-pre-recovery-20260923:/backup \
     pgvector/pgvector:pg17 sh -c 'cp -a /source/. /backup/'
   ```

3. Build the matching checkout before migration and record immutable image IDs.
   Recreate only PostgreSQL so Docker resolves current bind sources, wait for
   readiness, create a custom-format logical backup, and verify it is readable:

   ```bash
   docker compose build api eligibility-segmentation embeddings taxonomy-scheduler article-generation
   docker compose images
   docker compose up -d --force-recreate postgres
   docker compose exec postgres pg_isready -U postgres -d triage
   docker compose exec -T postgres pg_dump -U postgres -d triage -Fc > triage-pre-041.backup
   pg_restore --list triage-pre-041.backup
   ```

4. Apply the ordered migrations with workers still stopped. Abort if migration
   041, 042, or 043 is absent, if the runner fails, or if the failed attestation
   changes:

   ```bash
   docker compose run --rm migrate
   docker compose exec -T postgres psql -U postgres -d triage -v ON_ERROR_STOP=1 -c \
     "SELECT filename FROM schema_migrations WHERE filename >= '041' ORDER BY filename;"
   docker compose exec -T postgres psql -U postgres -d triage -v ON_ERROR_STOP=1 -c \
     "SELECT id,status,error_summary FROM taxonomy_runs ORDER BY id; SELECT taxonomy_run_id,status,last_error FROM taxonomy_run_jobs ORDER BY taxonomy_run_id; SELECT taxonomy_run_id,gate_passed,failures,input_sha256 FROM taxonomy_release_attestations ORDER BY taxonomy_run_id; SELECT count(*) AS published_runs FROM taxonomy_runs WHERE status='published';"
   ```

   For the observed state, run/job 1 must be failed, its attestation must still
   be nonpassing with the recorded hash, and published count must remain zero.

5. Start only the matching rebuilt services. Require PostgreSQL and scheduler
   health, inspect bounded logs, then check the protected operations endpoint
   with a configured token. The expected first-run state is quality-blocked,
   not processing and not published:

   ```bash
   docker compose up -d --force-recreate api eligibility-segmentation embeddings taxonomy-scheduler article-generation public-web
   docker compose ps
   docker compose exec taxonomy-scheduler python -m triage_processor.taxonomy_scheduler --healthcheck
   docker compose logs --tail=200 postgres migrate taxonomy-scheduler api
   curl --fail-with-body --silent --show-error \
     -H "Authorization: Bearer $TAXONOMY_REVIEW_TOKEN" \
     http://127.0.0.1:8081/api/operations/summary
   ```

Stop and restore the complete physical backup volume or the verified logical
backup if migration fails before service restart. Do not edit or delete the
failed attestation, set publication state directly, or retry readiness to evade
the gate. Correct naming/evidence quality through a new cumulative candidate.

## Acceptance commands

```bash
docker compose -f compose.taxonomy-journey.yaml up -d --build --wait
docker compose -f compose.taxonomy-journey.yaml --profile acceptance run --rm journey
docker compose -f compose.taxonomy-journey.yaml --profile acceptance down -v
docker compose -f compose.test.yaml down
docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests
```

The journey passed with no skipped assertion. The fresh verification stack
passed 218 tests with zero skips. From `frontend/admin`, `npm test` passed nine
files with zero failures/skips; `npm run typecheck` and `npm run build` passed.
