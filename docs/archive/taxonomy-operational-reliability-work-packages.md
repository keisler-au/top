# Taxonomy operational-reliability work packages

**Status: superseded.** This plan is retained as historical context for the
candidate-taxonomy reliability work. It does not meet the current objective,
because it explicitly retained the incremental taxonomy after production
enablement. Its completed successors are listed in the
[work-package archive](work-packages.md); do not use this plan for new work.

This plan supersedes the historical batch-taxonomy proposal summarized in the
[work-package archive](work-packages.md). It addresses the incomplete
operational path in the current implementation.

## Rules for every package

- Do not publish a taxonomy run automatically. Keep publication disabled until
  the final package enables it through an explicitly configured deployment
  setting.
- Preserve legacy input topic strings and workers until all programmatic
  compatibility checks pass.
- Every mutation must be transactional, idempotent, and safe to retry after a
  worker restart.
- Test database-dependent behaviour against PostgreSQL with pgvector, not a
  mock or string-only SQL assertion.
- Every release gate must be machine-readable and fail closed.

## Sequence

```text
OR-WP1 run creation and immutable snapshot
   -> OR-WP2 resumable pipeline correctness
   -> OR-WP3 complete published-run readers
   -> OR-WP4 PostgreSQL end-to-end verification
   -> OR-WP5 shadow operation and automated quality metrics
   -> OR-WP6 rollback and deployment hardening
   -> OR-WP7 automated production-enable gate
```

## OR-WP1 — Atomic run creation and evidence snapshot

### Objective

Make it possible to create a runnable taxonomy rebuild from the live corpus
without hand-written SQL or test fixtures.

### Work

- Add one service and operator API/CLI command that creates a `taxonomy_runs`
  row and all `taxonomy_run_evidence` rows in one transaction.
- Take a database timestamp cutoff inside that transaction. Select canonical
  evidence at that cutoff: segments when present before the cutoff; otherwise
  the original input. Never select both for an original.
- Require completed inputs and a matching, non-null embedding with the selected
  model, representation, and dimension.
- Record deterministic source and configuration SHA-256 hashes, selected
  evidence count, vector dimension, embedding model, representation, algorithm
  version, prompt versions, and model identifiers.
- Reject a snapshot with missing vectors, mismatched models/representations,
  duplicate canonical targets, or zero evidence. Return structured error counts
  without returning raw evidence text.
- Queue the newly created run only after the snapshot transaction commits.

### Automated acceptance criteria

- PostgreSQL tests prove a late-arriving input is entirely absent from the run.
- Tests cover segmented, unsegmented, duplicate, missing-vector, and model-
  mismatch cases.
- A rollback on any snapshot failure leaves no run, evidence, or queue job.
- Repeating an idempotency key returns the original run without changing its
  evidence membership.

## OR-WP2 — Resumable pipeline and candidate integrity

### Objective

Make clustering, naming, theme inference, and reconciliation reliably resumable
after a process failure.

### Work

- Replace stage-presence heuristics with an explicit durable stage state:
  `snapshot`, `clustering`, `topic_naming`, `theme_inference`,
  `theme_reconciliation`, and `ready_for_review`.
- Add per-stage leases and heartbeats. A worker losing its lease must stop
  writing; an expired lease may be safely reclaimed.
- Persist membership probabilities, noise decisions, centroid dimensions,
  representative selection policy, and all bounded prompt inputs/outputs.
- Finish topic validation in code: literal-evidence support checks, label
  granularity checks, duplicate normalized names, and failed-attempt durability.
- Implement deterministic candidate-theme reconciliation. Preserve original
  candidate themes and attempts; create a reconciled result with antecedent
  links instead of mutating or deleting candidates.
- Make failures stage-specific, retryable with capped backoff, and observable.

### Automated acceptance criteria

- Fault-injection tests restart after each stage and produce the same durable
  result as an uninterrupted run.
- Concurrent workers cannot process the same stage successfully.
- Tests prove no candidate rows can be added after a run is ready, rejected, or
  published.
- Deterministic fixtures cover noise, singleton, duplicate-source,
  zero-vector, segmented-input, duplicate-topic, and overlapping-theme cases.

## OR-WP3 — Complete published-run reader migration

### Objective

Ensure every live consumer uses exactly one published taxonomy run and stable
topic IDs, while historical records retain their original display snapshots.

### Work

- Move dashboard, taxonomy detail, evidence, recommendation, input-detail,
  generation-target, generation-evidence, article editor, and article library
  reads to one shared published-run query layer.
- Use `topic_id` for all new topic relationships. Keep `topic_name` and legacy
  keys only as immutable display/compatibility snapshots.
- Resolve old topic URLs through aliases, including renamed, split, and merged
  topics; return a deterministic redirect/compatibility response when an alias
  maps to more than one successor.
- Ensure unrepresented current evidence remains visible through input views as
  pending/unclassified but is excluded from taxonomy aggregates.
- Make publication a short transaction that switches only the published run;
  do not copy partial data into live tables.
- Add an automated rollback command that republishes a prior eligible run and
  logs the decision durably.

### Automated acceptance criteria

- Every reader returns either the legacy view before the first publication or
  one published run after it—never a mixture.
- Tests prove article tags and citations remain unchanged after topic rename,
  split, merge, retirement, publication, and rollback.
- API contract tests cover numeric topic IDs and legacy aliases for every
  affected endpoint.

## OR-WP4 — PostgreSQL end-to-end reliability suite

### Objective

Make the complete rebuild lifecycle executable in CI against the production
database engine and extensions.

### Work

- Add a disposable PostgreSQL+pgvector integration fixture to CI.
- Test: corpus fixture → atomic snapshot → queue → each durable stage →
  ready candidate → publication → dashboard/input/generation/article reads →
  rollback.
- Add transaction-failure tests for each migration, snapshot insertion,
  publication, rejection, retry, and rollback path.
- Test migration from a legacy-only schema with existing themes, topic strings,
  articles, revisions, jobs, citations, and archived articles.
- Assert operations and quality endpoints never expose raw evidence, prompts,
  responses, credentials, or unbounded error content.
- Run SQL linting, migration-from-empty checks, migration-from-current checks,
  and query-plan/index assertions for representative corpus sizes.

### Automated acceptance criteria

- CI executes the suite on every change to taxonomy code, migrations, or API
  query modules.
- All tests run without network LLM calls by using deterministic structured
  client fixtures.
- A failed test leaves the disposable database schema cleanly removable.

## OR-WP5 — Shadow operation and machine-measured quality

### Objective

Operate scheduled candidate rebuilds without affecting live readers and collect
reproducible reliability/quality signals.

### Work

- Add a configured schedule that creates and queues snapshots in shadow mode.
- Store per-run metrics: snapshot completeness, stage duration, retry count,
  noise rate, topic acceptance rate, duplicate-topic rate, cluster-size
  distribution, run-to-run membership agreement, theme overlap, and drift from
  the prior shadow run.
- Compute quality thresholds from configuration and persist a pass/fail result
  with exact metric values and configuration version.
- Alert on failed runs, stuck leases, stale successful shadow runs, missing
  embeddings, threshold failures, and unexpected drift.
- Keep quality calculations bounded and aggregate-only; do not expose source
  text through operations endpoints.

### Automated acceptance criteria

- A scheduled run cannot publish or change dashboard responses in shadow mode.
- Synthetic stable and drifting corpora produce predictable quality pass/fail
  results.
- Alert conditions are testable from persisted metrics and do not require an
  external monitoring account.

## OR-WP6 — Rollback, deployment, and recovery hardening

### Objective

Prove the system remains recoverable through service, database, and deployment
failures.

### Work

- Add a deployment configuration for the scheduler, database migrations,
  pgvector availability check, worker health checks, and safe shutdown.
- Add an authenticated rollback API/CLI that can select a prior published run
  only when its evidence and candidate state are complete and immutable.
- Define and enforce retention for run snapshots, reports, quality metrics, and
  raw LLM audit payloads.
- Add backup/restore verification for taxonomy tables and a migration rollback
  compatibility policy.
- Add rate limits and authentication/authorization boundaries for all
  taxonomy-run mutation endpoints.

### Automated acceptance criteria

- Container/integration tests prove restart recovery during each pipeline
  stage, including lease expiry and retry.
- A rollback changes every reader consistently and preserves historical
  article snapshots.
- Health checks fail when migrations are missing, pgvector is unavailable, or
  the scheduler cannot acquire a database connection.

## OR-WP7 — Automated production-enable gate

### Objective

Enable publication only when the implementation has met all machine-verifiable
reliability requirements.

### Work

- Add a deployment flag `TAXONOMY_PUBLICATION_ENABLED`, defaulting to `false`.
- Require the publication service to verify: current migration version, a
  successful end-to-end suite artifact, required shadow-run count, recent
  successful shadow run, passing quality thresholds, rollback test artifact,
  complete reader-migration contract version, and no active taxonomy job.
- Store the evaluated gate inputs and result with each publication attempt.
- Keep rejection and rollback available regardless of the flag; do not permit
  automatic publication.

### Automated acceptance criteria

- Publication is rejected when any gate input is missing, stale, or failing.
- A fully passing fixture publishes exactly one run and all reader tests switch
  together.
- The default configuration cannot publish.

## Explicit non-goals

- No manual review, manual test checklist, manual quality annotation, or
  operator sign-off is required by these work packages.
- No retirement of legacy workers occurs in this plan. That is a separate
  change after sustained production operation and a revised contract.
