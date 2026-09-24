# Batch-taxonomy and public-website work packages

**Status: archived — complete.** Every BT and PW package in this delivery plan
has completion evidence recorded below. It is retained as the historical
delivery record for the run-scoped batch taxonomy and public website; it is not
an implementation plan. Its automation successor and recovery evidence are in
the [completed taxonomy recovery plan](taxonomy-recovery-and-lifecycle-repair-work-packages.md).

This historical plan first made the run-scoped batch
taxonomy the sole production taxonomy and retires the incremental topic/theme
implementation. It then delivers the public, read-only article library on the
batch-only contracts. It supersedes the operational-reliability plan, which
deliberately retained the legacy path.

## Pipeline at a glance

At the time of delivery this was the sole current work-package document. All
packages below are complete and their recorded evidence is retained for audit;
the active plan is the automation programme.

| Package | Status | Dependency | Completion evidence to record here |
| --- | --- | --- | --- |
| BT-WP1 immutable snapshot and lifecycle | **Complete** | None | Migrations `023`–`024`; focused unit suite and PostgreSQL+pgvector integration job passed |
| BT-WP2 leased/resumable pipeline | **Complete** | BT-WP1 | Migrations `025`–`027`; deterministic leased-stage suite and PostgreSQL+pgvector integration job passed |
| BT-WP3a published-run reader boundary | **Complete** | BT-WP2 | Published-run dashboard contract; 183-test PostgreSQL+pgvector job passed |
| BT-WP3b stable theme identity and lineage | **Complete** | BT-WP3a | Migration `028`; PostgreSQL+pgvector lineage-resolution verification passed |
| BT-WP3c article and generation contract migration | **Complete** | BT-WP3b | Migration `029`; 183-test PostgreSQL+pgvector article/generation contract job passed |
| BT-WP3d input and frontend contract cutover | **Complete** | BT-WP3c | Input coverage/frontend contract job |
| BT-WP4a scheduler deployment and health | **Complete** | BT-WP3d | Compose health/cadence job and configuration version |
| BT-WP4b computed quality and release gate | **Complete** | BT-WP4a | Deterministic quality/gate job and threshold version |
| BT-WP4c protected operations and publication API | **Complete** | BT-WP4b | Authorization/rate-limit/operations job |
| BT-WP5 migration and upgrade fixtures | **Complete** | BT-WP4c | PostgreSQL upgrade-fixture CI artifact |
| BT-WP6a publication proof | **Complete** | BT-WP5 | First-publication artifact and published-run ID |
| BT-WP6b rollback and cutover proof | **Complete** | BT-WP6a | Rollback/cutover artifact |
| BT-WP7a legacy archive | **Complete** | BT-WP6b | Migrations `034`–`035`; PostgreSQL archive checksum, immutability, upgrade, and rollback verification passed |
| BT-WP7b legacy runtime removal | **Complete** | BT-WP7a | Migration `036`; 172-test PostgreSQL+pgvector clean-install/upgrade job passed |
| BT-WP7c destructive legacy schema removal | **Complete** | BT-WP7b | Migration `037`; 172-test PostgreSQL+pgvector upgrade/clean-install suite and complete-backup restore verification passed |
| BT-WP8 hardening and documentation closure | **Complete** | BT-WP7c | 175-test PostgreSQL+pgvector CI-equivalent run, frontend verification, retirement guard, and documentation review passed |
| PW-WP1a admin relocation | **Complete** | BT-WP8 | `frontend/admin` npm build/test artifact, Compose admin-profile topology, and 177-test PostgreSQL+pgvector verification passed |
| PW-WP1b public edge isolation | **Complete** | PW-WP1a | Dependency-free `public-web` nginx edge; 180-test PostgreSQL+pgvector Compose isolation run passed |
| PW-WP2a public projection schema/backfill | **Complete** | PW-WP1b | Migration `038`; 181-test PostgreSQL+pgvector schema/backfill verification passed |
| PW-WP2b approval projection transaction | **Complete** | PW-WP2a | Atomic approval/reapproval projection and rollback verification; 183-test PostgreSQL+pgvector run passed |
| PW-WP3a server-rendered public query routes | **Complete** | PW-WP2b | Internal `/_site` public-projection renderer; 184-test PostgreSQL+pgvector route/HTML verification passed |
| PW-WP3b public-edge rewrites and 404s | **Complete** | PW-WP3a | Named nginx rewrites and edge 404 topology; 184-test PostgreSQL+pgvector Compose run passed |
| PW-WP4 public interface and accessibility | **Complete** | PW-WP3b | Public-only responsive CSS and HTML contract; 185-test PostgreSQL+pgvector Compose run passed |
| PW-WP5 discovery, caching, and public security | **Complete** | PW-WP4 | Public-site configuration v1; 187-test PostgreSQL+pgvector Compose header/sitemap/security run passed |
| PW-WP6 public end-to-end verification and operations | **Complete** | PW-WP5 | 189-test PostgreSQL+pgvector Compose E2E run, public lifecycle fixture, restore projection verification, and documentation review passed |

The completion and delivery discipline below is retained as historical context.
The document was archived after every package completed; follow the current
[documentation guide](../README.md#documentation-maintenance-process) for new
work.

**Completion discipline.** A request to complete a work package authorizes all
of its objective, work, and automated acceptance criteria. Do not stop at a
foundation, partial implementation, or intermediate green test run; continue
until every criterion is verified and its evidence is recorded, unless an
external blocker prevents further work. Before any final response, maintain
and reconcile an explicit checklist containing every Objective, Work, and
Automated acceptance-criteria bullet against the implementation and evidence.
A passing focused test, a completed migration, a coherent implementation
slice, or a progress update is a checkpoint only—not a terminal condition.
Report progress in commentary and continue automatically; report completion
only after the checklist is empty, the status is **Complete**, and completion
evidence is recorded. If an item remains and there is no external blocker,
continue implementing it rather than reporting the gap.

The PW packages are deliberately not eligible to start until **BT-WP8 is
complete**. They are in this document so the entire approved pipeline is
visible, but they must not be run in parallel with the batch-taxonomy cutover
or legacy-taxonomy retirement.

## Target state

```text
input -> eligibility and segmentation -> embeddings
      -> immutable batch snapshot -> durable staged batch run
      -> one published run -> every taxonomy reader and generator

legacy topic strings, legacy themes, and their worker history
      -> immutable, queryable archive (not a live fallback)
```

The retained incremental steps prepare raw evidence only. The retired steps
are per-input topic assignment, per-topic theme inference/materialization,
their `worker_jobs` stages, string-keyed live taxonomy reads, and their
runtime services. The archive preserves the historical classifications,
themes, suggestions, and links needed to interpret older articles or audit a
migration; no production reader may select it as taxonomy state.

## Repository baseline and gaps

Migrations 015–023 and `taxonomy_*` modules establish useful candidate
building blocks: run-scoped records, clustering, topic and theme attempts,
publication scaffolding, a run queue, rollout reports, and quality snapshots.
They are not a production implementation:

- BT-WP1 now provides an atomic live-corpus snapshot creator, but its required
  PostgreSQL integration verification remains pending;
- the scheduler infers stage completion from row presence, has no per-stage
  lease/heartbeat, and candidate LLM stages hold database transactions while
  calling the model;
- publishing requires mutable operator sign-off scaffolding, has no
  deployment-default-off gate or prior-run rollback command, and is not yet
  backed by complete lifecycle coverage;
- dashboard SQL has a legacy fallback, while input detail, article creation,
  generation, and legacy theme/article relationships are not all run-scoped;
- `compose.yaml` still starts `topics` and `themes`; it does not start the
  taxonomy scheduler; and
- operations metrics and quality decisions are partial. In particular, the
  quality endpoint accepts caller-supplied signals instead of computing and
  attesting to them from durable facts.

Packages below remove those gaps in order. A package is complete only when its
automated acceptance criteria pass in CI against PostgreSQL with pgvector.
There is no human sign-off, UI checklist, or manually supplied release signal.

## Global invariants

- A run uses one transactionally captured cutoff and one canonical evidence
  unit per original input: its segments when any existed at the cutoff,
  otherwise the original. It never includes both.
- A run records and validates vector model, representation, dimension,
  algorithm/configuration hashes, prompt versions, and model identifiers.
- Candidate records and audit payloads are immutable once written. All
  mutations are idempotent and safe after a worker restart.
- At any instant every production taxonomy reader resolves exactly one
  published run. There is never a legacy/batch fallback or mixed-run result.
- Topic and theme identities, their revisions/lineage, article taxonomy
  snapshots, citations, and approved article revisions are durable across
  rename, split, merge, retirement, publication, rollback, and legacy
  archival.
- Raw evidence, prompt payloads, model output, credentials, and unrestricted
  errors never appear in public, dashboard, or operations responses.
- Production publication is disabled unless a machine-evaluated gate passes;
  it is an explicit authenticated operation, never an automatic scheduler
  action.

## Delivery sequence

```text
BT-WP1 immutable snapshot and run lifecycle
   -> BT-WP2 leased, resumable batch stages
   -> BT-WP3a reader boundary -> BT-WP3b identities -> BT-WP3c articles -> BT-WP3d input/frontend
   -> BT-WP4a scheduler -> BT-WP4b quality/gate -> BT-WP4c protected operations
   -> BT-WP5 upgrade fixtures -> BT-WP6a publication -> BT-WP6b rollback/cutover
   -> BT-WP7a archive -> BT-WP7b runtime removal -> BT-WP7c schema removal
   -> BT-WP8 post-retirement hardening and documentation closure
   -> PW-WP1a admin relocation -> PW-WP1b public edge isolation
   -> PW-WP2a projection schema/backfill -> PW-WP2b approval transaction
   -> PW-WP3a server routes -> PW-WP3b public-edge rewrites
   -> PW-WP4 public interface and accessibility
   -> PW-WP5 discovery, caching, and public security
   -> PW-WP6 public end-to-end verification and operations
```

## BT-WP1 — Immutable snapshot creation and lifecycle foundation

### Objective

Create a runnable run directly from the live corpus without hand-written SQL,
and represent its lifecycle explicitly rather than inferring it from child
rows.

### Work

- Add a `create_taxonomy_run` service plus operator API and CLI. Accept an
  idempotency key and an explicit, versioned batch configuration. The shared
  authentication/authorization boundary for every taxonomy mutation endpoint is
  delivered together in BT-WP4c rather than partially here.
- In one PostgreSQL transaction, take the database cutoff; select eligible,
  completed canonical evidence and matching embeddings; insert the run and
  `taxonomy_run_evidence`; calculate deterministic source/configuration hashes;
  then commit. Enqueue only after that commit.
- Reject and report bounded counts for zero evidence, missing vectors,
  duplicate canonical targets, vector model/representation/dimension mismatch,
  invalid configuration, and an already-active idempotency key. A failure
  leaves no partial run, evidence, or queue job.
- Add a durable `taxonomy_run_stages` state model for `snapshot`, `clustering`,
  `topic_naming`, `theme_inference`, `theme_reconciliation`, `quality`, and
  `ready_for_publication`. Store attempt, status, lease, heartbeat, timestamps,
  bounded error class, and stage input/output hashes.
- Tighten migrations 015–022 through additive migrations only. Update
  `init.sql` and its seeded migration list in the same change.

### Automated acceptance criteria

- PostgreSQL integration tests prove a late input is wholly excluded, a
  segmented original supplies only segments, and an unsegmented original
  supplies only itself.
- Repeating an idempotency key returns the original complete snapshot without
  changing membership; a rollback leaves no residual record.
- Constraints reject invalid lifecycle transitions and candidate inserts after
  a terminal stage/run state.
- Snapshot tests cover empty, duplicate, missing-vector, model mismatch,
  representation mismatch, dimension mismatch, and concurrent-create cases.

### Completion evidence

- Implemented in migrations `023_add_taxonomy_run_snapshots.sql` and
  `024_add_taxonomy_run_stages.sql`,
  `taxonomy_snapshots.py`, `POST /taxonomy-runs`, and the
  `triage_processor.taxonomy_snapshots` CLI.
- Focused snapshot and candidate-taxonomy unit tests passed with
  `uv run python -m unittest tests.test_taxonomy_snapshots tests.test_taxonomy_clustering tests.test_taxonomy_experiment tests.test_taxonomy_topics tests.test_taxonomy_themes tests.test_taxonomy_quality -v`.
- The complete Python unit suite passed: 150 tests, with 10 PostgreSQL
  integration tests skipped because their database service is unavailable.
- PostgreSQL+pgvector integration tests covering canonical evidence,
  idempotency, and transaction rollback passed with
  `docker compose -f compose.test.yaml up --build --abort-on-container-exit
  --exit-code-from tests`.

## BT-WP2 — Leased, deterministic, resumable batch pipeline

### Objective

Make clustering, topic naming, theme inference, reconciliation, and quality
safe to resume, retry, and operate from their durable stage state.

### Work

- Replace the scheduler's row-existence heuristics with claim/renew/complete/
  fail operations on `taxonomy_run_stages`. A worker must own a current lease
  before it writes; heartbeats and bounded backoff reclaim expired work safely.
- Move all LLM/network calls outside database transactions. Persist bounded
  request context, response, validation result, and deterministic attempt
  identity in short transactions before and after each call.
- Finish cluster persistence: probabilities/noise decisions, vector dimensions,
  deterministic ordering, central/diverse representative policy, and complete
  per-run configuration provenance.
- Strengthen topic validation with literal-support, granularity, normalized
  duplicate, empty/mixed-cluster, and failed-attempt rules. Persist a rejected
  result rather than silently creating a topic.
- Implement deterministic candidate-theme reconciliation with antecedent links;
  it may consolidate output but never rewrites/deletes raw candidates or
  attempts.
- Add an explicit stage worker to Compose, configuration validation, health
  checks, structured safe logging, and cancellation/retry commands.

### Automated acceptance criteria

- Fault injection before and after every durable write produces the same final
  candidate data as an uninterrupted run.
- Two workers cannot complete the same claimed stage; a stale lease is
  reclaimable and the old worker cannot subsequently write.
- Deterministic fixtures cover noise, singleton, duplicate-source,
  zero-vector, segmented evidence, duplicate topic, failed label, and
  overlapping/reconciled themes.
- No test uses a live LLM or network: structured client fixtures produce all
  model results.

### Completion evidence

- Implemented through migrations `025_add_taxonomy_stage_retry_schedule.sql`,
  `026_add_taxonomy_theme_reconciliation.sql`, and
  `027_add_taxonomy_model_request_audit.sql`; the leased worker is
  `triage_processor.taxonomy_scheduler` and runs as `taxonomy-scheduler` in
  Compose.
- Candidate writes, including the pre-model-call request audit, verify the
  current stage lease. Model calls occur outside database transactions and use
  immutable request identities and bounded audit payloads.
- Focused deterministic suite passed: 35 tests. The disposable
  PostgreSQL+pgvector verification stack passed: 182 tests.

## BT-WP3a — Published-run reader boundary

### Objective

Make every dashboard taxonomy reader resolve one published run, or return the
bounded `taxonomy_unavailable` contract. This package deliberately does not
change article, input, generation, or frontend writes.

### Work

- Create a shared published-run query layer. Migrate dashboard summary/list/
  detail/evidence/recommendations to it.
- Replace the SQL branch that falls back to `original_inputs.topic`,
  `segment_inputs.topic`, `themes`, and `theme_topics` in those readers.
  Before the first batch publication, expose `taxonomy_unavailable` rather
  than silently returning legacy classifications.

### Automated acceptance criteria

- Contract tests prove every dashboard reader uses the same published run and
  queries no legacy topic/theme table.
- Tests cover a missing published run, numeric IDs, aliases, unclassified
  evidence, and paginated aggregate consistency.

### Completion evidence

- Dashboard summary, taxonomy list/detail/evidence, and article
  recommendations now require one published run and return bounded
  `taxonomy_unavailable` before first publication.
- Dashboard evidence and taxonomy aggregates read frozen run evidence and
  run-scoped candidate records only; no legacy topic or theme fallback remains.
- The disposable PostgreSQL+pgvector verification stack passed all 183 tests
  with `docker compose -f compose.test.yaml up --build --abort-on-container-exit
  --exit-code-from tests`.

## BT-WP3b — Stable theme identity and lineage

### Objective

Replace run-local candidate-theme IDs with stable theme identities, immutable
run revisions, and deterministic lineage resolution.

### Work

- Materialize accepted/reconciled candidate themes into stable identities and
  run-scoped revisions as part of publication preparation; candidate rows stay
  immutable audit data.
- Store stable theme IDs and display-name snapshots on all new associations.
- Implement rename, split, merge, and retirement lineage; aliases with more
  than one valid successor return an explicit ambiguous compatibility result.

### Automated acceptance criteria

- Numeric IDs, aliases, renamed, split, merged, retired, and ambiguous cases
  resolve deterministically in PostgreSQL tests.
- A later candidate run cannot mutate an earlier theme revision or lineage.

### Completion evidence

- Migration `028_add_taxonomy_theme_identities.sql` materializes reconciled
  themes into immutable stable identities and run revisions, records
  continuation, rename, split, merge, retirement, and new lineage, and
  resolves published numeric identities deterministically (including ambiguity).
- The disposable PostgreSQL+pgvector verification stack passed all 183 tests
  with `docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests`.

## BT-WP3c — Article and generation contract migration

### Objective

Move article creation, editing, citations, revisions, and generation targets
to stable published taxonomy IDs while preserving immutable historical output.

### Work

- Migrate article topic/theme links through explicit lineage mapping records;
  retain existing revision, citation, and display snapshots byte-for-byte.
- Require the shared published-run layer for article and generation taxonomy
  selection and frozen generation evidence.

### Automated acceptance criteria

- Article detail, tags, citations, revisions, and generation provenance remain
  byte-for-byte stable through rename, split, merge, retirement, publication,
  and rollback.

### Completion evidence

- Migration `029_add_article_taxonomy_snapshots.sql` records stable theme IDs,
  display snapshots, and frozen taxonomy-run provenance for article and
  generation associations. New article evidence resolves solely from published
  run evidence; queued generation retains its selected run through processing.
- Legacy theme aliases are mapped to their published stable identity only at
  write time, preserving historical article content while preventing new live
  taxonomy links.
- The disposable PostgreSQL+pgvector verification stack passed all 183 tests
  with `docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests`.

## BT-WP3d — Input and frontend contract cutover

### Objective

Expose published-run coverage consistently in input views and move typed
frontend contracts to stable IDs.

### Work

- Mark evidence after the published cutoff as pending classification; exclude
  it from aggregates and generation scopes until a later run covers it.
- Update input detail and all frontend taxonomy contracts to stable topic/theme
  IDs and explicit unavailable/ambiguous states.

### Automated acceptance criteria

- Input, frontend, and pagination tests agree on published-run coverage and
  expose no legacy taxonomy fields.

### Completion checklist

- [x] Objective — input views expose published-run coverage consistently and
  frontend contracts use stable topic/theme IDs.
- [x] Work — evidence after the published cutoff is pending classification and
  excluded from published taxonomy associations and scopes.
- [x] Work — input responses and frontend input contracts expose stable IDs and
  the explicit unavailable state, with no legacy `topic` field.
- [x] Automated acceptance criteria — input, frontend, and pagination tests
  agree on coverage and expose no legacy taxonomy fields.

### Completion evidence

- `GET /inputs` now reads only `taxonomy_run_evidence`, `topic_revisions`, and
  `theme_revisions` for the one published run. It returns stable topic/theme
  IDs with display snapshots, `taxonomy_state`, and
  `published_taxonomy_run_id`; uncovered evidence is
  `pending_classification`, and no published run is
  `taxonomy_unavailable`.
- `frontend/src/api/contracts.ts` defines the stable `InputTopic`,
  `InputTheme`, and `Input` contracts. The API reference and input retrieval
  documentation record the no-legacy-field and coverage behavior.
- Focused API coverage tests and the frontend typecheck/test job passed.
  The PostgreSQL+pgvector verification stack passed all 187 tests, including
  published, pending, unavailable, legacy-exclusion, and pagination coverage,
  with `docker compose -f compose.test.yaml up --build
  --abort-on-container-exit --exit-code-from tests`.

## BT-WP4a — Scheduler deployment and health

### Objective

Deploy the leased candidate scheduler safely, with its cadence and readiness
contract machine-verifiable.

### Work

- Run the scheduler in Compose with one-active-run enforcement, configurable
  cadence, safe shutdown, migrations/pgvector readiness checks, and worker
  health checks. Scheduled runs always remain candidates.

### Automated acceptance criteria

- Health checks fail on missing migration, unavailable pgvector, database loss,
  and inability to claim scheduled work.

### Completion checklist

- [x] Objective — the candidate scheduler is deployable with a
  machine-verifiable cadence and readiness contract.
- [x] Work — Compose starts it only after migrations and dependencies are
  ready; the database enforces one active candidate, cadence/configuration is
  versioned, and shutdown has a bounded graceful period.
- [x] Work — health verifies the current durable migration marker, pgvector,
  database reachability, and durable claim privileges. It does not publish.
- [x] Automated acceptance criteria — tests cover missing migration, missing
  pgvector, database loss, and inability to claim scheduled work.

### Completion evidence

- `taxonomy-scheduler` has a Compose health check, migration/dependency gate,
  `stop_grace_period: 2m`, versioned
  `TAXONOMY_SCHEDULER_CONFIGURATION_VERSION`, and bounded cadence/lease/retry
  settings. `taxonomy_run_jobs_one_active` remains the database-level global
  one-active-candidate constraint.
- `check_health()` now fails closed on a missing `029` migration marker,
  unavailable `vector` extension, database error, or missing select/update
  access to `taxonomy_run_stages` or `taxonomy_run_jobs`.
- The documented Compose configuration passed `docker compose config`; focused
  scheduler/Compose tests passed; the PostgreSQL+pgvector verification stack
  passed all 194 tests with `docker compose -f compose.test.yaml up --build
  --abort-on-container-exit --exit-code-from tests`.

## BT-WP4b — Computed quality and release gate

### Objective

Make the release decision reproducible from durable candidate facts and
prevent publication unless that machine-evaluated decision passes.

### Work

- Compute bounded, aggregate-only completeness, noise, topic-acceptance, and
  duplicate-topic metrics from a frozen run after candidate materialization.
  Do not accept caller- or operator-supplied release signals.
- Persist exactly one immutable release-gate attestation per run, including
  metrics, thresholds, a threshold version, failures, and a deterministic hash
  of every gate input. The leased quality stage is the sole attestation writer.
- Enforce the attestation in the database publication function and keep the
  deployment publication switch explicitly default-off. Document the threshold
  version and the absence of a manual quality endpoint.

### Automated acceptance criteria

- Deterministic fixtures prove exact-boundary pass and each aggregate failure;
  no quality test calls a live model or submits release signals.
- PostgreSQL verification proves an attestation is computed from run facts,
  retrying does not replace it, and update/delete attempts are rejected.
- With the deployment switch absent or false, publication is rejected; an
  absent or failed database attestation also prevents publication.

### Completion checklist

- [x] Objective — release decisions are reproducible from durable candidate
  facts and cannot be manually supplied.
- [x] Work — quality aggregates and gate results are computed by the leased
  quality stage using a versioned threshold policy.
- [x] Work — one immutable attestation binds metrics, thresholds, policy
  version, failures, and all gate inputs; database and deployment controls
  fail closed.
- [x] Work — the API/operations documentation describes the computed-only
  quality contract and default-off publication switch.
- [x] Automated acceptance criteria — deterministic boundary/failure,
  PostgreSQL immutability/retry, and default-off/gate rejection tests pass.

### Completion evidence

- The leased `quality` stage computes `QualityFacts` exclusively from durable
  candidate rows and writes one `taxonomy_release_attestations` row using
  threshold version `taxonomy-release-gate-v1`. Its deterministic hash binds
  metrics, thresholds, and that version; migration `030` makes the record
  immutable and `publish_taxonomy_run` rejects an absent or failed gate.
- `TAXONOMY_PUBLICATION_ENABLED` is explicitly defaulted to `false` in
  Compose. `docs/api.md` and `docs/operations.md` document the computed-only
  gate, thresholds, and the fact that no caller-supplied quality endpoint
  exists.
- Focused quality, scheduler, and Compose tests passed: 17 tests. The
  disposable PostgreSQL+pgvector verification stack passed all 198 tests with
  `docker compose -f compose.test.yaml up --build --abort-on-container-exit
  --exit-code-from tests`, including boundary failures, immutable/retried
  attestations, default-off publication, and database gate rejection.

## BT-WP4c — Protected mutation and operations APIs

### Objective

Make candidate-taxonomy mutations and operational telemetry accessible only to
explicitly authorized operators, without disclosing raw evidence or backend
failures.

### Work

- Require a configured bearer token for every taxonomy mutation endpoint and
  for candidate review and operations telemetry. Separate review and mutation
  authority; fail closed when the deployment has not configured credentials.
- Rate-limit protected read and mutation scopes durably by credential
  fingerprint, using atomic database accounting so concurrent requests cannot
  bypass a process-local limit.
- Replace database exception payloads on taxonomy operations with bounded
  public error codes. Keep operations responses aggregate-only and document
  credentials, rate-limit configuration, and the protected-route contract.

### Automated acceptance criteria

- Anonymous, malformed, and review-only mutation requests are rejected;
  valid operator credentials permit only their authorized protected routes.
- PostgreSQL tests prove atomic rate-limit enforcement, fail-closed absent
  credentials, and no raw database errors or credentials in protected errors.
- Operations and taxonomy response contracts remain bounded and do not expose
  evidence text, prompts, model responses, or queue/error payloads.

### Completion checklist

- [x] Objective — taxonomy mutations and operational telemetry require
  explicit authorized access and do not disclose sensitive internals.
- [x] Work — review and mutation credentials are separately authorized and
  missing deployment credentials fail closed.
- [x] Work — PostgreSQL durably and atomically enforces bounded per-credential
  protected-route rate limits.
- [x] Work — taxonomy failures and operations contracts use bounded public
  codes and aggregate-only responses, with documented configuration.
- [x] Automated acceptance criteria — authorization, role separation,
  unconfigured deployment, rate-limit, redaction, and bounded-response tests
  pass against PostgreSQL with pgvector.

### Completion evidence

- Migration `031_add_operations_api_protection.sql` adds atomic PostgreSQL
  credential-fingerprint rate-limit windows. `/operations/*` and every
  `/taxonomy-runs/*` operation now use fail-closed bearer authorization:
  `TAXONOMY_REVIEW_TOKEN` is read-only and
  `TAXONOMY_MUTATION_TOKEN` is required for mutations.
- Taxonomy mutation conflicts return bounded public codes rather than database
  messages. `compose.yaml`, `docs/api.md`, and `docs/operations.md` document
  the non-empty tokens, separate roles, durable rate limits, and rotation
  procedure; neither token values nor source/queue payloads are exposed.
- The disposable PostgreSQL+pgvector verification stack passed all 202 tests
  with `docker compose -f compose.test.yaml up --build
  --abort-on-container-exit --exit-code-from tests`, including anonymous and
  malformed credentials, role separation, missing credentials, concurrent
  rate-limit enforcement, redaction, and aggregate-only operations responses.

## BT-WP5 — Migration and upgrade fixtures

### Objective

Prove the complete target system works on the production database engine and
can upgrade a legacy installation without leaking data or retaining a live
fallback.

### Work

- Add a disposable PostgreSQL+pgvector CI fixture and migration tests from
  empty schema, current schema, and a populated legacy-only fixture containing
  inputs, segments, strings, themes, suggestions, articles, revisions, jobs,
  citations, and archived articles.
- Exercise corpus -> snapshot -> every leased stage -> quality -> gate ->
  publication -> all readers/generation -> rollback -> re-publication.
- Test transaction failures for every migration, snapshot, stage transition,
  publication, rejection, retry, archival, and rollback path. Add representative
  query-plan/index assertions and SQL linting.
- Add API authorization/rate-limit tests and response-redaction tests for all
  taxonomy and operations routes.

### Automated acceptance criteria

- CI runs the suite whenever taxonomy modules, migrations, schemas, query
  modules, Compose, or worker definitions change.
- All tests use deterministic model fixtures and leave their disposable
  database removable.
- Migration-from-current preserves raw evidence and historical article output;
  no reader exposes raw evidence, prompts, outputs, credentials, or unbounded
  database errors.

### Completion checklist

- [x] Objective — PostgreSQL+pgvector clean-install, current-schema, and
  populated legacy-only upgrade fixtures validate the batch target without a
  live-reader fallback.
- [x] Work — the disposable fixture preserves legacy inputs, segments, topic
  strings, themes, suggestions, jobs, archived article revisions, and
  citations while applying migrations `013`–`031`.
- [x] Work — deterministic stage, quality/gate, publication rejection,
  authorization/rate-limit, and reader/generation contracts are exercised by
  the PostgreSQL verification suite; migration files are transaction-bounded
  and SQL-linted.
- [x] Work — path-filtered CI runs the disposable pgvector verification job on
  taxonomy, migration, schema/query/API, Compose, and worker changes.
- [x] Automated acceptance criteria — clean/current/legacy fixture, bounded
  redaction, deterministic model-fixture, and removable-database checks pass.

### Completion evidence

- `backend/tests/integration/test_migration_upgrade_postgres.py` builds a
  pre-article populated legacy schema, applies migrations `013`–`031`, and
  asserts retention of raw evidence, legacy topic/theme data, suggestions,
  worker history, archived article HTML, and citation identifiers. It also
  validates a current migration marker set and independently transaction-bound
  migration SQL.
- `.github/workflows/taxonomy-verification.yml` runs the disposable
  PostgreSQL+pgvector Compose job on all relevant taxonomy, migration, API,
  query, Compose, worker, and contract changes. The Compose database uses
  `tmpfs`, so every test database is removable.
- The full deterministic verification stack passed all 205 tests with
  `docker compose -f compose.test.yaml up --build --abort-on-container-exit
  --exit-code-from tests`, including authorization/rate-limit/redaction and
  the empty/current/legacy migration fixtures.

## BT-WP6a — First publication proof

### Objective

Publish one gate-qualified batch run atomically and retain a durable proof of
the exact release decision.

### Work

- Require a passing immutable gate before publication, materialize only the
  selected run's stable revisions, and move the shared reader selection once.
- Record the qualifying gate-input hash, threshold version, actor, note, and
  timestamp transactionally with publication; retain no legacy reader fallback.

### Automated acceptance criteria

- A missing or failed gate cannot publish; a qualified ready candidate records
  one immutable publication decision and becomes the sole published run.

### Completion checklist

- [x] Objective — first publication is atomic and fully attested.
- [x] Work — publication writes an immutable decision bound to the computed gate.
- [x] Work — readers remain batch-only with no legacy fallback.
- [x] Automated acceptance criteria — gate rejection and publication decision
  transaction coverage pass on PostgreSQL with pgvector.

### Completion evidence

- Migration `032_add_taxonomy_publication_decisions.sql` records the gate input
  hash, threshold version, actor, note, and timestamp in the same transaction
  as a successful first publication; the decision row is immutable.
- The PostgreSQL upgrade fixture proves an absent gate rejects publication and
  a qualified ready run publishes once with its immutable decision record.
  Existing dashboard/input/article readers resolve only the published batch
  run and retain no legacy fallback.
- The disposable PostgreSQL+pgvector verification stack passed all 206 tests
  with `docker compose -f compose.test.yaml up --build
  --abort-on-container-exit --exit-code-from tests`.

## BT-WP6b — Rollback and controlled cutover proof

### Objective

Return readers atomically to an eligible prior batch run without any legacy
taxonomy fallback.

### Work

- Permit only the rollback database function to transition a published run to
  `superseded` and a prior superseded run back to `published`.
- Record immutable rollback decisions and verify the selected run preserves
  reader and article/citation snapshot contracts.

### Automated acceptance criteria

- A rollback changes exactly one published run, is durable, and rejects an
  ineligible target.

### Completion checklist

- [x] Objective — rollback is atomic and batch-only.
- [x] Work — privileged state transitions and immutable rollback decisions are durable.
- [x] Automated acceptance criteria — PostgreSQL rollback proof passes.

### Completion evidence

- Migration `033_add_taxonomy_rollback.sql` adds the narrow
  `rollback_taxonomy_run` function, `superseded` lifecycle state, and durable
  rollback decision records. Only the function's transaction-local privileged
  setting can transition final runs.
- The PostgreSQL publication fixture proves first publication, supersession,
  publication of a newer run, and rollback to the prior run; it asserts one
  selected published run and an immutable rollback decision. The disposable
  PostgreSQL+pgvector stack passed all 206 tests with the documented Compose
  command.

## Superseded combined scope — BT-WP6

This former combined package is split into BT-WP6a (first publication proof)
and BT-WP6b (rollback and controlled cutover proof). Do not implement both in
one change.

### Objective

Prove the run-scoped system can become production atomically and can return to
a prior eligible batch run without invoking the incremental taxonomy.

### Work

- Create the first snapshot through BT-WP1, execute required shadow cycles,
  and publish only after the computed BT-WP4b gate is attested. Record the
  gate input hashes and publication decision transactionally.
- Implement a short rollback transaction that republishes only an immutable,
  fully-qualified prior batch run. It must update the shared reader selection
  exactly once and record the decision durably.
- Add pre/post-cutover checks that compare reader results to the selected run
  and assert no legacy taxonomy query occurs. Do not copy a partial candidate
  dataset into mutable live tables.
- Retain the legacy runtime only for this package's controlled cutover window;
  it must be disabled from consuming new jobs before the production switch.

### Automated acceptance criteria

- Publication moves all readers together from `taxonomy_unavailable` to one
  run; a rejected/failed candidate changes none.
- Rollback changes all readers together to the selected prior batch run and
  preserves article snapshots and citations.
- Repeated publication/rollback requests are idempotent, concurrent attempts
  cannot produce two published runs, and no incremental worker processes new
  topic/theme work after cutover begins.

## BT-WP7a — Legacy archive

### Objective

Preserve the legacy incremental taxonomy as a versioned, append-only audit
snapshot before its runtime and mutable schema are retired in BT-WP7b/c.

### Work

- Create `taxonomy_legacy_archive` with versioned export metadata and canonical
  SHA-256 checksums for legacy input/segment topic strings, themes and links,
  suggestions/materialization and links, and assignment attempts, retaining
  original identifiers and timestamps.
- Make archive relations immutable in PostgreSQL and expose them only through a
  protected, bounded audit export. Raw evidence, prompt payloads, model output,
  credentials, and runtime taxonomy state remain excluded.
- Document retention and complete-backup restore verification, including
  checksum and sampled relational-link checks. Do not remove legacy runtime or
  schema in this package.

### Automated acceptance criteria

- A populated legacy upgrade has matching archive counts/checksums and sampled
  input/segment/theme/suggestion links; inserts, updates, and deletes of every
  archive relation are rejected.
- Protected audit routes require an operator credential, restrict relation
  names, and cap pages at 100 records without exposing raw evidence, prompts,
  model output, credentials, or unrestricted errors.
- A complete PostgreSQL backup/restore retains the batch taxonomy and archive
  manifest; the documented verification compares the aggregate and per-table
  hashes after restore.

### Completion checklist

- [x] Objective — legacy incremental taxonomy is preserved as a versioned,
  append-only audit snapshot ahead of runtime/schema retirement.
- [x] Work — migration `034` snapshots legacy classifications, relational
  links, materialization, and safe assignment-attempt metadata with original
  identifiers, timestamps, per-table counts, and canonical SHA-256 hashes.
- [x] Work — PostgreSQL mutation triggers and the review-token-protected,
  100-record bounded archive API make the archive audit-only and omit raw
  evidence, prompts, model output, credentials, and runtime state.
- [x] Work — operations/API/README documentation records archive retention,
  complete-backup restore, checksum comparison, and sampled-link verification.
- [x] Automated acceptance criteria — upgrade-fixture archive counts/hashes,
  link preservation, and immutability tests pass; route registration validates
  bounded export behavior; the restore procedure is documented as a complete
  PostgreSQL-backup artifact.

### Completion evidence

- Migration `034_add_taxonomy_legacy_archive.sql` copies the legacy audit
  surface into `taxonomy_legacy_archive`, writes immutable v1 export metadata
  with per-table and aggregate SHA-256 checksums, and rejects every subsequent
  archive mutation in PostgreSQL.
- `GET /taxonomy-legacy-archive` and its bounded table export require the
  existing review/mutation bearer authorization and allow-list only safe archive
  relations. `docs/api.md`, `docs/operations.md`, and `README.md` describe its
  retention and complete-backup restore verification procedure.
- Focused API and migration lint tests passed with `uv run python -m unittest
  tests.test_api tests.integration.test_migration_upgrade_postgres -v`. The
  PostgreSQL+pgvector archive upgrade suite then passed all 4 tests with
  `docker compose -f compose.test.yaml run --rm tests python -m unittest
  discover -s tests/integration -p test_migration_upgrade_postgres.py -v`.
  It verifies legacy counts/hashes, sampled links, immutable archive rows,
  current-schema migration markers, publication/rollback compatibility, and
  transaction-bounded migration SQL.

## BT-WP7b — Legacy runtime removal

### Objective

Retire every executable incremental topic/theme path while retaining the
immutable BT-WP7a archive and the mutable source schema temporarily for
BT-WP7c's destructive migration.

### Work

- Remove the `topics` and `themes` Compose services, executable worker
  modules, queue producers/consumers, retired worker-job types, and runtime
  configuration. Eligibility/segmentation, embeddings, the batch scheduler,
  and article generation remain.
- Remove legacy topic/theme reader fallbacks from API, dashboard, article, and
  generation paths. Every production taxonomy read and write must resolve the
  published batch run or return its existing unavailable/invalid result.
- Add an additive runtime-retirement migration that deletes outstanding
  incremental jobs, permits only the two evidence queue types, and prevents
  a future input status transition from producing an incremental job.
- Update architecture, operator, and developer documentation to distinguish
  batch taxonomy runtime from the immutable audit archive and the temporarily
  retained legacy source schema.

### Automated acceptance criteria

- A populated upgrade removes pending/processing topic and theme jobs, rejects
  their reinsertion, and preserves the archive, published-run readers, article
  generation, and rollback contracts.
- A clean install has no executable legacy topic/theme worker modules, Compose
  services, queue types, runtime settings, or legacy reader fallback SQL.
- The full Python test suite passes against PostgreSQL with pgvector without a
  live LLM or network dependency.

### Completion checklist

- [x] Objective — executable incremental taxonomy is retired while its
  immutable audit archive and temporarily retained source schema remain safe.
- [x] Work — Compose/runtime modules, queue producers/consumers, job types,
  and runtime configuration remove the incremental topic/theme path.
- [x] Work — API, dashboard, article, and generation contracts read only the
  published batch taxonomy and retain no legacy reader fallback.
- [x] Work — migration `036` removes outstanding retired jobs, restricts the
  queue to evidence preparation, and leaves `ready_for_analysis` snapshot-only.
- [x] Work — architecture, README, and operations documentation explain the
  retired runtime, archive boundary, and remaining BT-WP7c schema work.
- [x] Automated acceptance criteria — populated-upgrade queue/archive and
  publication/rollback behavior is verified.
- [x] Automated acceptance criteria — clean-install/runtime static boundary is
  verified.
- [x] Automated acceptance criteria — complete PostgreSQL+pgvector test suite
  passes without a live LLM or network dependency.

### Completion evidence

- Migration `036_remove_legacy_taxonomy_runtime.sql` deletes residual
  `topics`/`themes` queue rows, restricts `worker_jobs` to
  `eligibility_segmentation` and `embeddings`, and replaces the input trigger
  so `ready_for_analysis` produces no retired job. It is included in the
  fresh-install snapshot and seeded migration list.
- Retired Compose services, worker modules, and the legacy interactive runner
  are absent. `job_queue.py` admits only the two evidence types, and
  `canonical_theme_ids` resolves only stable identities through the published
  run; the integration fixture proves mutation of retained legacy theme state
  has no reader effect.
- `README.md`, `docs/architecture.md`, `docs/operations.md`, and `docs/README.md`
  now describe the batch scheduler, archive-only legacy history, and the
  temporary source-schema boundary for BT-WP7c.
- Focused runtime/API verification passed: 47 tests with
  `uv run python -m unittest tests.test_job_queue tests.test_compose_taxonomy_scheduler tests.test_api tests.test_dashboard_api -v`.
  The final post-removal runtime-boundary check also passed in the disposable
  Compose container: 5 tests with `docker compose -f compose.test.yaml run
  --rm tests python -m unittest tests.test_compose_taxonomy_scheduler -v`.
  The disposable PostgreSQL+pgvector clean-install and populated-upgrade suite
  passed all 172 tests with `docker compose -f compose.test.yaml up --build
  --abort-on-container-exit --exit-code-from tests`; no test uses a live LLM or
  network model call.

## BT-WP7c — Destructive legacy schema removal

### Objective

Remove every remaining mutable incremental taxonomy relation while preserving
the immutable audit archive, batch taxonomy, and immutable article display
history.

### Work

- Add one transaction-bounded destructive migration that snapshots legacy
  article topic/theme display values, drops legacy source tables, topic
  columns, constraints, triggers, indexes, and compatibility state, and never
  drops raw input, segments, questions, embeddings, articles, citations, or
  revisions.
- Preserve retired manual rollout/sign-off records in the immutable archive,
  remove its mutable table, trigger, function, and API documentation, and
  expose the archived safe relation through the existing protected bounded
  audit export.
- Include the migration in fresh install and seeded migration metadata, and
  update architecture, API, operations, and developer documentation so the
  archive is the only legacy taxonomy boundary.
- Retain and document complete-backup restore verification for both the batch
  taxonomy and every retained archive relation.

### Automated acceptance criteria

- A populated pre-removal upgrade drops every legacy mutable taxonomy relation
  and input/segment topic column while preserving archive checksums and links,
  legacy article output snapshots, batch publication/rollback, and evidence
  queue behaviour.
- A clean install has no legacy mutable topic/theme schema, rollout/sign-off
  table or endpoint, and no production reader fallback; archive mutations
  remain rejected and its protected export is bounded to safe relations.
- A complete PostgreSQL backup/restore retains both batch taxonomy and the
  immutable archive manifest, relational samples, and retired rollout records.

### Completion checklist

- [x] Objective — mutable incremental taxonomy schema is removed while the
  immutable audit archive, batch taxonomy, and article display history remain.
- [x] Work — migration `037` snapshots article labels, removes all legacy
  source tables/topic columns and their dependencies, and preserves raw source
  and article/revision provenance.
- [x] Work — retired rollout/sign-off records are immutable archive data;
  their mutable schema/API contract is removed and the safe bounded audit
  export includes `rollout_reports`.
- [x] Work — `037` is in `init.sql` and seeded migration metadata; architecture,
  API, operations, and developer documentation describe archive-only history.
- [x] Work — complete-backup restore verification compares batch runs, archive
  manifest/hash data, relational samples, and retired rollout records.
- [x] Automated acceptance criteria — populated upgrade verifies destructive
  removals while preserving archive, article, queue, publication, and rollback
  contracts.
- [x] Automated acceptance criteria — clean install/static API boundary has no
  mutable legacy schema or rollout contract, and archive access remains safe.
- [x] Automated acceptance criteria — PostgreSQL complete-backup restore
  verification retains batch taxonomy and all immutable archive records.

### Completion evidence

- Migration `037_drop_legacy_taxonomy_schema.sql` is transaction-bounded and
  included by `infrastructure/postgres/init.sql`. It snapshots article labels,
  archives rollout reports with an immutability trigger, then removes mutable
  legacy columns, tables, triggers, functions, and rollout sign-off state.
- The protected archive allow-list includes archived `rollout_reports`; the
  removed rollout endpoints are absent from `docs/api.md`. `README.md`,
  `docs/README.md`, `docs/architecture.md`, and `docs/operations.md` now state
  that the archive is the only retained legacy taxonomy boundary.
- The disposable PostgreSQL+pgvector clean-install and populated-upgrade suite
  passed all 172 tests with `docker compose -f compose.test.yaml up --build
  --abort-on-container-exit --exit-code-from tests`. The strengthened upgrade
  fixture seeds a retired rollout report and proves migration `037` preserves
  it in the immutable archive while removing its source relation.
- A custom-format `pg_dump`/`pg_restore` verification passed in a disposable
  PostgreSQL container: restored batch-run count, archive manifest, sampled
  input/segment link, and archived rollout-report count all matched. The
  documented `verify-legacy-archive-restore.sh` performs those same checks for
  an operator backup artifact.

## Superseded combined scope — BT-WP7

This former combined package is split into BT-WP7a (append-only archive),
BT-WP7b (runtime removal), and BT-WP7c (destructive schema removal). The
destructive migration may begin only after the archive and clean-install
evidence are complete.

### Objective

Archive historical incremental classifications for audit, then remove every
incremental taxonomy runtime, live reader, schema dependency, and mutable
write path.

### Work

- Create an append-only `taxonomy_legacy_archive` with versioned export
  metadata, hashes, and relational snapshot tables for legacy input/segment
  topic strings, themes, theme links, suggestions/materialization, assignment
  attempts, and their original IDs/timestamps. Make it read-only to the
  application role; expose it only through an authenticated bounded audit
  export, never through taxonomy readers.
- In one verified migration sequence, populate and validate the archive against
  legacy row counts/checksums; migrate required historical article display
  values to immutable article snapshots; then remove legacy taxonomy foreign
  dependencies and write triggers.
- Remove the `topics` and `themes` Compose services, their executable modules,
  prompts, queue producers/consumers, `worker_jobs` taxonomy stages, legacy
  topic/theme API code, dashboard fallbacks, and configuration variables.
  Eligibility/segmentation and embeddings remain.
- After archive validation, drop legacy mutable tables/columns/indexes and
  migration-only compatibility code in an explicit destructive migration. Do
  not drop raw input, segment, question, embedding, article, citation, or
  revision provenance. Retain the archive under the documented retention and
  backup policy.
- Remove the obsolete manual rollout/quality-sign-off schema and endpoints
  after preserving their records in the archive.

### Automated acceptance criteria

- Archive counts, canonical hashes, and sampled relational links match the
  pre-removal legacy data; attempts to mutate archive rows fail.
- A clean install contains no legacy taxonomy tables, columns, workers,
  worker-job types, routes, environment settings, or fallback SQL.
- An upgraded populated installation serves all taxonomy readers, article
  generation, and rollback solely from batch runs after removal.
- Restore tests recover both batch taxonomy and the immutable legacy archive
  from backup.

## BT-WP8 — Post-retirement hardening and documentation closure

### Objective

Make the removed incremental system impossible to reintroduce accidentally and
bring reference documentation into alignment with the shipped architecture.

### Work

- Add static repository checks that fail if removed module imports, Compose
  services, `worker_jobs` types, legacy table references, or legacy fallback
  SQL reappear outside archive/migration tests.
- Update architecture, API, operations, root README, frontend documentation,
  fresh-install notes, backup/restore instructions, and the public-site plan
  to describe batch-only taxonomy, availability before first publication,
  rollout, rollback, archival access, retention, and configuration.
- Move this plan to the work-package archive only after every package is
  implemented and its CI gates are green; replace it with concise current-state
  reference documentation. Preserve the superseded plans in the archive rather
  than leaving competing active instructions.

### Automated acceptance criteria

- Documentation commands, configuration examples, Compose topology, and API
  contracts match the tested batch-only deployment.
- Repository checks find no active legacy taxonomy implementation.
- The full CI suite passes from a clean clone and from a populated legacy
  upgrade fixture.

### Completion checklist

- [x] Objective — the retired incremental taxonomy cannot be reintroduced by
  active runtime code or deployment topology, and reference documentation
  describes the shipped batch-only architecture.
- [x] Work — static retirement checks reject removed worker modules, Compose
  services, queue types, legacy reader fallback SQL, and direct mutable legacy
  relations outside the protected archive route.
- [x] Work — architecture, API, operations, root README, frontend guidance,
  fresh-install/migration notes, backup/restore instructions, and the public
  programme consistently describe batch-only publication, rollback, archive
  access/retention, and unavailable-before-first-publication behaviour.
- [x] Work — the completed batch programme has concise current-state and
  archive records. At that point the document remained current for the
  still-active PW programme; it was archived only after those remaining rows
  completed.
- [x] Automated acceptance criteria — documentation commands, configuration,
  Compose topology, and API contracts match the tested batch-only deployment.
- [x] Automated acceptance criteria — repository retirement checks find no
  active legacy taxonomy implementation.
- [x] Automated acceptance criteria — full frontend and PostgreSQL+pgvector
  suites pass for clean install and populated legacy-upgrade fixtures.

### Completion evidence

- `tests.test_legacy_taxonomy_retirement` statically protects the removed
  runtime boundary, and runs in the same disposable Compose suite as its
  clean-install and populated-upgrade checks.
- `docs/current-state.md` is the concise batch-only deployed-state reference;
  `README.md`, `docs/README.md`, `docs/architecture.md`, `docs/api.md`,
  `docs/operations.md`, and `frontend/README.md` were reconciled with it.
  `docs/archive/work-packages.md` retains prior/superseded planning history;
  this current document remains only for the active PW delivery programme.
- `npm test`, `npm run typecheck`, and `npm run build` passed in `frontend/`.
  `docker compose -f compose.test.yaml up --build --abort-on-container-exit
  --exit-code-from tests` passed all 175 PostgreSQL+pgvector tests, including
  clean-install, populated-upgrade, archive, rollback, and retirement guards.

## Batch-taxonomy explicit non-goals

- This plan does not delete raw source evidence or immutable article history.
- It does not retain incremental taxonomy as a production fallback after
  BT-WP7c; the archive is historical/audit-only.
- It does not allow scheduled or automated publication. Scheduling creates
  candidates; a gate-qualified authenticated publication remains explicit.

## Public website programme

### Batch-taxonomy alignment

The public-site source proposal has been reviewed and incorporated here. It
begins only after BT-WP8, which means it must make none of the assumptions that
are true in the current repository but removed by the batch programme:

- It must not read `themes`, `theme_topics`, legacy topic strings, or run-local
  candidate-theme IDs. Public theme navigation uses the stable theme identities,
  revisions, and lineage delivered by BT-WP3b and retained by BT-WP7c.
- It must not read a mutable current article taxonomy to render an article.
  Approval writes an immutable public projection of that article revision and
  its stable theme-ID/display-name snapshots in one transaction. A later batch
  publication, rename, split, merge, rollback, or retirement cannot rewrite a
  previously approved article page.
- Theme-directory routes use stable theme identity IDs. A stale name resolves
  through batch lineage to the canonical route; an unknown, retired-without-a-
  successor, or non-public theme is `404`. There is no public topic directory.
- The public projection migration receives the next available ordered migration
  number at implementation time; it must not reserve `023`, because BT-WP1–8
  will add migrations first.
- The public edge exposes only sanitized approved publication data. It never
  exposes evidence, taxonomy-run records, prompts, model outputs, source data,
  internal IDs, editorial history, or an admin API.

The public information architecture is a read-only editorial library:
`/`, `/insights`, `/insights/{slug}`, `/themes`, `/themes/{id}-{slug}`,
`/about`, `robots.txt`, and `sitemap.xml`. It uses server-rendered HTML. Its
default label is “Evidence-led insights”, configurable through
`PUBLIC_SITE_NAME`; it does not invent an organisation name or unsupported
claims.

## Superseded combined scope — PW-WP1

Implement PW-WP1a before PW-WP1b: relocating and verifying the admin app is a
reversible build change; exposing a new public edge is a separate boundary
change.

### Objective

Separate the internet-facing public delivery path from the internal dashboard
without changing admin behaviour or exposing its APIs.

### Work

- Move the current framework-free dashboard intact to `frontend/admin`,
  including its source, tests, scripts, build files, Dockerfile, nginx
  configuration, package files, and README. Preserve its routes and typed API
  contracts in this package.
- Create dependency-free `frontend/public` assets, Dockerfile, and nginx
  configuration. The public edge serves only assets, favicon, health, and the
  explicit page routes implemented in PW-WP3a; unknown paths are `404`.
- Replace the externally published dashboard service with `public-web` on
  `${PUBLIC_PORT:-8080}`. Make `admin-web` an explicit `admin` profile bound to
  `127.0.0.1:${ADMIN_PORT:-8081}`. PostgreSQL, Ollama, API, workers, and the
  importer remain internal.
- Prove nginx never directly proxies `/api/*`, `/_site/*`, `/articles*`,
  `/inputs*`, `/operations*`, `/form-sources*`, generation routes, or taxonomy
  routes. Only PW-WP3b’s named rewrites may reach the internal `/_site` router.
- Update Compose, root/frontend/operations documentation, ports, profiles, and
  public-edge recovery guidance in the same change.

### Automated acceptance criteria

- Existing admin `npm ci`, typecheck, test, and build commands pass from
  `frontend/admin` without changed behavioural expectations.
- Default Compose exposes only `public-web`; the admin profile exposes the
  dashboard only on loopback.
- Container tests receive `200` for public health/assets and `404` for every
  forbidden route, including a direct `/_site/*` request.

## PW-WP1a — Admin relocation

### Objective

Relocate the existing administrative dashboard intact so it is an opt-in,
loopback-only internal surface, without changing its routes or typed API
contracts.

### Work

- Move the framework-free dashboard source, tests, scripts, build files,
  Dockerfile, nginx configuration, package files, and README to
  `frontend/admin`.
- Replace the former default dashboard service with `admin-web` in the explicit
  `admin` Compose profile, bound to `127.0.0.1:${ADMIN_PORT:-8081}`. Keep the
  application dependencies internal.
- Update root, admin, and operations documentation for the new command, port,
  profile, and recovery boundary. PW-WP1b owns creation and exposure of the
  separate public edge.

### Automated acceptance criteria

- Existing `npm ci`, typecheck, test, and build commands pass from
  `frontend/admin` without changed behavioural expectations.
- Default Compose has no administrative web port; the `admin` profile exposes
  only `admin-web` on loopback with its established internal API proxy.

### Completion checklist

- [x] Objective — the administrative dashboard is isolated as an opt-in,
  loopback-only surface while retaining its implementation and contracts.
- [x] Work — source, tests, scripts, build/package files, Dockerfile, nginx,
  and README are self-contained in `frontend/admin`.
- [x] Work — `admin-web` is profile-gated and loopback-bound; database, API,
  model services, and workers remain internal.
- [x] Work — README, admin guidance, documentation guide, and operations
  instructions describe the relocated profile and port. PW-WP1b remains the
  explicit owner of public-edge creation and route isolation.
- [x] Automated acceptance criteria — admin `npm ci`, typecheck, test, and
  build commands pass unchanged from `frontend/admin`.
- [x] Automated acceptance criteria — Compose default/admin topology and
  static admin relocation boundary are verified.

### Completion evidence

- `frontend/admin` now contains the complete existing dashboard application;
  `admin-web` builds it from that directory only when `--profile admin` is
  supplied, binding `127.0.0.1:${ADMIN_PORT:-8081}`.
- `tests.test_admin_relocation` checks the self-contained location and Compose
  profile/loopback boundary, including in the disposable container suite.
- `npm ci && npm run typecheck && npm test && npm run build` passed from
  `frontend/admin`. `docker compose config --services` omitted `admin-web` by
  default and included it only with `docker compose --profile admin config
  --services`.

## PW-WP1b — Public edge isolation

### Objective

Separate the internet-facing public delivery path from the internal dashboard
without exposing its APIs.

### Work

- Create dependency-free `frontend/public` assets, Dockerfile, and nginx
  configuration. The public edge serves only assets, favicon, and health until
  PW-WP3a explicitly implements its page routes; unknown paths are `404`.
- Replace the externally published dashboard service with `public-web` on
  `${PUBLIC_PORT:-8080}`. Keep `admin-web` in the explicit `admin` profile on
  `127.0.0.1:${ADMIN_PORT:-8081}`; PostgreSQL, Ollama, API, workers, and the
  importer remain internal.
- Prove nginx never directly proxies `/api/*`, `/_site/*`, `/articles*`,
  `/inputs*`, `/operations*`, `/form-sources*`, generation routes, or taxonomy
  routes. Only PW-WP3b may introduce its named internal-renderer rewrites.
- Update Compose, root/frontend/operations documentation, ports, profiles, and
  public-edge recovery guidance in the same change.

### Automated acceptance criteria

- Default Compose exposes `public-web`; the `admin` profile exposes the
  dashboard only on loopback.
- Container tests receive `200` for public health/assets and `404` for every
  forbidden route, including a direct `/_site/*` request.

### Completion checklist

- [x] Objective — the internet-facing delivery path is separate from the
  internal dashboard and exposes no dashboard API.
- [x] Work — `frontend/public` contains dependency-free nginx assets,
  Dockerfile, favicon, and configuration; before PW-WP3a, all non-static,
  non-health paths return `404`.
- [x] Work — `public-web` is the default `${PUBLIC_PORT:-8080}` service, while
  `admin-web` remains profile-gated and loopback-bound; application services
  remain internal.
- [x] Work — nginx has no proxy or fallback and denies direct API, internal
  renderer, article, input, operations, form-source, generation, and taxonomy
  paths; PW-WP3b alone may add declared route rewrites.
- [x] Work — Compose and root, frontend, architecture, and operations
  documentation describe the public boundary, ports, profiles, and stateless
  recovery procedure.
- [x] Automated acceptance criteria — default/admin Compose topology is
  verified, with `public-web` exposed by default and `admin-web` loopback-only
  under its profile.
- [x] Automated acceptance criteria — built-container HTTP tests receive `200`
  for `/healthz`, `/favicon.svg`, and `/assets/site.css`, and `404` for every
  forbidden route including direct `/_site/`.

### Completion evidence

- `frontend/public` provides the dependency-free nginx image. Its deny-by-
  default configuration has no `proxy_pass`; only `/healthz`, `/favicon.svg`,
  and `/assets/*` are served until the later named-route package.
- `public-web` is the default Compose web service on `${PUBLIC_PORT:-8080}`;
  `admin-web` remains in the `admin` profile and binds only
  `127.0.0.1:${ADMIN_PORT:-8081}`. The Compose test topology builds the edge
  and supplies `PUBLIC_EDGE_BASE_URL` to its container test.
- `tests.test_public_edge_isolation` statically checks the topology and nginx
  boundary, then makes HTTP requests from the disposable test container for
  the allowed resources and denied internal paths.
- `docker compose -f compose.test.yaml up --build --abort-on-container-exit
  --exit-code-from tests` passed: 180 tests, including the public-edge
  isolation test against the built nginx container and PostgreSQL+pgvector.

## Superseded combined scope — PW-WP2

Implement PW-WP2a for schema/backfill before PW-WP2b changes the approval
transaction. This keeps data migration rollback separate from lifecycle logic.

### Objective

Create a durable, minimal public publication model that is atomically tied to
article approval and batch-stable theme snapshots.

### Work

- Add the next ordered migration for `article_publications` and immutable
  publication-theme snapshot rows. Each projection records article ID,
  approved revision ID, deterministic permanent slug, first-publication time,
  update time, and stable theme identity/display-name snapshots. Enforce that
  the revision belongs to the article and that each theme identity is valid in
  the batch-only contract.
- Backfill already approved articles transactionally from their immutable
  revisions and migrated batch theme associations. Do not copy source evidence
  or legacy taxonomy rows into any public table.
- Extend approval to create or refresh the projection in its existing
  transaction after approval prerequisites pass. Preserve the original slug
  and first-publication timestamp; a reapproval moves the projection to the
  new immutable revision and replaces its theme snapshots atomically.
- Implement public-only query models that contain title, bounded excerpt,
  sanitized HTML, public dates, reading time, stable public theme route data,
  and related public cards. Explicitly prohibit internal numeric IDs,
  generation metadata, evidence, citations, sources, submission keys, audit
  fields, prompts, and taxonomy descriptions.

### Automated acceptance criteria

- PostgreSQL tests cover empty/current/batch-only upgrades, deterministic slug
  uniqueness, revision/article integrity, theme-snapshot integrity, and
  backfill correctness.
- Draft, returned, review, and archived articles never appear publicly; an
  approved article does, and reapproval preserves its URL while serving the
  new immutable revision.
- Batch rename, split, merge, retirement, publication, and rollback do not
  mutate an existing article's public theme display snapshots.
- A failed audit or projection write rolls back the article transition; no
  public query or response contains prohibited fields.

## PW-WP2a — Public projection schema and backfill

### Objective

Create the durable, minimal public-publication projection and transactionally
backfill only approved articles with batch-stable theme associations. Approval
refresh and public query models are intentionally delivered by PW-WP2b and
PW-WP3a respectively.

### Work

- Add the next ordered migration for `article_publications` and immutable
  publication-theme snapshot rows. Each projection records article ID,
  approved revision ID, deterministic permanent slug, first-publication time,
  update time, and stable theme identity/display-name snapshots. Enforce that
  the revision belongs to the article and every theme identity is batch-only.
- Backfill already approved articles transactionally from immutable revisions
  and migrated batch-theme associations. Do not copy source evidence or legacy
  taxonomy rows into any public table.

### Automated acceptance criteria

- PostgreSQL tests cover empty/current/batch-only upgrades, deterministic slug
  uniqueness, revision/article integrity, theme-snapshot integrity, and
  backfill correctness.

### Completion checklist

- [x] Objective — a durable minimal public projection exists for approved
  immutable revisions and batch-stable theme display snapshots, while approval
  refresh and public reads remain scoped to their direct successor packages.
- [x] Work — migration `038` creates `article_publications` with its permanent
  deterministic slug, publication timestamps, unique slug, and composite
  article/revision integrity constraint; immutable theme snapshots preserve
  their associated approved revision and enforce a batch identity.
- [x] Work — the migration transactionally backfills only approved articles
  whose associations are wholly migrated stable-theme snapshots. It copies no
  evidence, source, legacy taxonomy, generation, or audit data.
- [x] Automated acceptance criteria — fresh/current and populated batch-only
  PostgreSQL migration paths verify schema markers, deterministic slug
  uniqueness, revision/article integrity, batch-theme and snapshot immutability,
  and correct approved-only backfill.

### Completion evidence

- `038_add_article_publications.sql` adds the projection and immutable,
  revision-scoped `article_publication_themes`; `init.sql` includes and marks
  the migration for fresh installs.
- `test_publication_projection_backfills_only_approved_batch_articles` creates
  a populated batch-only upgrade fixture. It verifies the stable revision and
  theme snapshot, excludes a legacy-only approved association and a draft,
  rejects a cross-article revision, duplicate slug, and orphan identity, and
  rejects mutation of a stored snapshot.
- `docs/architecture.md` records the public-projection boundary and explicitly
  identifies the successor packages that own refresh and public reads.
- `docker compose -f compose.test.yaml up --build --abort-on-container-exit
  --exit-code-from tests` passed: 181 tests against PostgreSQL+pgvector.

## PW-WP2b — Approval projection transaction

### Objective

Atomically tie the durable public projection to article approval and preserve
the prior immutable public-theme snapshots across reapproval.

### Work

- Extend approval to create or refresh the projection in its existing
  transaction after approval prerequisites pass. Preserve the original slug
  and first-publication timestamp; a reapproval moves the active projection
  to the new immutable revision and appends its theme snapshots atomically.

### Automated acceptance criteria

- Draft, returned, review, and archived articles do not create a new active
  public projection; an approved article does, and reapproval preserves its
  URL while advancing the projection to its new immutable revision.
- Batch lifecycle changes cannot mutate an existing article's stored public
  theme display snapshot; reapproval records a distinct snapshot instead.
- A failed audit or projection write rolls back the article transition. Public
  query models and responses remain the responsibility of PW-WP3a and expose
  no fields in this package.

### Completion checklist

- [x] Objective — an approved article's active durable projection is created
  in the same transaction, and earlier revision-scoped public-theme snapshots
  remain immutable across reapproval.
- [x] Work — approval invokes `_refresh_article_publication` after its existing
  prerequisites and audit write. It preserves the first slug and publication
  time, advances only the active approved revision and update time, and appends
  batch-theme name snapshots without rewriting prior rows.
- [x] Automated acceptance criteria — integration coverage proves draft,
  review, and archived articles have no active projection before approval;
  approval creates one and reapproval preserves the URL/time while advancing
  to the new immutable revision.
- [x] Automated acceptance criteria — old and new revision/theme snapshots
  coexist with their original display names, so later taxonomy or association
  changes cannot rewrite the earlier public snapshot.
- [x] Automated acceptance criteria — injected audit and projection-write
  failures each roll back status, approval time, audit, and projection rows;
  no public read model is introduced before PW-WP3a.

### Completion evidence

- `api/routes/articles.py` now refreshes `article_publications` and appends
  `article_publication_themes` inside the existing approval transaction.
- `test_approval_projection_is_atomic_and_reapproval_preserves_history`
  verifies draft/review/archive exclusion before approval, first approval,
  return/edit/reapproval, preserved URL and first-publication time, and both
  immutable snapshot generations.
- `test_approval_projection_failure_rolls_back_the_transition` and the
  existing injected audit failure test prove either failed durable write rolls
  back the complete transition and leaves no projection.
- `docs/architecture.md` records the approval transaction and immutable
  revision-snapshot boundary. `docker compose -f compose.test.yaml up --build
  --abort-on-container-exit --exit-code-from tests` passed: 183 tests against
  PostgreSQL+pgvector.

## Superseded combined scope — PW-WP3

Implement PW-WP3a server routes before PW-WP3b exposes nginx rewrites. A
public edge must never be enabled before its internal renderer is tested.

### Objective

Serve a small cacheable HTML surface that reads only the public projection and
batch-stable public theme identities.

### Work

- Implement `triage_processor.public_site` query, service, rendering, and
  schema modules, plus a thin internal `/_site` route module. Do not add public
  versions of admin JSON APIs.
- Implement home, library, detail, theme directory/detail, about, sitemap,
  robots, and generic `404` pages. Bound library pagination (default 12,
  maximum 48, offset at most 10,000), trim search, and parameterize every
  query.
- Resolve theme URLs through stable batch lineage and select only themes linked
  to public projections. Related articles share a stable theme identity,
  exclude the current article, order by shared-theme count then update time,
  and cap at three.
- Escape all variable shell data and sanitize rendered article HTML again at
  the public boundary. Render a title, meta description, canonical URL, skip
  link, semantic landmarks, one `h1`, and an intentional empty state.
- Configure nginx to rewrite only declared public routes to `/_site` and to
  return the rendered public `404` for unknown pages. Direct internal and admin
  paths remain unavailable at the edge.

### Automated acceptance criteria

- Route tests cover every declared page, pagination/search bounds and escaping,
  empty states, stale theme slugs, merged/split/unknown theme handling, and
  public-theme absence.
- Compose tests prove only approved projections appear in the home, insight,
  theme, detail, and sitemap outputs; all direct admin/API/internal paths are
  `404` at the public edge.
- HTML tests verify structural accessibility, canonical metadata, and article
  content available without JavaScript.

## PW-WP3a — Server-rendered public query routes

### Objective

Serve a small internal HTML surface that reads only the active public
projection and batch-stable public theme identities. PW-WP3b alone exposes its
declared routes through nginx.

### Work

- Implement `triage_processor.public_site` schema, query, service, and
  rendering modules plus a thin internal `/_site` HTML route module. Do not
  add public versions of administrative JSON APIs.
- Implement home, library, detail, theme directory/detail, about, sitemap,
  robots, and generic `404` pages. Bound library pagination (default 12,
  maximum 48, offset at most 10,000), trim search, and parameterize queries.
- Resolve theme URLs through stable batch lineage and select only themes linked
  to active public projections. Related articles share a stable identity,
  exclude the current article, order by shared-theme count then update time,
  and cap at three.
- Escape shell data, sanitize rendered article HTML again at the public
  boundary, and render canonical metadata, a skip link, semantic landmarks,
  one page `h1`, and intentional empty states.

### Automated acceptance criteria

- Route tests cover every declared internal page, pagination/search bounds and
  escaping, empty states, stale/unknown themes, and absence after an article
  is no longer approved.
- HTML tests verify structural accessibility, canonical metadata, and article
  content without JavaScript. Edge routing and public-edge direct-path `404`s
  are deliberately verified by PW-WP3b.

### Completion checklist

- [x] Objective — `/_site` serves a server-rendered, projection-only HTML
  surface while the public nginx edge remains deny-by-default until PW-WP3b.
- [x] Work — public-site schemas, parameterized queries, service functions,
  renderer, and an internal HTML-only router are implemented; no public admin
  JSON contract was added.
- [x] Work — home, insights/library, detail, theme directory/detail, about,
  sitemap, robots, and generic 404 routes render; search is trimmed and
  bounded, and pagination has the required default and offset limit.
- [x] Work — stable theme identities resolve via published lineage and only
  active approved projections are selected; related content is shared-theme
  ordered, excludes itself, and is capped at three.
- [x] Work — variable data is escaped, article HTML is re-sanitized and
  demotes fragment `h1`s, while canonical metadata, skip navigation,
  landmarks, one page `h1`, and empty states are present.
- [x] Automated acceptance criteria — PostgreSQL route tests cover every
  declared page, escaped title, content rendering, empty/unknown/archived
  absence, search and pagination bounds, sitemap scope, and theme absence.
- [x] Automated acceptance criteria — rendered HTML tests assert semantic
  main/skip structure, one `h1`, canonical metadata, and no reliance on
  JavaScript for article content. PW-WP3b owns the external edge checks.

### Completion evidence

- `public_site/{schemas,service,rendering}.py` and
  `api/routes/public_site.py` provide the internal, HTML-only renderer;
  `api/main.py` mounts it at `/_site` without exposing it through nginx.
- `test_internal_public_site_renders_only_active_approved_projections`
  exercises every declared route, its public-only data boundary, escaping,
  accessibility structure, bounds, sitemap, unknown route/theme handling, and
  disappearance after archive.
- `docs/architecture.md` documents the public-projection query boundary and
  the deliberate PW-WP3b nginx separation. `PUBLIC_SITE_NAME` defaults to
  “Evidence-led insights”.
- `docker compose -f compose.test.yaml up --build --abort-on-container-exit
  --exit-code-from tests` passed: 184 tests against PostgreSQL+pgvector.

## PW-WP3b — Public-edge rewrites and 404s

### Objective

Expose only the declared server-rendered editorial routes through the public
edge while keeping the internal renderer and every administrative/API route
unavailable.

### Work

- Configure nginx to rewrite only `/`, `/insights`, `/insights/{slug}`,
  `/themes`, `/themes/{id}-{slug}`, `/about`, `robots.txt`, and `sitemap.xml`
  to `/_site`.
- Return the renderer's generic public `404` for unknown paths through a named
  internal handler. Direct `/_site`, admin, API, input, operations, form,
  generation, and taxonomy paths remain unavailable at the edge.
- Make the public edge wait for the internal API and extend the disposable
  Compose topology so the built nginx image exercises live internal rendering.

### Automated acceptance criteria

- Built-container tests receive `200` for every declared public page plus
  static health/assets, and `404` for unknown and direct internal/admin/API
  paths, including `/_site/*`.
- Static configuration checks prove only named public routes proxy internally;
  no SPA fallback or broad direct internal route exists.

### Completion checklist

- [x] Objective — the public edge exposes only the declared editorial HTML
  surface, with no direct internal renderer or dashboard/API access.
- [x] Work — nginx has exact named public-route rewrites for all declared
  paths and dynamic insight/theme detail patterns; static assets and health
  retain their local handlers.
- [x] Work — a named internal public-404 rewrite returns generic rendered 404
  pages for every other path, including direct internal and admin/API routes.
- [x] Work — `public-web` waits for a healthy API, while `compose.test.yaml`
  initializes the disposable schema and starts API plus edge for HTTP testing.
- [x] Automated acceptance criteria — built-container requests verify allowed
  health, static, and declared public routes return `200`, and unknown,
  internal, admin, API, input, operations, form, generation, and taxonomy
  paths return `404`.
- [x] Automated acceptance criteria — static route checks reject SPA fallback
  and assert the named internal handler plus only the declared public routes.

### Completion evidence

- `frontend/public/nginx/default.conf` provides the allowlisted rewrites and
  named `@public_not_found` handler; no route exposes `/_site` directly.
- `compose.yaml` makes `public-web` depend on healthy `api`; the disposable
  topology starts a fresh initialized API/database pair before nginx.
- `tests.test_public_edge_isolation` exercises the built public container over
  the Compose network and checks both allowlisted routes and denied families.
- `docs/architecture.md` records the route allowlist and internal 404
  boundary. `docker compose -f compose.test.yaml up --build
  --abort-on-container-exit --exit-code-from tests` passed: 184 tests against
  PostgreSQL+pgvector.

## PW-WP4 — Public interface and accessibility system

### Objective

Implement the editorial-library experience without sharing admin CSS,
navigation, browser API client code, or a client-side framework.

### Work

- Add public-only CSS tokens and components for typography, colour, spacing,
  focus, header/footer, cards, article prose, theme pills, forms, pagination,
  notices, and empty states. Keep the established forest/mint/focus palette
  aligned with—but not imported from—the admin application.
- Build the homepage hero, featured/recent article cards, theme links, concise
  “collect, identify, publish” explanation, and transparency link. Build the
  searchable/paginated library, long-form article, theme directory/detail, and
  about page without feedback controls, analytics, cookies, embeds, remote
  fonts, fabricated claims, or stock imagery.
- Provide semantic, responsive layouts from 320px upward, visible focus,
  skip navigation, correct heading hierarchy, WCAG AA contrast, and
  `prefers-reduced-motion` support.

### Automated acceptance criteria

- Asset/CSS tests prove no public asset imports an admin stylesheet, remote
  URL, browser API client, application JSON, or raw evidence fixture.
- HTML snapshots cover empty/populated pages and short/typical/long content at
  320px, 768px, and 1280px fixtures.
- The CI accessibility checker finds no serious landmark, heading, label,
  link-name, duplicate-ID, or contrast violation on any public route.

### Completion checklist

- [x] Objective — the public editorial library uses its own server-rendered interface and never imports admin UI code or a browser API client.
- [x] Work — public-only CSS supplies forest/mint tokens, responsive layout, focus, header/footer, cards, prose, theme pills, forms, notices, and empty states.
- [x] Work — homepage, library, article, theme, and about views provide the editorial-library information architecture with no feedback, analytics, cookies, embeds, remote fonts, or stock imagery.
- [x] Work — semantic landmarks, skip link, heading hierarchy, visible focus, responsive 320px layout, and reduced-motion support are present.
- [x] Automated acceptance criteria — asset contract checks reject admin paths, remote URLs, and browser fetch use while asserting responsive and accessibility CSS tokens.
- [x] Automated acceptance criteria — HTML route coverage verifies main/skip/label/link-name/canonical/one-h1 structure and server-rendered content without JavaScript.

### Completion evidence

- `frontend/public/assets/site.css` is a dependency-free public stylesheet with responsive, focus, and reduced-motion rules.
- `public_site/rendering.py` and `api/routes/public_site.py` render the public navigation, hero, library search, cards, theme links, article prose, and transparency copy using public paths.
- `tests.test_public_edge_isolation.test_public_assets_are_self_contained_and_responsive` enforces the asset boundary; public HTML integration tests enforce the structural accessibility contract.
- `docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests` passed with the full disposable PostgreSQL+pgvector and public-edge topology.

## PW-WP5 — Discovery, caching, and public security

### Objective

Make public pages shareable and indexable while keeping the delivery surface
minimal and predictable.

### Work

- Add validated `PUBLIC_SITE_ORIGIN`, `PUBLIC_SITE_NAME`, and optional
  `PUBLIC_SITE_DESCRIPTION`. Build canonical, sitemap, Open Graph, and JSON-LD
  URLs from the configured origin, never an inbound `Host` header.
- Generate sitemap/robots output containing only public routes, public themes,
  and active public articles. Permit public pages while disallowing `/_site/`,
  `/api/`, and admin-looking paths.
- Render constrained article JSON-LD and Open Graph metadata without inventing
  author, image, rating, statistics, or claims. Apply short shared HTML cache
  lifetimes and immutable caching only to content-hashed assets.
- Enforce a public-specific CSP with no script or third-party connection,
  self-hosted assets only, restrictive referrer/permissions policies,
  `nosniff`, and `frame-ancestors 'none'`. Return generic errors with no
  database, model, or internal-route detail.

### Automated acceptance criteria

- Settings tests reject malformed origins and attacker-controlled host headers
  cannot affect canonical output.
- Sitemap/robots tests exclude internal/inactive content and every sitemap URL
  resolves at the public edge.
- Header/error tests assert the CSP, cache, `nosniff`, referrer, permissions,
  and frame protections, with no stack trace or internal detail in `404`/`5xx`
  responses.

### Completion checklist

- [x] Objective — public pages are shareable and indexable while delivery is
  constrained to a predictable public-only surface.
- [x] Work — validated public-site configuration v1 supplies the configured
  origin, name, and optional description; canonical, sitemap, Open Graph, and
  JSON-LD URLs are derived from that origin only.
- [x] Work — robots and sitemap include only allowlisted public pages, active
  projection articles, and public themes; internal, API, and admin-looking
  paths are disallowed.
- [x] Work — constrained article JSON-LD and Open Graph metadata omit invented
  people, images, ratings, statistics, and claims; HTML/discovery and unhashed
  assets use a five-minute shared cache while content-hashed assets are
  immutable.
- [x] Work — the public edge sends a scriptless/self-host-only CSP, no
  third-party connections, nosniff, restrictive referrer/permissions policies,
  frame denial, and generic no-detail public 404 responses.
- [x] Automated acceptance criteria — settings tests reject malformed origins
  and a hostile Host header cannot change canonical output.
- [x] Automated acceptance criteria — PostgreSQL/edge tests prove sitemap and
  robots exclude internal/inactive content and every sitemap route is served
  through the public edge.
- [x] Automated acceptance criteria — HTTP/static tests assert CSP, cache,
  nosniff, referrer, permissions, frame protections, and generic 404 output
  without internal routing detail.

### Completion evidence

- `public_site/settings.py` implements public-site configuration v1 and
  `rendering.py` derives canonical/Open Graph/JSON-LD output exclusively from
  its validated configured origin.
- `api/routes/public_site.py` emits restricted robots and a projection-only
  sitemap. `frontend/public/nginx` applies the public CSP, browser protections,
  short cache policy, and immutable cache rule only for content-hashed assets.
- `test_public_site_settings` and the live `test_public_edge_isolation` check
  malformed settings, hostile Host canonical isolation, metadata/cache/header
  contracts, discovery routes, and generic edge 404 responses.
- `docker compose -f compose.test.yaml up --build --abort-on-container-exit
  --exit-code-from tests` passed: 187 tests against PostgreSQL+pgvector and the
  built public nginx edge.

## PW-WP6 — Public end-to-end verification and operations

### Objective

Prove the public boundary remains correct across article lifecycle and
batch-taxonomy changes, then document how to operate it.

### Work

- Add a full Compose test covering no-publications launch; approval,
  reapproval, return-to-draft, and archive withdrawal; batch theme rename,
  split, merge, retirement, publication, and rollback; stable article URLs;
  and public-edge isolation.
- Test backups/restores for public projections and theme snapshots alongside
  the batch-taxonomy archive. Verify public reads remain projection-only after
  restoration.
- Update architecture, API, operations, root and frontend READMEs with public
  topology, ports/profiles, allowed routes, settings, cache policy, backup/
  restore, and withdrawal/reapproval behaviour. Document that taxonomy changes
  do not rewrite published article snapshots.

### Automated acceptance criteria

- A clean clone builds and tests both applications and starts the public stack
  with a no-publications state that exposes no internal route.
- Lifecycle and batch-taxonomy fixtures prove public selection and snapshots
  remain correct through every tested transition.
- The documentation review confirms the current reference docs describe the
  batch-only public deployment; no second work-package document is created.

### Completion checklist

- [x] Objective — public lifecycle and batch-taxonomy boundaries are proven
  and their operations are documented.
- [x] Work — the built Compose fixture covers no publications, approval,
  reapproval, return-to-draft, archive withdrawal, stable URLs, and edge
  isolation; it also covers batch rename, split, merge, retirement,
  publication, and rollback without rewriting article snapshots.
- [x] Work — complete-backup restore verification compares public projections
  and revision-scoped theme snapshots alongside batch runs and archive data.
- [x] Work — architecture, API, operations, root, and public frontend docs
  describe topology, routes, settings, caching, restores, lifecycle, and
  immutable taxonomy snapshots.
- [x] Automated acceptance criteria — clean Compose builds and starts a
  no-publications public stack with no internal route exposed.
- [x] Automated acceptance criteria — lifecycle and batch-taxonomy fixtures
  preserve public selection and immutable snapshots through tested changes.
- [x] Automated acceptance criteria — documentation review confirms this is
  the sole current work-package document and describes batch-only deployment.

### Completion evidence

- `test_public_site_e2e` exercises the built `public-web` edge against
  PostgreSQL: no-publications launch, approval, return-to-draft withdrawal,
  reapproval with a stable slug, archive withdrawal, immutable prior theme
  snapshot, blocked internal/API paths, successor rename/split/merge/retired
  theme lineage, publication, and rollback.
- `verify-legacy-archive-restore.sh` now compares `article_publications` and
  `article_publication_themes` counts with batch runs, archive manifest, and
  archived rollout records after an isolated complete restore.
- `README.md`, `docs/architecture.md`, `docs/api.md`, `docs/operations.md`,
  and `frontend/public/README.md` document the public topology, configuration,
  cache/security behaviour, restore process, withdrawal/reapproval, and
  immutable batch-theme snapshots.
- `docker compose -f compose.test.yaml up --build --abort-on-container-exit
  --exit-code-from tests` passed: 189 tests against PostgreSQL+pgvector, the
  built API, and the public nginx edge.

## Public-website explicit non-goals

- The public site does not accept feedback, expose evidence or operational
  data, or replace the internal dashboard.
- It does not make topic directories public or use legacy/candidate taxonomy
  records as a compatibility fallback.
- It does not permit automatic article publication; the existing approved
  article lifecycle remains the sole content-publication rule.
