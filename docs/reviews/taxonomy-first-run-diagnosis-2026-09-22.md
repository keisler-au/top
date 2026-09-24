# Taxonomy first-run diagnosis — 2026-09-22

This is a documentation-only review of the persistent first-run message:

> Taxonomy is being created for the first time. Wait for eligible evidence and
> the automatic candidate to finish.

No application code, schema, data, container, or deployment was changed. The
review started from clean revision
`1b7a6c7fa9774f24cfa93abcbad010623060da57`. It covers the complete path from
input preparation through automatic snapshotting, candidate stages, quality
attestation, publication, dashboard error mapping, operator telemetry, Compose,
and the tests that claim to prove that path. It also revalidates the relevant
AC-02, AC-03, AC-04, AC-06, AC-07, AC-08, and AC-09 contracts.

## Intended operational state

The current reference contract is clear about ordinary operation:

1. An eligible input is segmented when needed and embedded.
2. The taxonomy scheduler automatically freezes canonical evidence into one
   candidate and queues its durable stages.
3. The candidate progresses through clustering, topic naming, theme inference,
   reconciliation, quality, and readiness.
4. A passing immutable release attestation causes automatic publication. A
   failed attestation does not publish and produces a bounded, actionable
   quality state.
5. Readers use exactly one published run. Before the first publication they
   receive a truthful bounded unavailable state; routine success requires no
   operator action.

The reported message is valid only while evidence is genuinely being prepared
or an automatic candidate is genuinely progressing. It is incorrect for a
terminally failed candidate, incompatible evidence, disabled automation, a
stopped scheduler/database, or a failed quality gate.

## What happened in this installation

The original failure was not a lack of eligible evidence. Read-only inspection
before the database outage found candidate run 1 still marked `running`, with
its final `ready_for_publication` stage terminally failed after three attempts.
The quality stage had written a `taxonomy_release_attestations` row, but the
deployed readiness code looked for an obsolete `taxonomy_quality_snapshots`
row. It therefore raised `ValueError` on every readiness attempt. The deployed
failure path then failed only the stage and left the run and queue job active.

The candidate's release gate also failed independently: one of three topic
labels was accepted and two failed literal representative support. Correct
behaviour after lifecycle recovery is therefore `taxonomy_quality_blocked`,
with no publication. Bypassing that gate would violate AC-03.

Revision `1b7a6c7` already contains a source repair for the obsolete readiness
check and stranded lifecycle, plus migration
`041_repair_taxonomy_stage_recovery.sql`. The running images were built before
that revision and the migration log ends at migration 040. The exact reported
sentence is absent from the current tree and every reachable Git revision.
Consequently, the displayed UI, deployed backend, checked-out source, and
database schema do not form one identifiable release.

During this review PostgreSQL subsequently stopped with exit code 127. The API,
taxonomy scheduler, evidence workers, and article worker are now restarting
because the `postgres` hostname is unavailable. Admin requests return nginx
502 responses. PostgreSQL's retained log ends without the cause of that exit,
so this review does not invent one. This outage now prevents all taxonomy
progress and is separate from the earlier readiness-stage defect.

## Findings

Primary evidence is concentrated in these owners:

| Finding | Code, contract, or runtime evidence |
| --- | --- |
| TFR-01, TFR-02 | [`taxonomy_stages.py`](../../backend/src/triage_processor/taxonomy_stages.py), [`taxonomy_stage_quality.py`](../../backend/src/triage_processor/taxonomy_stage_quality.py), and [migration 041](../../infrastructure/postgres/migrations/041_repair_taxonomy_stage_recovery.sql) |
| TFR-03, TFR-04 | [backend Dockerfile](../../backend/Dockerfile), [admin Dockerfile](../../frontend/admin/Dockerfile), migration/container status, and bounded live logs recorded during this review |
| TFR-05 | [`taxonomy_automation.py`](../../backend/src/triage_processor/taxonomy_automation.py), [`taxonomy_clustering.py`](../../backend/src/triage_processor/taxonomy_clustering.py), [`taxonomy_stage_quality.py`](../../backend/src/triage_processor/taxonomy_stage_quality.py), and [Compose defaults](../../compose.yaml) |
| TFR-06 | [`embeddings.py`](../../backend/src/triage_processor/workers/embeddings.py), [`taxonomy_automation.py`](../../backend/src/triage_processor/taxonomy_automation.py), [`taxonomy_snapshots.py`](../../backend/src/triage_processor/taxonomy_snapshots.py), and the accepted [question-context plan](../archive/question-context-implementation-plan.md) |
| TFR-07 through TFR-09 | [`taxonomy_automation.py`](../../backend/src/triage_processor/taxonomy_automation.py), [`taxonomy_snapshots.py`](../../backend/src/triage_processor/taxonomy_snapshots.py), [AC-03](../architecture-contracts.md#ac-03--taxonomy-visibility-and-publication), and the [automatic taxonomy plan](../archive/automatic-taxonomy-work-packages.md) |
| TFR-10, TFR-11 | [dashboard route](../../backend/src/triage_processor/api/routes/dashboard.py), [operations route](../../backend/src/triage_processor/api/routes/operations.py), [admin client](../../frontend/admin/src/api/client.ts), and [admin errors](../../frontend/admin/src/api/errors.ts) |
| TFR-12 | [`taxonomy_automation.py`](../../backend/src/triage_processor/taxonomy_automation.py) and [`taxonomy_scheduler.py`](../../backend/src/triage_processor/taxonomy_scheduler.py) |
| TFR-13 | [`security.py`](../../backend/src/triage_processor/api/security.py), [AC-07](../architecture-contracts.md#ac-07--security-model-output-and-diagnostics), and [architecture-baseline R1](architecture-baseline.md#r1--high-operator-reads-can-accept-missing-credentials) |
| TFR-14 | [test Compose](../../compose.test.yaml), [taxonomy verification workflow](../../.github/workflows/taxonomy-verification.yml), and the [AT-WP3 criteria](../archive/automatic-taxonomy-work-packages.md#at-wp3--operator-visible-automation-and-delivery-verification) |
| TFR-15 | [operations reference](../operations.md), [documentation guide](../README.md), [archive index](../archive/work-packages.md), and [completed recovery plan](../archive/taxonomy-recovery-and-lifecycle-repair-work-packages.md) |
| TFR-16 | [admin nginx](../../frontend/admin/nginx/default.conf), [public nginx](../../frontend/public/nginx/default.conf), [API health](../../backend/src/triage_processor/api/main.py), and [Compose health wiring](../../compose.yaml) |

### TFR-01 — High — deployed readiness checks an artifact the quality stage does not write

The deployed readiness stage queries `taxonomy_quality_snapshots`, while the
sole current quality owner writes `taxonomy_release_attestations`. This makes a
successfully completed quality stage incapable of completing readiness. It is
the direct trigger for run 1's three final-stage failures.

Current source lines 332–337 of `taxonomy_stages.py` use the release
attestation, and the real PostgreSQL lifecycle test covers both passing and
failing attestations. That repair exists in Git but is not in the running
image. This is a deployed bug with an undeployed source repair, not a defect in
the current line 332 query.

### TFR-02 — High — the deployed terminal lifecycle strands the singleton queue

The deployed stage lifecycle contains three coupled bugs:

- Terminal `fail_stage` changes only the stage. It does not atomically fail the
  parent `taxonomy_runs` or `taxonomy_run_jobs` row, leaving the candidate
  apparently active and retaining the singleton queue slot.
- Explicit retry and cancellation change only the stage. They do not reacquire
  or release the parent queue lifecycle, so the documented recovery commands
  cannot restore a consistent candidate.
- Lease renewal, completion, and failure match only stage ID and owner. They do
  not include the claim attempt, allowing an old claim with a reused owner to
  act on a newer attempt.

Current source and migration 041 repair these cases and include transactional
PostgreSQL coverage. The live database has not applied that migration, so its
backfill has not reconciled the already-stranded run and job.

### TFR-03 — High — deployment contents are neither synchronized nor traceable to a revision

Backend/admin images are older than revision `1b7a6c7`, the database has only
migrations through 040, and the reported UI text is in neither the checkout nor
Git history. The Dockerfiles embed no commit/revision label and the application
has no build-version endpoint. Operators cannot establish which code produced
the message from the running artifacts.

This drift also makes a source-only diagnosis unsafe: rebuilding the backend
without applying migration 041 would deliberately fail the scheduler health
check, while applying the migration without rebuilding would leave the obsolete
readiness implementation in place.

### TFR-04 — Critical operational condition — the current stack has no database

`docker compose ps -a` reports PostgreSQL exited with code 127. The API and all
database workers repeatedly fail name resolution for `postgres`; admin requests
receive 502. The retained PostgreSQL logs do not establish why the container
exited. Database recovery and cause analysis are required before any candidate
can progress, but were outside this documentation-only instruction and no
service was restarted.

### TFR-05 — High — the default policy admits a candidate that clustering cannot process

Automation defaults `TAXONOMY_AUTOMATION_MINIMUM_EVIDENCE` to 1. Its snapshot
configuration omits clustering sizes, so clustering defaults to
`min_cluster_size=3` and `min_samples=2`. A diagnostic call through the real
clusterer with one evidence row raised `ValueError: k must be less than or equal
to the number of training points`. Two rows became 100% noise and necessarily
failed the release gate.

On a fresh installation, the documented default can therefore create a first
candidate that is structurally unable to pass. With the deployed lifecycle bug
it becomes stranded; with current source it becomes a terminal failed
candidate. The admission threshold and clustering/gate minimums need one shared
validated contract.

### TFR-06 — High — generic evidence is excluded or makes mixed snapshots invalid

The embedding worker correctly records `answer-only` for generic inputs and
`question-answer` for contextual inputs. The accepted question-context design
says this column is descriptive and both kinds occupy one global vector space.
Automation instead defaults to `question-answer`, filters its eligibility count
by that value, and requires every canonical row in the snapshot to have the
same representation.

The resulting failures are deterministic:

- A generic-only installation waits forever for “minimum evidence” even though
  its inputs are complete and embedded.
- A mixed generic/contextual installation counts only contextual rows during
  admission, then rejects the canonical snapshot for representation mismatch.
- If every row uses a nonconfigured model, representation, or dimension, the
  inner join used by admission reports zero evidence instead of the bounded
  `snapshot_invalid` state used for a partial mismatch.

This contradicts the implemented input contract that generic inputs remain
valid and prevents a first taxonomy for supported data.

### TFR-07 — High — evidence that becomes ready after a publication cutoff is lost forever

The published checkpoint stores a run's snapshot timestamp. Later eligibility
and snapshots require the input or segment's creation timestamp to be greater
than that checkpoint. Consider an input created before a snapshot while its
eligibility or embedding job is still running: it is absent from that snapshot,
but when it later reaches `ready_for_analysis`, its creation timestamp remains
older than the published cutoff. No later automatic snapshot can select it.

The cutoff needs to represent membership/readiness correctly, or selection
must otherwise prove that every canonical target omitted before publication is
eligible later. The present implementation violates TR-A3 and AC-02's shared
canonical semantics.

### TFR-08 — High — one failed quality candidate permanently stops automatic successors

A nonpassing release attestation leaves the run `ready_for_review`, which is a
valid review state. Automation records `quality_gate_failed`, but immediately
treats every `ready_for_review` run as an active candidate and returns before it
examines newer evidence. New eligible evidence therefore cannot create a new
automatic candidate until an operator explicitly rejects the old one.

This conflicts with the archived automation contract: unchanged failed evidence
must be suppressed, while new eligible evidence must be able to change the
decision. It also turns an ordinary quality miss into mandatory operator action
despite the stated automatic operating model.

### TFR-09 — High design conflict — replacement publication loses historical coverage

Later automatic snapshots contain only evidence whose input/segment creation
time is after the prior published cutoff. Publication then supersedes the one
old published run, while every reader resolves only the new run. Evidence that
was classified in the old run is absent from the new run and becomes
`pending_classification` to current readers.

The archived automation plan explicitly selected post-cutoff-only candidates,
but AC-03 now records cumulative versus post-cutoff membership as an unresolved
product/data decision. The “one published run serves every reader” contract
cannot preserve historical coverage with a delta-only replacement unless the
new run also carries forward prior membership/taxonomy state. The required end
state must be chosen before this boundary can be repaired.

### TFR-10 — High — the first-run API and admin UI collapse actionable states into “wait”

The unprotected dashboard endpoints look only for a publication, any historical
nonpassing attestation, and any failed run/stage. They do not inspect the
automation checkpoint, evidence queue, scheduler state, policy-disabled state,
debounce, incompatible embeddings, or the active candidate's stage. As a
result, `taxonomy_first_run` covers all of the following:

- no inputs;
- evidence genuinely being prepared;
- an automatic candidate progressing;
- automation disabled;
- all eligible embeddings filtered out by configuration;
- an unexpected automation exception that was only logged;
- a scheduler that is not running.

The protected operations endpoint has a richer aggregate contract, but the
admin client defines no operations types or request, supplies no operator
authorization, and renders none of those states. It also has no candidate list
or stage identifier with which to follow its own retry guidance. This is the
undelivered AT-WP3 operator-visibility scope, despite reference documentation
claiming it shipped.

### TFR-11 — Medium — operations status can be dominated by stale or unrelated history

`/operations/summary` reports `blocked_by_quality` if any running, failed, or
reviewable run has ever recorded a failed attestation, before considering a
newer active or published run. An old nonpassing candidate left in one of those
states can therefore keep the system blocked after a later successful
publication. Its
`candidate_failed` flag is based on the newest run of any origin, rather than
the current automatic decision. `preparing_evidence` counts input statuses but
does not distinguish terminally failed preparation jobs.

These queries do not identify the current policy decision and can send an
operator toward an obsolete candidate.

### TFR-12 — Medium — unexpected automation failures are not durably bounded

Only `SnapshotValidationError` is translated to a durable bounded failure.
Other exceptions escape `evaluate_automation`; the scheduler catches them,
logs a stack trace, and continues polling. A reserved decision can then replay
the same persistent failure every poll without attempt count, backoff, terminal
state, or API-visible reason. The scheduler comment says policy state records
bounded failures, but that is false for this path.

This violates the durable failure/retry requirements in AC-03 and AC-04 and is
another way the dashboard can show a permanent first-run wait.

### TFR-13 — High security defect — single-token operator reads fail open

`require_operator` permits a review read when either the mutation or review
token matches. If exactly one token is configured, the other configured value
is the empty string. A missing/malformed bearer token also produces the empty
string, so `compare_digest("", "")` authorizes the request. Mutation routes do
not have the same OR condition, but protected operations and candidate reads
violate AC-07 and the API documentation.

The integration suite covers both-token, no-token-configuration, and valid
mutation-token reads. It does not cover anonymous reads with only one token
configured. This finding was previously recorded as architecture-baseline R1
and remains present at revision `1b7a6c7`.

### TFR-14 — High delivery defect — no test proves the claimed automatic Compose journey

The archived AT-WP3 acceptance requires a built Compose journey from input,
through the evidence workers and taxonomy scheduler, to automatic publication.
`compose.test.yaml` contains PostgreSQL, API, public nginx, and a test runner;
it contains no evidence workers, taxonomy scheduler, or Ollama. The integration
test seeds embeddings directly, calls automation/stage functions in-process,
and mocks clustering/model responses.

Those are useful database integration tests, but they cannot prove production
Compose wiring, worker startup, model compatibility, health, or the no-operator
journey. The archive index labels AT-WP3 complete while the plan itself still
labels it planned. CI also watches the obsolete `frontend/src/api/**` path and
runs no admin typecheck/tests. The completion claim therefore lacks its required
acceptance evidence.

### TFR-15 — Medium — operations documentation contradicts the runtime

The operations guide says the scheduler “never publishes” its durable candidate
even though automatic promotion is implemented and described a few lines
earlier. It documents release gate v1 and omits the reconciled-theme threshold,
while source uses `taxonomy-release-gate-v2`. The documentation guide says
there is no current work-package file even though `docs/work-packages.md`
exists, and the current plan's next action describes lifecycle repairs already
present in revision `1b7a6c7`.

These contradictions make the intended recovery and release state harder to
establish and violate DC-01/DC-06. They are recorded here rather than silently
corrected because this review was instructed not to fix bugs.

### TFR-16 — Medium operational defect — web and API health can be green while user journeys fail

Both nginx services answer `/healthz` locally with unconditional 200 responses.
The API health endpoint performs no database query after startup. Compose can
therefore show the admin/public edge healthy after its required upstream is
gone; that happened during this review while admin API requests returned 502.
The endpoint is a valid process-liveness signal but is used as if it were
readiness for a dependency-backed user journey.

## Verification and limits

The following checks were run against revision `1b7a6c7` before this report was
written:

- `env UV_CACHE_DIR=/tmp/triage-uv-cache uv run python -m unittest discover -s tests -v`
  from `backend`: 201 tests passed; 36 database/public-edge tests skipped because
  their external test environment was absent.
- `npm test`, `npm run typecheck`, and `npm run build` from `frontend/admin`:
  all passed.
- `docker compose -f compose.test.yaml up --build --abort-on-container-exit
  --exit-code-from tests`: 201 tests passed with no skips in the isolated
  PostgreSQL/public-edge stack.
- A read-only review of production Compose status/logs and, before PostgreSQL
  stopped, bounded taxonomy run/stage/attestation state.
- A local pure diagnostic of the real HDBSCAN wrapper and release gate with one
  and two evidence rows; it confirmed TFR-05 without database mutation.

The passing suite establishes the current source repair for TFR-01/TFR-02 and
many lower-level boundaries. It does not cover the worker-to-publication Compose
journey identified in TFR-14, and it has no regressions for TFR-05 through
TFR-13. No production service was restarted, no migration was applied, and no
production row was changed.

## Open product decision

One decision is required before implementation: after a replacement taxonomy is
published, should the sole published run contain all eligible historical
evidence through its cutoff, or should it process only post-cutoff evidence and
explicitly carry prior classifications/taxonomy state forward? The first is the
smaller model consistent with current one-run readers. The second requires a
defined merge/carry-forward model. The current delta-only replacement provides
neither continuity mechanism.

## Handoff

The safe recovery sequence, if separately authorized, is to establish why
PostgreSQL exited and restore it, deploy one identifiable revision with its
matching migrations (including 041), verify the stranded run is reconciled,
and confirm the UI changes from a false first-run state to the truthful failed
quality state. Source fixes for TFR-05 through TFR-16 then require their own
acceptance tests and the evidence-continuity decision above. A failed gate must
remain nonpublishable throughout.
