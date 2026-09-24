# Taxonomy recovery and lifecycle repair

Archived 2026-09-24. Final status: Complete. TR-0 through TR-3 and all
feature-level acceptance criteria have recorded evidence; the affected local
installation was recovered without publishing its failed candidate. Archive
reason: the feature is complete and its lasting behaviour is documented in the
current-state, architecture, API, operations, and dated recovery references.

## Feature contract

Status: complete, 2026-09-24. TR-3 completed the isolated journey, populated
recovery drill, and backup-first recovery of the affected local installation. The completed diagnosis is
[Taxonomy first-run diagnosis — 2026-09-22](../reviews/taxonomy-first-run-diagnosis-2026-09-22.md).
The evidence-continuity choice is accepted in
[ADR-0001](../decisions/0001-cumulative-taxonomy-replacement.md); cumulative
membership implementation is now TR-2 work.
Baseline: `157eeb3909c175c6fec98a3248f05c819549fdae`, dirty tree containing
uncommitted automatic taxonomy implementation, migrations 039/040, dashboard
and operations changes, Compose changes, and architecture/delivery documentation.
The documentation review resumed from clean revision
`1b7a6c7fa9774f24cfa93abcbad010623060da57`, which had incorporated that work
and an undeployed migration 041. Preserve it. No data deletion or quality-gate
bypass is authorized.

Live read-only evidence: run 1 is running, final readiness stage failed three
times with valueerror; quality stage wrote a release attestation but no legacy
quality snapshot. Gate failed topic acceptance (1/3); two labels failed literal
representative support. That state was observed before PostgreSQL later exited
with code 127 on 2026-09-22. The API and database workers now restart because
the database hostname is unavailable; the retained database log does not prove
the exit cause. No service was restarted during the review.

Owners: taxonomy_stages, taxonomy_scheduler, taxonomy_automation,
taxonomy_snapshots, taxonomy_stage_quality, dashboard/operations API and admin
error normalization. Applicable contracts AC-01 through AC-04, AC-06 through
AC-09. Existing publication functions and immutable audit records remain owners.

Inputs/outputs: eligible canonical evidence -> immutable candidate -> leased
stages -> attested reviewable candidate -> gated publication; bounded API errors
must distinguish active work from terminal failure. Retry preserves frozen
outputs and releases/reacquires the existing singleton queue slot atomically.

Decision: automatic replacement candidates use cumulative eligible canonical
evidence through their frozen snapshot cutoff, so every replacement reclusters
the complete set. The prior publication cutoff is only a change trigger, not a
membership filter. See ADR-0001. Deployment/recovery will be presented only
after a concrete tested change. No automatic mutation of old attestations or
accepted/rejected naming results.

## Pipeline

| Package | Status | Dependencies | Output / acceptance |
| --- | --- | --- | --- |
| TR-0 first-run diagnosis | complete | current source, contracts, tests, and read-only live evidence | dated review lists deployed, current-source, security, documentation, verification, and operational findings; no runtime change |
| TR-1 lifecycle and diagnostics | complete | current schema and observed failure | source lifecycle plus current-candidate dashboard/operations status verified locally; migration 041 populated upgrade verified; deployment remains TR-3 |
| TR-2 automation repair | complete | TR-1 status rule; canonical snapshot owner; ADR-0001 cumulative membership | versioned cumulative admission and frozen membership, safe replay, bounded errors, first-run diagnostics, and local verification |
| TR-3 integrated verification and recovery | complete | TR-1/TR-2 | isolated PostgreSQL lifecycle, frontend checks, documentation, concrete operational recovery |

## TR-1 — Lifecycle and first-run diagnostics

Status: complete, 2026-09-22. Input: migration 041 and the source readiness/lease repair
at `1b7a6c7`; the dated first-run diagnosis. Output: locally verified terminal
stage and retry lifecycle plus bounded dashboard/operations status for the
current candidate. Owners: `taxonomy_stages.py`, migration 041, dashboard and
operations API, admin error mapping. AC-01, AC-03, AC-04, AC-06, AC-08, AC-09.
No publication bypass, membership-policy change, live deployment, or data
mutation outside the isolated test database belongs to this package.

The shared status rule selects the current candidate, favors its active state
over stale terminal history, and reports its failed release gate or terminal
failure before a first-run wait. Readers with an existing publication continue
using it. Retry stays explicit, claim-attempt bound, and atomic across
stage/run/job; a failed gate remains nonpublishable. API errors use stable
bounded codes; no raw error details leave the backend.

Objective, work, and acceptance checklist:

- [x] TR1-O1: a real quality result reaches readiness and the existing DB
  publication gate without making a failed attestation publishable.
- [x] TR1-O2: stage terminal failure, cancellation, and explicit retry preserve
  a recoverable run/job/stage lifecycle with stale claims rejected.
- [x] TR1-O3: first-run dashboard and protected operations status identify the
  current candidate's quality block, failure, or active processing truthfully.
- [x] TR1-W1: reconcile current source, migration 041, callers, and existing
  tests; change lifecycle code or schema only where evidence shows a gap.
- [x] TR1-W2: implement a shared bounded candidate-status rule for API
  consumers and update frontend error copy if the wire contract changes.
- [x] TR1-W3: add meaningful PostgreSQL lifecycle/status and frontend tests,
  including stale history and transaction rollback.
- [x] TR1-W4: update API, operations, architecture/current-state, frontend, and
  root references affected by changed behaviour; record exact evidence and
  downstream handoff.
- [x] TR1-A1: isolated PostgreSQL pass/fail attestation, publication gate,
  failure/cancel/retry, stale claim, and rollback tests pass without skips.
- [x] TR1-A2: first-run endpoints and operations status distinguish active,
  quality-blocked, and failed current candidates despite stale history; admin
  error tests, typecheck, and build pass.
- [x] TR1-A3: changed-document links and `git diff --check` pass, and the
  package handoff names remaining deployment and TR-2 inputs.

TR-1 evidence (2026-09-22, baseline `1b7a6c7` plus the preserved documentation
changes and the TR-1 working-tree implementation):

- O1/A1: `docker compose -f compose.test.yaml run --rm tests` passed 205 tests
  with no skips in isolated PostgreSQL+pgvector/public-edge services. The
  computed pass/fail attestation test drives all six taxonomy stages and the
  existing publication function. The populated 040-to-041 upgrade test proves
  stranded run/job failure while retaining its failed attestation and no
  publication. Terminal failure, cancel/retry, same-owner stale attempt, and
  queue-transition rollback tests passed. The earlier full Compose run failed
  one newly added fixture setup that attempted a protected published-run
  transition; the corrected fixture and final 205-test run passed.
- O2/W1/W3: `taxonomy_stages.py` and migration 041 already implement the
  guarded lifecycle; no second lifecycle owner or schema rewrite was added.
  The new populated upgrade, rollback, and same-owner tests cover the missing
  boundary evidence. `env UV_CACHE_DIR=/tmp/triage-uv-cache uv run python -m
  unittest tests.test_dashboard_api -v` from `backend` passed 13 tests.
- O3/W2/A2: `taxonomy_status.py` now provides one bounded latest-candidate
  rule to dashboard and operations routes. New PostgreSQL cases cover active
  successor after old failed quality, terminal failure, and failed gate with
  no raw details. A focused PostgreSQL follow-up also passed for a newest
  superseded run after rollback, retaining the older active publication.
  `npm test` passed 9 test files with zero failures/skips;
  `npm run typecheck` and `npm run build` passed from `frontend/admin`.
- W4/A3: API, operations, architecture, current-state, frontend, root, and
  delivery references were reviewed and updated. A local check of 41 relative
  links across 10 changed documents found zero missing targets;
  `git diff --check` passed; the active-plan check returned only
  `docs/work-packages.md`.

TR-1 handoff: the local source now reports the newest candidate rather than
stale terminal history. HTTP codes remain bounded and unchanged; there is no
new schema or wire payload. Migration 041 still needs to be applied together
with a matching built image during TR-3; this package did not touch the live
database or production services. TR-2's concrete inputs are the shared
candidate-status rule, the canonical snapshot owner, ADR-0001, and the
diagnosis findings TFR-05 through TFR-12. TR-2 must repair admission,
cumulative membership, replay and policy failure states, including tying
operator status to the durable automatic decision rather than unrelated manual
run history. TR-1 evidence does
not satisfy those criteria or the complete automatic Compose journey.

## TR-2 — Automation admission and cumulative replacement

Status: complete, 2026-09-23. Baseline: `1b7a6c7` plus the preserved TR-1 and decision
working tree shown above. Inputs: ADR-0001, TR-1's candidate status rule,
`create_taxonomy_snapshot` as the sole frozen-membership owner, migration 041,
and TFR-05 through TFR-12. Output: automatic candidate creation from a
validated cumulative canonical set, durable bounded replay/failure state, and
truthful first-run policy diagnostics. AC-01 through AC-04, AC-06, AC-08,
AC-09 apply. No mutation of existing run membership, attestations, or accepted
naming results; no quality-gate bypass or live recovery.

Objective, work, and acceptance checklist:

- [x] TR2-O1: first-run admission waits for enough processable evidence and
  supports generic, contextual, and mixed answers in one compatible vector
  space; invalid model/dimension stays bounded and visible.
- [x] TR2-O2: every automatic replacement freezes all eligible canonical
  evidence through its cutoff and reclusters it; late embeddings on old inputs
  can trigger a replacement without removing earlier coverage.
- [x] TR2-O3: a failed quality candidate does not block a materially changed
  successor, while identical failed evidence cannot create an automatic loop;
  reserved decisions replay their original frozen membership after a crash.
- [x] TR2-O4: unexpected automation errors have bounded durable retry/terminal
  state and no permanent false first-run wait or unbounded log loop.
- [x] TR2-W1: use the canonical snapshot selector for admission and snapshot
  membership; separate change detection and debounce from membership filtering.
- [x] TR2-W2: align minimum evidence with clustering inputs and mixed
  representation validation across snapshot and clustering consumers; version
  policy/configuration defaults consistently.
- [x] TR2-W3: migrate durable decision retry and membership-mode metadata for
  safe replay of old reserved decisions; update scheduler schema readiness.
- [x] TR2-W4: update dashboard/operations bounded diagnostics and admin error
  handling for automation blocks; preserve operator auth and published readers.
- [x] TR2-W5: add real PostgreSQL+pgvector tests for first-run admission,
  cumulative replacement, failed-gate successor, replay, terminal errors,
  fresh initialization and populated upgrade; add frontend mapping tests.
- [x] TR2-W6: update affected API, architecture, operations, current-state,
  root and frontend references; record exact evidence and TR-3 handoff.
- [x] TR2-A1: isolated database tests prove generic/mixed evidence and minimum
  clustering input, bounded invalid vectors, and cumulative old/new membership.
- [x] TR2-A2: isolated database tests prove late readiness, no identical
  failure loop, changed-evidence successor after failed gate, crash replay,
  bounded unexpected-error retries, and publication gate preservation.
- [x] TR2-A3: first-run API/operations and frontend tests distinguish active,
  blocked, and failed automation states with bounded codes; backend/frontend
  suites and typecheck/build pass with exact skips reported.
- [x] TR2-A4: fresh schema, populated upgrade, changed-document links,
  `git diff --check`, and downstream assumptions are verified and documented.

TR-2 interface and recovery contract: automatic admission and
`create_taxonomy_snapshot` use the same canonical selector. A decision stores
its policy version, cumulative evidence fingerprint, membership mode, admission
cutoff, predecessor cutoff for audit, and bounded retry state. The snapshot
cutoff is immutable and reused after a crash. Existing reserved decisions
default to historical `post_cutoff` mode; new decisions use `cumulative` mode.
Only the existing database publication function may promote a passing
attestation. A failed gate retains the prior published run. A changed evidence
fingerprint may reserve a successor; the unchanged fingerprint reuses its
terminal result. The scheduler writes heartbeat and bounded evaluation-error
state; the API exposes only stable codes. Operator authorization and the
existing publication readers remain the owners of their boundaries.

TR-2 evidence (2026-09-23, starting revision
`1b7a6c7fa9774f24cfa93abcbad010623060da57` plus the preserved uncommitted
TR-1/decision tree and this uncommitted TR-2 implementation):

- O1/W1/W2/A1: the PostgreSQL+pgvector integration cases
  `test_generic_only_inputs_create_an_automatic_candidate`,
  `test_automation_accepts_generic_and_mixed_evidence_and_rejects_incompatible_vectors`,
  and `test_automation_reports_model_dimension_and_representation_errors_as_invalid`
  prove generic, contextual, and mixed admission with bounded invalid-vector
  errors. The real HDBSCAN three-row test reaches the configured clusterer;
  policy v2 records `min_cluster_size=3` and `min_samples=2`. Snapshot and
  clustering readers share the `mixed` compatibility rule in ADR-0002.
- O2/O3/W1/A2: the cumulative replacement integration case proves a published
  run's five earlier rows remain in a six-row replacement after a pre-cutoff
  input gets a late embedding; a changed successor has seven rows after the
  failed quality gate, while unchanged evidence creates no repeat and the
  prior publication remains served. The admission-cutoff race test freezes five
  rows despite a sixth arriving before the snapshot write, then admits all six
  on a successor. Legacy reserved and cumulative committed-snapshot replay
  cases prove both membership modes. The existing publication-gate and TR-1
  computed-attestation cases remain passing in the final suite.
- O4/W3/W4/A2/A3: reserved snapshot failures retry with durable 5/10-second
  backoff and stop after three attempts; scheduler evaluation failures stop
  after three attempts per policy version. PostgreSQL tests cover those states,
  policy-version reset, heartbeat expiry, first-run codes, operator status,
  protected routes, and preservation of published readers. Admin error mapping
  tests cover processing, blocked automation, and scheduler unavailability.
  Migration 042 preserves populated old decisions and adds immutable replay
  metadata. Scheduler health requires its migration marker.
- W3/W5/A4: the fresh `docker compose -f compose.test.yaml down` followed by
  `docker compose -f compose.test.yaml up --build --abort-on-container-exit
  --exit-code-from tests` initialized PostgreSQL with migrations 042 and 043
  and passed **218 backend/database/public-edge tests, zero skips**. The
  populated 040→041, 041→042, and 042→043 upgrade fixtures pass; migration
  lint and current-schema marker/reapply checks pass. The isolated stack has
  PostgreSQL+pgvector, API, and public edge, but no evidence workers, taxonomy
  scheduler, or Ollama; the complete Compose journey remains TR-3.
- W4/W5/W6/A3/A4: from `frontend/admin`, `npm test` passed 9 test files with
  zero failures/skips, and `npm run typecheck` and `npm run build` passed.
  API, operations, architecture/contracts, current-state, root, admin, and
  decision references were updated. A relative-link check found 83 valid links
  across 12 changed Markdown files and zero missing targets; `git diff
  --check` passed. The active-plan search returned only
  `docs/work-packages.md` outside its archive.

Verification drift: the first fresh run passed 217 tests before the added
dimension/representation case. Two subsequent 217-test runs failed only the
existing concurrent operations rate-limit test (four 200 responses rather than
two). Investigation found the old SQL combined a rounded epoch integer with a
truncated second, allowing adjacent window keys. Migration 043 uses one
whole-window floor, preserves populated counters, and the final 218-test fresh
run passed. This narrow repair was needed to make the operator boundary and
full acceptance gate deterministic.

TR-2 handoff: the local code now builds each automatic replacement from the
latest frozen cumulative embedding set; the policy version changes to v2 and
new decisions use cumulative mode. Migrations 041–043 and a matching image
must be deployed together in TR-3. That package must inspect the live
PostgreSQL exit-127 cause, preserve the failed attestation and prior
publication, run the evidence workers, scheduler, and Ollama in an isolated
end-to-end journey, and verify the documented live recovery before any plan
closure. No production database or service was changed in TR-2.

## TR-3 — Integrated verification and operational recovery

Status: complete, 2026-09-24. Baseline:
`1b7a6c7fa9774f24cfa93abcbad010623060da57` plus the preserved uncommitted
TR-1/TR-2 implementation and documentation listed in the feature contract.
Inputs: migrations 041–043, the matching current application source, the
TR-1/TR-2 acceptance evidence, the stopped local PostgreSQL container, and the
downloaded local Ollama models. Output: a production-shaped isolated journey,
verified upgrade/recovery behaviour, current frontend and documentation, and a
concrete recovery record for the affected installation. AC-01 through AC-04
and AC-06 through AC-09 apply.

The isolated journey may create and destroy only its disposable Compose
project, database, and model cache. The affected persistent stack remains
read-only until separately authorized: completing repository work does not by
itself authorize deployment, restart, backup, migration, or mutation of that
installation. Recovery instructions must keep migrations 041–043 and the
matching image together, preserve the failed attestation and any publication,
and validate bounded post-upgrade status before workers resume.

Objective, work, and acceptance checklist:

- [x] TR3-O1: a built, production-shaped isolated Compose journey accepts
  inputs, runs eligibility/segmentation and embedding workers, admits and runs
  the automatic taxonomy scheduler through its durable stages, and reaches a
  bounded publication or quality decision without operator mutation.
- [x] TR3-O2: fresh and populated-upgrade verification proves migrations
  041–043 preserve immutable attestations/publications, reconcile the stranded
  run/job lifecycle, and keep the failed candidate nonpublishable.
- [x] TR3-O3: the affected installation's PostgreSQL exit is explained from
  container evidence and has an exact backup-first, synchronized-image/schema,
  validation, and recovery procedure with stop conditions.
- [x] TR3-O4: all feature acceptance, references, and package metadata agree;
  the completed plan is archived only after every criterion has evidence.
- [x] TR3-W1: add the smallest durable isolated acceptance harness and fixtures
  needed to exercise real Compose services and model protocols across the
  complete automatic journey; keep it separate from persistent application
  data and make failures observable.
- [x] TR3-W2: run the full isolated PostgreSQL/public-edge suite from a fresh
  schema, populated migration upgrades, the complete Compose journey, and
  frontend tests/typecheck/build; report skips and environmental limits.
- [x] TR3-W3: inspect the stopped PostgreSQL container and retained logs,
  reconcile the diagnosed failure with current Compose mounts, and document
  exact preflight, backup, deploy, validation, and failure-recovery commands.
- [x] TR3-W4: review and update root, current-state, architecture, API,
  operations, frontend, CI/test documentation, active-plan metadata, and the
  archive index wherever the verified behaviour changes their claims.
- [x] TR3-W5: reconcile every TR-3 and feature-level checkbox against evidence,
  check downstream assumptions, record the durable closing handoff, and mark
  the package complete before archiving the plan.
- [x] TR3-A1: the disposable Compose journey proves at least three inputs move
  through both evidence workers into one cumulative automatic candidate; all
  taxonomy stages finish and the immutable gate alone determines publication.
- [x] TR3-A2: fresh initialization and populated 040-to-current upgrade tests
  pass without skips, including stranded-stage repair and immutable failed-gate
  preservation; current migration markers and scheduler health agree.
- [x] TR3-A3: backend/database/public-edge checks and frontend tests,
  typecheck, and build pass; exact commands, counts, skips, environment, and
  working-tree identity are recorded.
- [x] TR3-A4: the recovery record names the observed exit cause, verifies the
  current mount sources before restart, backs up before migration, deploys one
  matching source/schema set, and checks migration 041 reconciliation plus
  migrations 042–043 without bypassing the quality gate.
- [x] TR3-A5: changed-document links, the single-active-plan rule, and
  `git diff --check` pass; TR-A5 and all remaining feature criteria are checked,
  references describe implemented rather than merely planned behaviour, and
  the completed plan is archived with its evidence intact.

TR-3 evidence (2026-09-23 through 2026-09-24, starting revision `1b7a6c7` plus
the complete preserved working tree):

- O1/W1/A1: `compose.taxonomy-journey.yaml` and its black-box assertion script
  exercised the API, both evidence workers, real Ollama `nomic-embed-text`
  embeddings, scheduler, all seven durable stages, release gate, and automatic
  publication. Six inputs and embeddings produced a cumulative six-row run;
  every stage completed at attempt one, the immutable gate passed, and one run
  published without operator mutation. Structured chat was deterministic, so
  this proves service/protocol/lifecycle integration rather than chat-model
  quality. The disposable tmpfs database and model volume were removed.
- O2/W2/A2/A3: after `docker compose -f compose.test.yaml down`, the fresh
  `docker compose -f compose.test.yaml up --build --abort-on-container-exit
  --exit-code-from tests` passed 218 tests with zero skips. It includes fresh
  markers, populated 040→041, 041→042, and 042→043 upgrades, immutable failed
  attestations, publication gating, API, and public-edge checks. `npm test`
  passed nine frontend files with zero failures/skips; `npm run typecheck` and
  `npm run build` passed. Both acceptance Python fixtures compiled. CI now
  watches the actual admin path and runs database/public-edge, full journey,
  and frontend jobs.
- O2/O3/W3/A4: Docker container state identified the exit-127 cause as a stale
  Docker Desktop/WSL bind source that could not mount a file, not a PostgreSQL
  process failure. A read-only clone of the affected volume reproduced the
  migration-040 stranded state. Its readable 474,948-byte custom-format backup
  had SHA-256 `be52af0c6588052040f8c4ac43fa58cde8ade41d32dcd8a6d87fab5a7e3fb3f9`.
  Applying 041–043 changed run/job 1 to failed, retained its exact failed
  attestation/hash, published nothing, preserved legacy `post_cutoff` replay,
  and passed current scheduler health. The disposable clone was removed.
- O3/A4: after explicit deployment approval, consumers were stopped and the
  source volume was copied read-only to retained volume
  `triage-postgres-pre-recovery-20260923`. A live logical backup was readable
  (474,948 bytes, SHA-256
  `dad64887e783397ea77b4a6e90360044320f4b48f363b08d59ba00f9c3ae4669`).
  Current images were built, PostgreSQL was recreated from valid current
  mounts, and migrations 041–043 applied before consumers restarted. Live
  validation reproduced the clone result: run/job 1 failed, the nonpassing
  attestation and hash stayed unchanged, and published count stayed zero.
  Scheduler, PostgreSQL, API, admin, Ollama, and public-edge health passed;
  `/api/dashboard/summary` returned bounded
  `taxonomy_quality_blocked`. Operator tokens are unconfigured, so protected
  operations correctly remain unavailable and are not claimed as evidence.
- O4/W4/W5/A5: root, documentation guide, current-state, architecture
  contracts, operations, frontend, CI, dated recovery record, decisions, and
  archive index were reviewed and updated. The final link check found 142 valid
  relative links across 68 Markdown files and no missing target. The
  active-plan search and archived unchecked-item search produced no output;
  default, test, and journey Compose configurations passed `config --quiet`;
  the workflow YAML parsed; and `git diff --check` passed. There is no
  downstream package: the feature is complete and this evidence remains in its
  archive.

TR-3 handoff: the affected local stack is recovered on migrations 041–043 and
matching rebuilt application/admin images. The failed first candidate remains
nonpublishable and truthfully quality-blocked. New materially changed evidence
may produce a cumulative successor through ordinary automation. Retain
`triage-postgres-pre-recovery-20260923` until a normal post-recovery backup has
been taken and independently verified; removing that retained backup is an
operator decision, not package cleanup. Retired legacy worker containers remain
stopped orphans and were not deleted because cleanup was outside this package.

## Acceptance and handoff

- [x] TR-A1: real quality computation -> readiness succeeds for pass and fail;
  passing candidate publishes through existing DB gate, failing candidate does not.
- [x] TR-A2: stage failure/cancellation and explicit retry keep run/job/stage
  consistent; stale claims cannot change results; transaction rollback verified.
- [x] TR-A3: crash replay and eligibility changes cannot strand automation;
  unchanged failed evidence never causes an automatic creation loop.
- [x] TR-A4: dashboard/operations distinguish quality block, candidate failure,
  and genuine first-run processing, with frontend error tests and build.
- [x] TR-A5: affected documentation and links checked; exact test commands,
  results, limitations and live recovery recorded before closure.
- [x] TR-A6: a replacement run reclusters cumulative canonical evidence,
  including earlier classified rows and late embeddings on pre-cutoff targets;
  unchanged evidence does not create repeated candidates, and a failed quality
  gate leaves the prior publication served.

## Prior 2026-09-22 diagnosis handoff

Review: [taxonomy first-run diagnosis](../reviews/taxonomy-first-run-diagnosis-2026-09-22.md).
No application or production state was changed. Current-source backend and
frontend checks pass, including a 201-test isolated PostgreSQL/public-edge run,
but that harness does not contain the evidence workers, taxonomy scheduler, or
Ollama and therefore does not satisfy the automatic Compose journey.

Decision resolved: ADR-0001 requires cumulative replacement membership. TR-2
implementation had to make admission detect newly ready evidence independently of
the complete canonical snapshot, including late embeddings on older targets.
It must prove earlier and newer evidence both contribute to replacement
clusters, while failed gates retain the published run and unchanged evidence
cannot loop. The decision alone does not satisfy TR-2 or TR-A3.

At diagnosis time, local repair was not yet authorized. Live recovery still
requires PostgreSQL cause analysis, one identifiable code/schema deployment,
and verification that migration 041 reconciles the stranded lifecycle without
publishing the failed quality attestation. No production state was changed for
the decision or TR-1.

Decision-documentation check on 2026-09-22 at `1b7a6c7` plus the preserved
dirty tree: `git diff --check` passed; a local relative-link check found no
missing targets across the four changed documents (29 links); the active-plan
file check returned only `docs/work-packages.md`. No application tests were run
for this documentation-only decision. TR-2 and TR-3 were still open then.
