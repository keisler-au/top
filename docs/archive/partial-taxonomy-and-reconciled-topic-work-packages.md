# Partial taxonomy and reconciled-topic work packages

Final status: **complete**. Archived 2026-10-10 after PTR-8 and PTR-F1–F6
verification. Source is implemented and verified, not merged or deployed.
See final package evidence and feature closure below.

## Concise pipeline reference

```text
Prepare evidence
→ cluster similar answers within each question
→ reject incoherent or insufficiently distinct clusters
→ label each passing cluster with an LLM using up to 40 representative answers
→ validate response format and evidence links, not meaning by word matching
→ merge equivalent topics across questions while retaining their evidence
→ infer optional themes from related, distinct topics
→ publish one immutable taxonomy with explicit with-topic/without-topic coverage
```

The design gives semantic work to embeddings and the LLM, and gives
deterministic code the facts it can prove: cluster shape, valid identifiers,
bounded output, traceable evidence links, non-overlapping reconciliation,
truthful coverage, and safe publication. Equivalent topics merge; merely related topics
remain distinct and may share a theme. Valid topics are useful even when other
evidence has no topic or no broader theme exists.

## Resumption record — 2026-10-07

Starting HEAD: `8b3910acdf88bddb87e4f10a41819c6bfad595b6`. Existing dirty tree contains PTR-0–PTR-2 source, tests, documentation, configuration, migrations 044/045 and unfinished PTR-3 module/tests/migration 046. Preserve all existing changes. Revalidated running scheduler: lexical label validation removed, gate-v2 still active; historical run 2 retains immutable rejected attempts. Documentation guide/current-state lag package completion. Acceptance checklist is every remaining Objective, Work and A criterion in PTR-3–PTR-8 below; each package remains incomplete until its boundary evidence is recorded. New release policy must use a new automation version so unchanged evidence can receive one successor without retrying the rejected run.

## Resumption record — 2026-10-08 (PTR-3)

Starting HEAD: `8b3910acdf88bddb87e4f10a41819c6bfad595b6`. The starting
checkout has 49 modified tracked files and 11 untracked files, including
PTR-0–PTR-2 work, the unfinished reconciliation module/pure tests/migration
046, and later-package edits (047/048, quality, publication, API and dashboard).
All are preserved. This session completes PTR-3; later packages retain their
separate acceptance obligations. Revalidated provisional inputs and existing
stage handler. Remaining checklist: A1/A2 shortlist and byte bounds; A3 semantic
fixtures; A4 invalid/contradictory rollback; A5 exact union and source guards;
A6 separate counts; A7 crash/transport replay, concurrent writers and lost
leases; A8 replacement/split/merge/new lineage; fresh/populated migration,
reference updates and PTR-4 handoff. Migration 046 is untracked, has no live
deployment evidence, and is completed here before deployment.

## Resumption record — 2026-10-08 (PTR-4)

Starting HEAD: `8b3910acdf88bddb87e4f10a41819c6bfad595b6`, with the
same 49 modified tracked and 11 untracked paths preserved from PTR-3.
PTR-3 canonical revisions, antecedents, exact memberships and stage order
exist and match its handoff. Existing PTR-4 edits include optional theme
neighborhoods, gate-v3 Python and untracked migration 047; 048 and API/admin
edits belong to later packages and remain preserved. Checklist: A1 canonical
bounded theme packets; A2 related/equivalent distinction; A3 zero themes and
materialization; A4 exact coverage; A5 question/submission counts; A6 partial
and rejected attempts pass; A7 stage/membership/trace/arithmetic failures;
A8 immutable/replayed/leased/private attestation; fresh and populated 047,
reference consistency and PTR-5 handoff. Migration 047 has no deployment
evidence and is completed here before deployment.

Resumed after interruption: HEAD unchanged; 51 tracked paths modified and 12
untracked paths now include the PTR-4 implementation/tests above. Pending
commands finished: 81 taxonomy pure tests passed; initial nine PostgreSQL
cases had one fixture error (attempted to rewrite an immutable completed
stage) and one security failure. The review-only configuration exposed an
existing empty-token comparison bug in `api/security.py`; AC-07 requires its
small shared-owner correction to prove PTR-4's protected diagnostics boundary.
All prior changes remain preserved.

## Feature contract: PTR — partial taxonomy with reconciled topics

- **Status / last updated:** Complete; 2026-10-10. PTR-0 through PTR-8 and PTR-F1–F6
  are implemented and verified in the preserved dirty checkout. The 2026-10-07 user request authorizes completion of PTR-3 through PTR-8 in the repository and disposable verification; live deployment and application-data changes remain outside scope.
- **User request and authorized scope:** Plan future implementation of scope 2:
  publish valid topics when some evidence has no topic, with explicit coverage;
  replace lexical topic validation with cluster-quality plus LLM semantic
  labelling; provide all evidence up to 40 or 30 central plus 10 diverse; and
  reconcile equivalent topics across questions before theme inference; require
  immutable question context for every input; retain evidence-processing
  statuses so ineligible input is not embedded; remove input-facing taxonomy
  states; and derive every input's current topics/themes only from the published
  run. The 2026-09-29 request to review and complete the next package authorizes
  PTR-1 repository implementation and disposable verification, but not live
  deployment or application-data changes. The 2026-09-30 request to identify
  the prior handoff and continue the next package authorizes PTR-2 repository
  implementation and disposable verification, but not live deployment or
  application-data changes.
- **Outcome and feature-level acceptance IDs:**
  - PTR-F1: A coherent cluster can produce a canonical topic without exact
    word overlap between its description and every evidence item.
  - PTR-F2: Equivalent provisional topics from different questions become one
    canonical topic whose evidence union and antecedents are durable.
  - PTR-F3: Related but non-equivalent topics remain distinct and can share an
    optional theme.
  - PTR-F4: One published taxonomy may have partial topic coverage; its coverage reports
    evidence with and without canonical topics, while input readers expose
    current topic/theme associations without a taxonomy classification state.
  - PTR-F5: A run with at least one publishable topic and no themes can be
    published and used for topic browsing and topic-targeted generation.
  - PTR-F6: Replacement, rollback, replay, concurrency, audit, article
    provenance, and public exposure remain safe at the single-run boundary.
- **Non-goals:** Independent topic publication from multiple runs; manual
  mutation of model output inside an immutable candidate; automatic merging of
  merely related concepts; changing approved article snapshots; changing the
  Google Sheets identity/import contract; removing evidence preparation,
  worker, taxonomy-run, or editorial lifecycle statuses; re-embedding unchanged
  evidence for every run; selecting numerical similarity thresholds without
  evaluation evidence.
- **Baseline revision and relevant uncommitted work:** Clean
  `466275729316274d7d0a55414d8b02293f5a92b1` before this documentation-only
  plan and ADR were added. There was no pre-existing `docs/work-packages.md`.
  The plan was revalidated at clean `8b3910acdf88bddb87e4f10a41819c6bfad595b6`
  before this state-free association amendment.
- **Current behaviour and evidence:** `taxonomy_clustering.make_cluster_plan`
  runs question-scoped HDBSCAN over normalized frozen contextual embeddings,
  applies the calibrated geometry policy, and persists an all-<=40 or
  30-central+10-diverse packet. `taxonomy_topics.validate_topic_response`
  checks only structure, bounds, normalized collisions, and exact packet IDs;
  at most two immutable attempts can produce one separate provisional topic.
  PTR-4's `taxonomy_stage_quality` now computes gate-v3 consistency and
  exact with-topic/without-topic coverage; rejected attempts and zero themes
  are valid. The installed local runtime still uses gate v2 until deployment.
  PTR-5 verified the new PostgreSQL publication transitions; PTR-8 rechecked the complete feature. Dashboard taxonomy readers require
  exactly one `published` run. Input responses retain evidence-processing
  status and expose published topic/theme associations without a taxonomy
  lifecycle field. Read-only run 2 evidence is recorded in ADR-0003.
- **Delivered behaviour and existing owners:** Extend embeddings and
  snapshots under AC-02; clustering in `taxonomy_clustering.py`; structured
  model transport in `clients/llm.py`; provisional naming in
  `taxonomy_topics.py`; add durable topic reconciliation beside existing theme
  reconciliation; extend scheduler stages and automation rather than adding a
  queue; replace publication functions by numbered migration; update dashboard,
  inputs, operations, generation, admin contracts/pages, and existing test
  harnesses together. Preserve evidence-processing statuses, remove the
  computed input `taxonomy_state`, and resolve input topics/themes from the one
  published run; empty associations are normal.
- **Applicable AC IDs and decision records:** AC-01 through AC-09 as applicable,
  especially AC-02, AC-03, AC-04, AC-06, AC-08 and AC-09; ADR-0001,
  ADR-0002, and [ADR-0003](../decisions/0003-partial-taxonomy-and-topic-reconciliation.md).
- **Open decisions, assumptions and risks:** PTR-0 selected
  `partial-topic-policy/v1`, the existing contextual vector within immutable
  question scopes, calibrated geometry thresholds, a 32,768-byte packet bound,
  and a same-concept reconciliation rubric. PTR-2 selected
  `partial-topic-naming/v1` with at most two immutable structural attempts per
  cluster. Remaining risks include model-specific
  threshold drift, LLM over-merging related topics, transitive merge
  inconsistency, double-counting one submission across questions, and
  prompt/audit truncation.
  Each deployment must audit any existing questionless inputs before enforcing the
  required-question boundary; historical question wording cannot be invented.
- **Migration/deploy order, compatibility window and recovery:** PTR-0 has no
  production mutation. If PTR-0 selects a second durable embedding identity,
  PTR-1 delivers its compatibility migration and backfill; otherwise PTR-1
  retains the current schema. Subsequent storage changes use new numbered
  migrations and update `init.sql` plus scheduler readiness markers.
  PTR-1 audits questionless rows before a numbered migration makes
  `original_inputs.question_id` non-null; unresolved rows block that migration.
  Migration 045 then adds provisional identities without rewriting prior
  attempts or published topics; deploy it with the scheduler configured for
  `partial-topic-naming/v1` because scheduler health requires its marker.
  Deploy migrations with matching scheduler/API/admin images; do not run an old
  scheduler against the new stage lifecycle. Preserve the prior publication
  through candidate construction. Create a new versioned cumulative candidate;
  never rewrite run 2 or its attestation. On failure, stop the new scheduler,
  retain the old publication, and diagnose immutable stage records. Rollback of
  a successful replacement uses the existing explicit run rollback boundary.

| Interface / data / setting | Owner | Before → after | Producers and consumers | Compatibility / verification |
| --- | --- | --- | --- | --- |
| Embedding representation and snapshot provenance | `workers/embeddings.py`, `taxonomy_snapshots.py`, `taxonomy_automation.py`, `input_embeddings` | Current answer-only/question-answer compatibility → reuse `question-answer` vectors under `partial-topic-policy/v1`, scoped by immutable question | Embedding worker → snapshot admission → clustering | PTR-0-A1, PTR-1-A1–A3; no representation backfill selected |
| Cluster plan and diagnostics | `taxonomy_clustering.py`, run configuration, `taxonomy_cluster_*` | HDBSCAN with 3 central + 1 diverse and no release cohesion/separation contract → versioned per-question clustering, calibrated checks, all <=40 or 30 central + 10 diverse | Scheduler clustering stage → topic labelling, review, quality | PTR-1-A4–A7; pure fixtures and PostgreSQL persistence/replay |
| Provisional naming | `taxonomy_topics.py`, `taxonomy_topic_naming_attempts`, model audit | Exact lexical overlap can accept/reject meaning → LLM owns semantics; code validates shape, bounds, identity, membership, and provenance | Topic naming stage → reconciliation and operations review | PTR-2-A1–A6; adversarial shape/provenance tests and real stored fixtures |
| Canonical topic reconciliation | New owner beside `taxonomy_reconciliation.py`; new migration/tables; scheduler stage | Every accepted cluster immediately acts as a topic; only exact-name collision exists → immutable provisional topics are reconciled into non-overlapping canonical equivalence groups with unioned memberships | Provisional naming → theme inference, taxonomy readers, lineage, generation | PTR-3-A1–A8; PostgreSQL atomicity/replay/concurrency tests |
| Theme inference | `taxonomy_themes.py`, `taxonomy_reconciliation.py`, theme identity functions | Consumes accepted cluster topics; at least one reconciled theme required → consumes canonical topics; zero themes is a valid outcome | Canonical topics → themes → quality/publication/readers | PTR-4-A1–A4 |
| Release checks and publication | `taxonomy_stage_quality.py`, `taxonomy_automation.py`, publication SQL functions | Acceptance ratio >=0.80 and >=1 theme block the whole run → coverage is reported but does not block publication; processing must be finished and stored results must agree; >=1 valid topic is required | Quality stage/automation/API → PostgreSQL transition → all readers | PTR-4-A5–A8, PTR-5-A1–A7, PTR-7-A5/A6; migration, publication-check, replacement and rollback tests |
| Input associations and processing status | `api/routes/inputs.py`, API/admin contracts, `original_inputs.status` | Computed `taxonomy_state` plus optional question context → required question context; evidence-processing status retained; `taxonomy_state` removed; topics/themes projected from one published run and may be empty | Evidence workers and published run → API/admin/external consumers | PTR-1-A8, PTR-5-A3, PTR-6-A1–A3, PTR-7-A1–A3 |
| Dashboard/operations/generation | Dashboard queries/routes, operations, generation, admin | No publication returns 503; summaries count topic-linked evidence only; themes assumed available → partial publication is readable, run coverage reports with-topic/without-topic counts, zero-theme topic generation works | API → admin; generation worker → articles | PTR-6-A4–A9 |
| Public projection | `articles.py`, article approval, `public_site/` | Approved immutable article/theme snapshots | Same projection; candidate evidence and evidence without topics remain private; topic-origin articles remain valid | Editorial approval → public edge | PTR-6-A10, PTR-7-A4 |

## Pipeline

| Package | Status | Dependencies and required outputs | Outputs / consumers | Completion evidence |
| --- | --- | --- | --- | --- |
| PTR-0 — representation and policy calibration | complete | Current clean baseline, ADR-0003, frozen privacy-safe evaluation method | `partial-topic-policy/v1`, contextual per-question scope, four thresholds, 32,768-byte bound, reconciliation rubric | PTR-0-A1–A6 passed 2026-09-29 |
| PTR-1 — coherent clusters and bounded evidence packets | complete | PTR-0 `partial-topic-policy/v1` and its thresholds/bounds | Required-question boundary, traceable evidence preparation, durable cluster diagnostics, and deterministic <=40/30+10 packets consumed by PTR-2 | PTR-1-A1–A10 passed 2026-09-30 |
| PTR-2 — structurally validated provisional topics | complete | PTR-1 cluster eligibility and packets | Immutable provisional topic attempts with no lexical semantic gate consumed by PTR-3 | PTR-2-A1–A6 passed 2026-09-30 |
| PTR-3 — cross-question canonical topic reconciliation | complete | PTR-2 provisional identities/memberships; PTR-0 equivalence rubric | Canonical topics, antecedents, unioned evidence and lineage consumed by themes/readers | PTR-3-A1–A8 passed 2026-10-08; focused upgrade passed |
| PTR-4 — optional themes and coverage attestation | complete | PTR-3 canonical topics; PTR-0 calibrated publication policy | Themes over canonical topics; immutable with-topic/without-topic coverage attestation consumed by publication | PTR-4-A1–A8 passed 2026-10-08; fresh/populated 047 verified |
| PTR-5 — partial publication and published-run associations | complete | PTR-4 attestation; numbered migration; stable coverage vocabulary | Atomic publication plus state-free input topic/theme projection consumed by admin/generation | PTR-5-A1–A7 passed; P1–P7 (2026-10-09) |
| PTR-6 — admin review, coverage, and topic generation | complete | PTR-5 backend contracts | Operator-visible partial topics, unresolved clusters, coverage and zero-theme generation | PTR-6-A1–A10 passed; U1–U4 (2026-10-09) |
| PTR-7 — replacement associations and historical isolation | complete | PTR-5 publication/association contract; PTR-6 reader contracts | Current inputs reflect only the newest publication while earlier runs and approved articles remain unchanged | PTR-7-A1–A6 passed; R1–R4 (2026-10-09) |
| PTR-8 — integrated lifecycle, migration, and handoff | complete | PTR-1–PTR-7 complete outputs | Full Sheets-to-partial-publication journey, upgrade/recovery evidence, current references | PTR-8-A1–A8 passed; J1–J5 (2026-10-10) |

All packages are complete. PTR-8 closed the feature on 2026-10-10 with
fresh disposable PostgreSQL, populated-upgrade preservation, the complete
Sheets/API-to-publication journey, frontend checks and final reference review.
The integration owner is PTR-8; no next package remains in this feature.
These source changes are not committed, merged or deployed.

## Package PTR-0: Select the representation and measurable topic policy

### Entry and scope

- **Objective and non-goals:** Produce reproducible evidence for the embedding
  representation, per-question scope, cohesion/separation/stability policy,
  representative prompt bound, and topic-equivalence rubric. Do not change
  runtime behaviour, persist experimental vectors in application tables, or
  tune solely to run 2.
- **Dependency outputs verified:** Current architecture/contracts, ADR-0001,
  ADR-0002, ADR-0003, frozen selector semantics, and the existing
  `taxonomy_experiment.py` evaluation owner.
- **Expected modules/files and owners:** Evaluation fixtures/scripts under the
  existing experiment/test owners; ADR-0003 and this plan for the resulting
  decision; no production writer.
- **Applicable AC IDs / decisions:** AC-02, AC-03, AC-07, AC-08, AC-09;
  ADR-0001–0003.
- **Baseline rechecked on / drift discovered / resolution:** Rechecked
  2026-09-29 at `8b3910acdf88bddb87e4f10a41819c6bfad595b6` with the pre-existing
  documentation edits listed in the calibration record. No production drift;
  the stopped local database was restarted for read-only aggregate analysis.

### Local contract

- **Inputs and outputs:** Use privacy-safe synthetic/approved fixtures plus
  bounded aggregate analysis of representative installed data. Compare current
  contextual vectors with answer-focused alternatives; output a versioned
  representation definition, question-scope rule, metric definitions,
  calibrated thresholds, topic semantics, prompt serialized-size bound, and
  reconciliation rubric.
- **Invariants and transaction boundaries:** No application DB mutation; no raw
  evidence committed; deterministic dataset/config hashes identify results.
- **State transitions, leases, idempotency and concurrency:** Not applicable:
  offline evaluation only.
- **Authorization, private/public data exposure:** Treat evidence as protected;
  reports contain aggregate metrics and synthetic examples only.
- **Failure/retry/recovery and rollout:** An inconclusive evaluation keeps PTR-1
  blocked with the exact missing corpus/decision; it does not choose a default.
- **Compatibility and downstream package impacts:** Outputs become explicit
  inputs to PTR-1 through PTR-4 and may refine ADR-0003 without changing current
  runtime references.

### Work and acceptance

- [x] PTR-0-A1/A2: Compare representations on multiple question types,
  including terse answers, repeated questions, synonyms, opposing positions,
  and cross-question equivalent concepts.
- [x] PTR-0-A3: Define and calibrate cohesion, separation, membership, and
  stability metrics; demonstrate why each rejects a known bad cluster without
  hiding supported small clusters.
- [x] PTR-0-A4: Define when two topic labels represent the same concept and
  document same-concept versus merely-related examples, including opposing views.
- [x] PTR-0-A5: Measure <=40/all and 30-central+10-diverse coverage and select a
  deterministic serialized-input bound compatible with configured models and
  full audit reconstruction.
- [x] PTR-0-A6: Record the selected policy/version and update downstream package
  inputs; do not mark ready while a required product decision is unresolved.

| Acceptance ID | Observable condition (including relevant failure case) | Verification command/test | Result / date / environment / revision or dirty-tree context |
| --- | --- | --- | --- |
| PTR-0-A1 | Evaluation separates identical-question/different-concept answers while retaining contextual meaning for terse answers | Focused experiment command recorded with dataset/config hashes | Passed 2026-09-29: 24-item fixture and 38-item installed aggregate; contextual per-question policy selected; hashes in calibration record |
| PTR-0-A2 | Equivalent concepts across different questions remain reconcilable | Synthetic/approved cross-question fixture report | Passed 2026-09-29: equivalent fixture centroids remained shortlistable at 0.779 and 0.844 while identical terse text became question-specific |
| PTR-0-A3 | Versioned metrics and thresholds distinguish cohesion and separation and include sensitivity analysis | Focused pure evaluation tests/report | Passed 2026-09-29: `partial-topic-policy/v1`; 11 focused tests plus sensitivity table in calibration record |
| PTR-0-A4 | Reconciliation rules distinguish the same concept, opposing views about that concept, and broader related concepts | Reviewed ADR examples and deterministic rubric fixtures | Passed 2026-09-29: executable equivalent/related/distinct rubric and ADR-0003 update |
| PTR-0-A5 | Evidence packet selection covers all <=40 cases, 30+10 cases, duplicate originals, and prompt-bound exhaustion | Pure selection/budget experiment tests | Passed 2026-09-29: deterministic packet tests cover all four cases; 32,768-byte evidence bound selected |
| PTR-0-A6 | ADR/plan contain concrete outputs sufficient for PTR-1 entry | `git diff --check` and documentation link review | Passed 2026-09-29: ADR, calibration record, package inputs and links reviewed; `git diff --check` passed |

### Documentation and handoff

- **References to update:** ADR-0003 and this plan only; runtime references wait
  for implementation.
- **Delivered behaviour and interface changes:** No runtime change. Added the
  privacy-safe fixture and offline metrics, packet selector, rubric, and fixture
  embedding command under the existing experiment owner.
- **Tests passed/failed/skipped and unverified criteria:** `cd backend &&
  UV_CACHE_DIR=/tmp/triage-uv-cache uv run python -m unittest
  tests.test_taxonomy_experiment -v` passed 11 tests. The full backend command
  `UV_CACHE_DIR=/tmp/triage-uv-cache uv run python -m unittest discover -s
  tests -v` passed 224 tests with 52 environment-dependent PostgreSQL/public
  edge skips. No external labelled corpus was available; installed results are
  aggregate geometry evidence only.
- **Decisions/drift and unresolved risks:** The calibration record owns exact
  sensitivity and limits. Recalibrate for any model or representation change.
- **Next package and concrete inputs:** PTR-1 receives the selected
  representation, metric formulae, thresholds, scope rule, and prompt bound.
- **Completion reconciliation:** Complete 2026-09-29. All six outputs agree;
  PTR-1 inputs are concrete and no unresolved product decision remains.

## Package PTR-1: Produce coherent clusters and bounded evidence packets

### Entry and scope

- **Objective and non-goals:** Implement the selected contextual-vector,
  immutable-question-scoped clustering policy; persist calibrated diagnostics; and
  select every member up to 40 or deterministic 30 central plus 10 diverse.
  Require immutable question context for every input while preserving the
  eligibility boundary that prevents ineligible input from being embedded. Do
  not call the topic LLM or change publication. Remove the current rule that
  rejects a split answer merely because a resulting part begins with a word
  such as `because`, `that`, or `which`. Do not add code that tries to judge
  whether segments overlap in meaning, omit meaning, or keep a qualifier with
  the right statement; the eligibility/segmentation LLM owns those language
  decisions.
- **Dependency outputs verified:** PTR-0 `partial-topic-policy/v1`: existing
  `question-answer` representation; per-question scope; HDBSCAN 2/1; cohesion
  0.95, separation 0.08, membership p10 0.60, persistence 0.05; and a
  32,768-byte serialized evidence-object bound.
- **Expected modules/files and owners:** `workers/eligibility_segmentation.py`,
  `workers/embeddings.py`, `job_queue.py`,
  `taxonomy_snapshots.py`, `taxonomy_automation.py`, `taxonomy_clustering.py`,
  input schemas/routes, configuration/Compose, a required-question migration,
  migrations if vector identity changes, and clustering/snapshot tests.
- **Applicable AC IDs / decisions:** AC-01, AC-02, AC-04, AC-08, AC-09;
  ADR-0001–0003.
- **Baseline rechecked on / drift discovered / resolution:** Rechecked
  2026-09-29 at `8b3910acdf88bddb87e4f10a41819c6bfad595b6` with the existing
  PTR-0 dirty-tree changes recorded in its handoff. The selected representation
  is already produced, so no vector backfill is required. Drift found: current
  clustering is run-wide with 3+1 representatives, question context remains
  optional at API/database boundaries, and evidence workers hold the input-row
  transaction over the model call and persist before queue ownership is
  confirmed. PTR-1 will correct those gaps through the existing owners.

### Local contract

- **Inputs and outputs:** Every new input carries immutable question context.
  Ineligible input stops before embedding. The original answer, ordered
  segments, model/prompt identity and model decision remain linked so a reviewer
  can trace a questionable segment back to its source. Frozen eligible
  canonical evidence plus selected versioned vectors produces per-question
  cluster candidates, evidence without a usable cluster, member probabilities,
  centroid, cohesion/separation/stability diagnostics, eligibility decision,
  and ordered evidence packet metadata.
- **Invariants and transaction boundaries:** One representation/model/dimension
  per run; no silent vector mixing; cluster plan and diagnostics commit under
  the existing stage lease; every selected representative belongs to the
  cluster and is reconstructable from immutable evidence.
- **State transitions, leases, idempotency and concurrency:** Preserve the
  clustering stage's claim/lease/replay rules. A reclaimed committed plan is a
  no-op. A failing geometry policy produces a durable unresolved outcome, not a
  model call. Preserve `new → ineligible` and `new → ready_for_embedding →
  ready_for_analysis`; these are evidence-processing states, not taxonomy
  classifications. Eligibility and embedding workers claim work in a short
  database operation, call the model without holding the input row locked, and
  confirm the same job ownership before saving in a new short transaction.
- **Authorization, private/public data exposure:** Raw evidence remains internal
  to the model packet and protected review; routine diagnostics are aggregate.
- **Failure/retry/recovery and rollout:** Topic-labelling model transport is not
  involved; eligibility/segmentation and embedding model calls retain their
  existing bounded retry policy. Representation migration/backfill must be
  retryable and retain current embeddings until the new candidate is verified.
  Audit existing questionless rows before making `question_id` non-null;
  unresolved rows block deployment and must not receive invented question text.
  A structurally invalid model response may be retried, but code does not reject
  a well-formed segmentation by attempting to judge its linguistic quality. A
  worker that no longer owns its job cannot save, delete, or replace segments
  or embeddings.
- **Compatibility and downstream package impacts:** PTR-2 consumes only
  eligible clusters and their ordered packets. Existing frozen runs remain
  readable and immutable.

### Work and acceptance

- [x] PTR-1-A1–A3: Implement/version representation production, storage,
  admission, snapshot provenance, backfill/upgrade, and mismatch rejection.
- [x] PTR-1-A4/A5: Implement per-question clustering plus calibrated cohesion,
  separation, membership and stability diagnostics with deterministic failure.
- [x] PTR-1-A6: Implement all<=40 or 30 central + 10 iterative farthest-first
  diverse selection, original-input deduplication, and prompt bound.
- [x] PTR-1-A7: Persist and replay the complete plan atomically under leases.
- [x] PTR-1-A8: Require question context at the API and database boundaries;
  audit existing rows; preserve eligibility and embedding lifecycle states.
- [x] PTR-1-A9: Keep each ordered segment and model decision traceable to the
  unchanged original answer. Limit code checks to response structure, non-empty
  values and valid source links; do not add overlap, omission, qualifier,
  ordering or grammar-based judgments.
- [x] PTR-1-A10: Claim the job and read its input in a short transaction, call
  the language or embedding model after releasing database locks, then confirm
  that the same worker still owns the job before saving all results and the job
  outcome together.

| Acceptance ID | Observable condition (including relevant failure case) | Verification command/test | Result / date / environment / revision or dirty-tree context |
| --- | --- | --- | --- |
| PTR-1-A1 | The selected existing contextual representation is generated once per canonical target with immutable provenance | Focused worker/PostgreSQL tests | Passed 2026-09-30: worker unit tests and disposable PostgreSQL evidence-worker tests; the complete Compose suite passed 231 tests. |
| PTR-1-A2 | Admission and snapshot reject missing/incompatible vectors without partial membership | PostgreSQL+pgvector integration tests | Passed 2026-09-30: pgvector admission, incompatible representation/model/dimension, and rollback cases passed in the disposable Compose suite. |
| PTR-1-A3 | Fresh install and populated upgrade preserve prior vectors/runs and require no representation backfill | Disposable Compose migration tests | Passed 2026-09-30: fresh initialization plus `test_044_upgrades_resolved_rows_and_links_historical_segments`, migration replay, and prior migration regressions passed. |
| PTR-1-A4 | Same-question distinct concepts split on calibrated fixtures; terse contextual answers remain interpretable | Pure clustering fixtures | Passed 2026-09-30: question-scope, HDBSCAN 2/1, contextual, geometry, and real-clusterer tests passed in the 231-test Compose suite. |
| PTR-1-A5 | Cohesion/separation/stability failures are durable, bounded, and make no topic-model request | Scheduler/PostgreSQL tests | Passed 2026-09-30: failed-geometry, eligible-only naming, durable-plan, and full scheduler-lifecycle tests passed. |
| PTR-1-A6 | <=40 selects all; >40 selects deterministic 30 central and up to 10 farthest-first diverse within the size bound | Pure representative-selection tests | Passed 2026-09-30: <=40, 45-member 30+10, duplicate-original, and bound-exhaustion cases passed. |
| PTR-1-A7 | Crash replay and stale lease cannot duplicate or overwrite a committed plan | PostgreSQL lease/replay tests | Passed 2026-09-30: committed-plan replay, exclusive/reclaimable leases, reused-owner stale attempt, and owner-bound completion passed against PostgreSQL. |
| PTR-1-A8 | Every stored input has immutable question context; ineligible input receives no embedding; migration fails closed on unresolved historical rows | API, worker and populated-upgrade PostgreSQL tests | Passed 2026-09-30: API/worker cases and `test_044_fails_closed_when_historical_inputs_have_no_question` passed without mutating the failed-upgrade fixture. |
| PTR-1-A9 | Every segment is ordered and linked to its unchanged original answer plus the model/prompt decision; only malformed data or broken links are rejected by code, and no overlap, omission, qualifier, wording or first-word rule judges its meaning | Segmentation traceability and worker tests | Passed 2026-09-30: `because`-prefixed acceptance, ordered decision persistence, migration backfill links, FK integrity, and immutability cases passed. |
| PTR-1-A10 | A slow model call holds no input-row lock or open transaction; only the worker that still owns the job can save segments/embeddings and complete it, and retry creates no duplicate result | PostgreSQL worker ownership/concurrency tests | Passed 2026-09-30: both focused PostgreSQL model-call tests proved row-lock release, stale-owner rejection, atomic completion, and single-result retry. |

### Documentation and handoff

- **References to update:** Architecture, API, operations, root README and
  AC-02/04/06/08 for the required-question and representation boundaries.
- **Delivered behaviour and interface changes:** Current working tree requires
  input question context, writes only `question-answer` vectors for new
  evidence, records immutable preparation decisions, commits worker results
  with their owned queue completion, and adds migration 044 plus
  `partial-topic-policy/v1` question-scoped diagnostics and packet metadata.
- **Tests passed/failed/skipped and unverified criteria:** `docker compose -f
  compose.test.yaml up --build --abort-on-container-exit --exit-code-from
  tests` passed all 231 tests on 2026-09-30 with PostgreSQL, pgvector, migrations,
  API, and public edge available. The focused worker/migration command passed
  12 tests, the dashboard PostgreSQL module passed 42 tests, and admin
  `npm test`, `npm run typecheck`, and `npm run build` passed (9 frontend tests).
  No PTR-1 criterion remains unverified.
- **Decisions/drift and unresolved risks:** Disposable verification exposed
  pre-044 integration fixtures without required question/preparation provenance;
  those fixtures now use the same boundary as production. Model-specific
  threshold drift remains a monitored policy risk, not incomplete PTR-1 scope.
- **Next package and concrete inputs:** PTR-2 receives eligible cluster IDs,
  immutable membership, calibrated diagnostics, and ordered bounded evidence
  packets. Fresh and populated database evidence confirms those inputs.
- **Completion reconciliation:** Complete 2026-09-30. All objective, work, and
  PTR-1-A1–A10 bullets have repository implementation and boundary evidence.

## Package PTR-2: Create structurally valid provisional topics

### Entry and scope

- **Objective and non-goals:** Let the structured LLM name coherent clusters
  from the full bounded packet and validate only response format, evidence
  links, and traceability. Do not
  perform cross-question merges, infer themes, or publish.
- **Dependency outputs verified:** PTR-1 eligible cluster and packet contracts;
  PTR-0 topic semantics and prompt bound.
- **Expected modules/files and owners:** `taxonomy_topics.py`,
  `clients/llm.py` only if transport bounds need extension, model audit tables,
  topic schemas/migrations if provisional identity must be separated from
  canonical revisions, and focused tests.
- **Applicable AC IDs / decisions:** AC-01, AC-02, AC-04, AC-07, AC-08, AC-09;
  ADR-0003.
- **Baseline rechecked on / drift discovered / resolution:** Rechecked
  2026-09-30 at `8b3910acdf88bddb87e4f10a41819c6bfad595b6` with the pre-existing
  PTR-0/PTR-1 dirty tree recorded at session start. PTR-2 had not started:
  `taxonomy_topics.py` still used lexical overlap and materialized canonical
  revisions directly. No conflicting implementation was found.

### Local contract

- **Inputs and outputs:** One eligible cluster and its packet produce one
  immutable accepted or structurally rejected provisional naming attempt with
  versioned model/prompt/request/response provenance.
- **Invariants and database-write boundaries:** The LLM cannot add evidence or
  change membership. Validation requires JSON strings, nonblank bounded name
  and description, 1–8 name words, no exact normalized collision, and matching
  evidence links and traceability to the request. No word-overlap check is used
  to judge meaning.
- **State transitions, leases, idempotency and concurrency:** External call
  occurs outside the transaction; lease ownership is revalidated before one
  winning append. Define bounded retry for transport/invalid shape without
  replacing a committed attempt.
- **Authorization, private/public data exposure:** Prompt evidence is protected;
  logs/errors contain IDs and bounded codes only.
- **Failure/retry/recovery and rollout:** Structurally invalid output is durable
  and retryable only under the selected versioned policy. Old attempts remain
  immutable and are never relabelled in place.
- **Compatibility and downstream package impacts:** PTR-3 consumes provisional
  identities, descriptions, centroids, membership and evidence packets.

### Work and acceptance

- [x] PTR-2-A1/A2: Version the prompt and pass the complete PTR-1 packet with
  question context and explicit topic-semantics instructions.
- [x] PTR-2-A3: Remove all lexical evidence-overlap decisions; retain and test
  structural, bound, duplicate and provenance validation.
- [x] PTR-2-A4: Define durable provisional identity distinct from final
  canonical identity without rewriting old migrations.
- [x] PTR-2-A5/A6: Prove lease-safe external call persistence, bounded failures,
  retry semantics and audit reconstruction at the maximum packet size.

| Acceptance ID | Observable condition (including relevant failure case) | Verification command/test | Result / date / environment / revision or dirty-tree context |
| --- | --- | --- | --- |
| PTR-2-A1 | Model receives all members for <=40 and the exact selected bounded packet for >40 | Structured-client fixture tests | Passed 2026-09-30: PTR-1 packet order is loaded from persisted representatives and exact evidence IDs are required; full 235-test disposable suite passed |
| PTR-2-A2 | Prompt distinguishes the concept being discussed from the view expressed about it and requests no broader theme merge | Prompt/version fixture review | Passed 2026-09-30: `partial-topic-naming/v1` prompt fixture asserts neutral concept, view, theme, and exact-link instructions |
| PTR-2-A3 | Synonyms and inflections are not rejected by code; malformed/blank/oversized/duplicate output is rejected | Pure validator tests | Passed 2026-09-30: `tests.test_taxonomy_topics` in the 235-test suite; no lexical evidence comparison remains |
| PTR-2-A4 | Accepted/rejected provisional attempts and source clusters remain immutable and independently auditable | PostgreSQL tests | Passed 2026-09-30: migration 045 plus `test_provisional_topics_postgres`; accepted and rejected attempts, model request/response, source cluster, and separate provisional identity verified |
| PTR-2-A5 | Stale worker cannot store a response; replay does not duplicate a committed attempt | PostgreSQL lease/concurrency tests | Passed 2026-09-30: model call held no run lock, replaced owner stored no response/attempt/topic, and replay made no second call |
| PTR-2-A6 | Maximum packet audit can be reconstructed or hash-verified without leaking evidence to logs | Audit-bound tests | Passed 2026-09-30: 40-item oversized audit fixture remained <=32,768 bytes and retained original byte count/SHA-256; full suite passed |

### Documentation and handoff

- **References to update:** Updated current state, root README, API, operations,
  AC-04, and this plan for the prompt, audit, migration, and handoff contracts.
- **Delivered behaviour and interface changes:** Migration 045 adds immutable
  `taxonomy_provisional_topics`, distinct from canonical `topic_revisions` and
  linked to an accepted attempt plus its source cluster. Naming now uses
  `partial-topic-naming/v1`, exact ordered packet IDs, stable validation codes,
  and `at-most-two-structural-attempts/v1`. Model transport remains outside the
  transaction; response, attempt, and provisional topic commit together only
  for the current lease owner. Scheduler health requires migrations 044/045.
- **Tests passed/failed/skipped and unverified criteria:** `docker compose -f
  compose.test.yaml run --rm tests python -m unittest discover -s tests -v`
  passed 235 tests on 2026-09-30 against disposable PostgreSQL, including fresh
  initialization, populated migration 045 upgrade, public edge, provisional
  immutability, replay, and stale-lease checks. The focused five-test
  PostgreSQL command for PTR-2 also passed. Deterministic structured responses
  were used; live-model semantic quality remains lifecycle acceptance work.
- **Decisions/drift and unresolved risks:** The structural retry policy permits
  one retry after an invalid shape and never replaces a committed attempt.
  Model quality is evaluated at the lifecycle level; structural validation
  does not claim semantic proof. PTR-2 intentionally creates no canonical
  revision, theme, attestation, or publication.
- **Next package and concrete inputs:** PTR-3 receives immutable provisional
  topics plus their cluster geometry, questions, memberships and bounded
  evidence.
- **Completion reconciliation:** Complete. All objective, work, output,
  immutability, retry, lease, audit, documentation, and acceptance items have
  evidence. PTR-3 assumptions were checked against migration 045 and the
  scheduler integration test.

## Package PTR-3: Reconcile equivalent topics across questions

### Entry and scope

- **Objective and non-goals:** Produce canonical topic identities by merging
  equivalent provisional topics across question scopes. Do not merge merely
  related concepts or infer themes.
- **Dependency outputs verified:** PTR-0 equivalence rubric; PTR-2 provisional
  identities, labels, geometry and evidence.
- **Expected modules/files and owners:** New topic reconciliation module beside
  `taxonomy_reconciliation.py`, scheduler/stage owner, numbered migration for
  antecedents/decisions/canonical membership, topic lineage/identity functions,
  and tests.
- **Applicable AC IDs / decisions:** AC-01–AC-04, AC-07–AC-09; ADR-0001 and
  ADR-0003.
- **Baseline rechecked on / drift discovered / resolution:** Rechecked
  2026-10-08 at `8b3910acdf88bddb87e4f10a41819c6bfad595b6` with the existing
  dirty tree recorded above. Migration 045 and provisional inputs match the
  contract. Unfinished PTR-3 source/migration/tests and later-package changes
  already existed. Preserved them; completed PTR-3 verification and corrected
  compact wire serialization, a losing-worker invalid-response race, and the
  contradictory-partition fixture's duplicate source evidence. No new product
  decision or departure from ADR-0003.

### Local contract

- **Inputs and outputs:** Deterministic similarity shortlisting creates bounded
  neighborhoods. Structured LLM decisions produce non-overlapping equivalence
  groups or explicit no-merge decisions. Backend creates canonical topics,
  immutable antecedent links, decision rationale/provenance, and the set union
  of evidence memberships.
- **Invariants and transaction boundaries:** A provisional topic belongs to at
  most one canonical topic; every canonical topic has at least one antecedent;
  every canonical membership derives from an antecedent membership; no evidence
  text or ID is invented; topic name uniqueness holds; related-only topics stay
  separate. Canonicalization and its membership union commit atomically.
- **State transitions, leases, idempotency and concurrency:** Add one durable
  `topic_reconciliation` stage to the existing run-stage lifecycle. Model calls
  occur outside transactions; persist only after lease validation. Replays use
  versioned request keys and cannot create a second partition.
- **Authorization, private/public data exposure:** Protected candidate review
  may expose decisions and evidence IDs; routine/public responses do not expose
  prompts or raw evidence.
- **Failure/retry/recovery and rollout:** Invalid overlapping, missing, or
  transitive-inconsistent groups fail boundedly without partial canonical
  writes. Retry preserves frozen provisional inputs.
- **Compatibility and downstream package impacts:** PTR-4 theme inference and
  quality consume canonical topics only. Historical topic revisions remain
  immutable; migration defines compatibility explicitly.

### Work and acceptance

- [x] PTR-3-A1/A2: Implement deterministic candidate shortlisting and bounded
  reconciliation packets; avoid global all-pairs LLM work.
- [x] PTR-3-A3/A4: Define structured equivalence/no-merge response and validate
  complete non-overlapping canonical partition plus canonical label shape.
- [x] PTR-3-A5/A6: Persist canonical identity, antecedents, rationale and exact
  unioned memberships atomically; preserve question/evidence provenance.
- [x] PTR-3-A7/A8: Integrate durable stage, replay/concurrency/recovery, stable
  identity/lineage, and scale fixtures across at least 50 question scopes.

| Acceptance ID | Observable condition (including relevant failure case) | Verification command/test | Result / date / environment / revision or dirty-tree context |
| --- | --- | --- | --- |
| PTR-3-A1 | Only geometrically/name-plausible neighbors enter an LLM packet; isolated topics bypass model comparison | Pure shortlist tests | Passed 2026-10-08: shortlist/isolated tests in P1/P2; isolated PostgreSQL fixture in P3 |
| PTR-3-A2 | Packet size/candidate count is bounded and deterministic for hundreds of provisional topics | Scale-focused pure tests | Passed 2026-10-08: deterministic 300-topic fixture, 12-topic/32,768-byte bounds in P1/P2; 50 question scopes and 100 evidence items in P3 |
| PTR-3-A3 | Equivalent cross-question fixtures merge; related, homonymous and opposing-position fixtures obey the PTR-0 rubric | Structured-client fixture tests | Passed 2026-10-08: real structured-client MockTransport fixture merges childcare synonyms/opposing parking positions; keeps related bus concepts and bank homonyms distinct (P3) |
| PTR-3-A4 | Overlapping, unknown, duplicate or incomplete model groups are rejected without writes | PostgreSQL rollback tests | Passed 2026-10-08: unknown/missing/duplicate/overlapping IDs, label collisions, transitive contradiction and injected late-write rollback leave zero canonical writes (P3) |
| PTR-3-A5 | A merged topic contains every linked evidence item once and contains no evidence from outside this taxonomy candidate | PostgreSQL consistency tests | Passed 2026-10-08: exact four-item union, foreign-run and unlinked same-run evidence rejected; antecedents immutable (P3, migration 046) |
| PTR-3-A6 | Evidence, distinct-submission and question counts remain separately derivable after merge | PostgreSQL aggregate tests | Passed 2026-10-08: four evidence items, two questions, two source/form-scoped submissions, derived separately (P3) |
| PTR-3-A7 | Crash replay, stale lease and concurrent worker cannot create a second partition or identity | PostgreSQL concurrency tests | Passed 2026-10-08: crash/transport replay, three-attempt bound, stale lease with unlocked model call, two concurrent writers and losing invalid response; stage blocks themes until complete (P3) |
| PTR-3-A8 | New and replacement runs retain stable topic lineage or record explicit split/merge/new relationships | PostgreSQL replacement tests | Passed 2026-10-08: replacement identity reuse, split, merge, rename, continuation, new lineage and unchanged historical revision (P3); populated history preserved (P4) |

### Documentation and handoff

- **Delivered behaviour and interfaces:** Migration 046 adds
  `taxonomy_topic_reconciliation_decisions` and
  `taxonomy_canonical_topic_antecedents`, immutable run-scoped provenance,
  canonical membership-source guards, and the new leased stage. Snapshot and
  scheduler include it before themes; `init.sql` includes its marker and
  scheduler readiness requires it. `cross-question-topic-reconciliation/v1`
  uses cosine >=0.82 or name-term similarity >=0.50 to shortlist, not merge;
  at most 12 topics/one per question and two whole answers per topic fit a
  32,768-byte compact UTF-8 packet. Metadata overflow fails closed. Canonical
  revisions, representatives, exact evidence union and lineage commit together.
  Transport retries have at most three durable requests; committed structural
  rejection is immutable. Replays consume accepted decisions.
- **Evidence context:** All commands below ran on 2026-10-08 against HEAD
  `8b3910acdf88bddb87e4f10a41819c6bfad595b6` plus the preserved dirty tree and
  this session's changes. P1/P2 use the local backend environment. P3/P4 use
  disposable PostgreSQL 17 + pgvector via `compose.test.yaml`; no required
  test skipped. The test stack was removed with
  `docker compose -f compose.test.yaml down` and freshly built/started using
  `docker compose -f compose.test.yaml up -d --build postgres api public-web`.
  Fresh initialization succeeded with all included schema/migration markers;
  P3 fixtures additionally create fresh isolated schemas from `init.sql`.
- **P1:** From `backend/`,
  `env UV_CACHE_DIR=/tmp/triage-uv-cache uv run python -m unittest discover -s tests -p 'test_taxonomy_topic_reconciliation.py' -v`
  — 12 passed, no skips.
- **P2:** From `backend/`,
  `env UV_CACHE_DIR=/tmp/triage-uv-cache uv run python -m unittest discover -s tests -p 'test_taxonomy*.py' -k reconciliation -k scheduler -k stages -v`
  — 38 passed, no skips, including P1 and existing stage/scheduler owners.
- **P3:** From repository root,
  `docker compose -f compose.test.yaml run --rm tests python -m unittest discover -s tests/integration -p test_topic_reconciliation_postgres.py -v`
  — final run 16 passed, no skips. Initial run: 14 passed and one fixture error
  from duplicate snapshot evidence; corrected with a third question and unique
  sources, then reran the entire file. Added the concurrent losing-response
  regression and compact wire-size assertion before the final passing run.
- **P4:** From repository root,
  `docker compose -f compose.test.yaml run --rm tests python -m unittest discover -s tests/integration -p test_migration_upgrade_postgres.py -k 046 -v`
  — one passed, no skips. Upgrade from populated 045 retains the published run
  and historical revision byte-for-byte and creates pending/completed stages
  appropriately without inventing antecedents.
- **Restart revalidation, 2026-10-09:** Rechecked the same HEAD with the
  preserved dirty tree, including subsequent PTR-4 completion and PTR-5 work.
  From repository root,
  `docker compose -f compose.test.yaml run --rm tests python -m unittest tests.test_taxonomy_topic_reconciliation tests.integration.test_topic_reconciliation_postgres tests.integration.test_migration_upgrade_postgres.MigrationUpgradePostgresTests.test_046_upgrades_populated_runs_without_rewriting_canonical_history -v`
  passed all 29 tests with no skips on disposable PostgreSQL 17 + pgvector.
  This rerun verifies the current PTR-3 boundary against later changes;
  it does not replace the dated fresh-initialization evidence above or close
  later packages. `git diff --check` passed and the active-plan check returned
  only `docs/work-packages.md`. PTR-3 remains complete; current pipeline
  status remains PTR-5 in progress.
- **Broader checks and downstream work:**
  `env UV_CACHE_DIR=/tmp/triage-uv-cache uv run python -m unittest discover -s tests -p 'test_taxonomy*.py' -v`
  from `backend/` ran 78 tests: 74 passed, three failures and one error.
  Pre-existing PTR-4 changes require updating/verifying
  `test_taxonomy_quality.py` (three old gate-v2 expectations) and
  `test_taxonomy_themes.py::test_subset_and_overlap` (old neighborhood shape).
  The whole migration file command (P4 without `-k 046`) ran 12 tests:
  11 passed and one failed in
  `test_first_publication_is_gate_bound_and_records_an_immutable_decision`,
  whose gate-v2 fixture/error expectation conflicts with unfinished migration
  048. PTR-5 owns that correction. These checks are not claimed green; the
  scoped PTR-3 boundary has no failing or skipped acceptance criterion.
- **Documentation checks:** `git diff --check` passed;
  `rg --files docs -g '*work*package*.md' -g '!**/archive/**' -g '!**/templates/**' -g '!**/reviews/**'`
  returned only `docs/work-packages.md`. A Python path-existence check of all
  relative Markdown links in changed documents checked 49 targets and passed.
  Reviewed pipeline, package criteria and references for consistent PTR-3
  completion/PTR-4 readiness.
- **References updated:** Documentation guide, architecture, current state,
  AC-02/03/04, operations, root README and ADR-0003. Existing API/admin edits
  are preserved; PTR-6 still owns acceptance of protected review presentation.
- **Risks and decisions:** Structural fixtures prove the equivalence protocol,
  not the accuracy of a live model. No live semantic evaluation or deployment
  was performed. Under/over-merging still needs PTR-8 journey/model evidence.
  Related-topic theme inference remains PTR-4. Broad regressions above must
  be resolved before feature closure or deployment.
- **Next package / concrete inputs:** PTR-4 is ready with canonical
  `topic_revisions`, `topic_memberships`, representative evidence,
  antecedents/decisions and `topic_lineage`; its theme reader already queries
  canonical revisions. Verify optional themes, exact coverage attestation and
  quality failure cases, including the existing 047 edits. PTR-5 receives
  that verified attestation and must revalidate 048/API contracts together.
- **Completion reconciliation:** Objective and all four work bullets plus
  PTR-3-A1–A8 have evidence above. Implemented and verified in this dirty
  checkout; not merged or deployed. PTR-4–PTR-8 retain their own acceptance
  obligations; the feature and current plan remain open.

## Package PTR-4: Infer optional themes and attest truthful coverage

### Entry and scope

- **Objective and non-goals:** Infer/reconcile broader themes from canonical
  topics and replace release-gate v2 with a versioned attestation that permits
  useful partial coverage. Do not publish or change readers yet.
- **Dependency outputs verified:** PTR-3 canonical topics/memberships/lineage;
  PTR-0 publication metric policy.
- **Expected modules/files and owners:** `taxonomy_themes.py`,
  `taxonomy_reconciliation.py`, `taxonomy_stage_quality.py`, scheduler stage
  order, theme materialization SQL in a new migration, and tests.
- **Applicable AC IDs / decisions:** AC-02–AC-04, AC-07–AC-09; ADR-0003.
- **Baseline rechecked on / drift discovered / resolution:** Rechecked
  2026-10-08 at HEAD `8b3910acdf88bddb87e4f10a41819c6bfad595b6` plus
  the recorded dirty tree, including the interrupted/resumed PTR-4 work.
  PTR-3 outputs and stage order match. Extended the existing owners and
  unfinished 047; moved optional materialization from untracked 048 into 047
  so the PTR-4 output exists before the publication package. Tightened exact
  audit matching and protected diagnostics; corrected the existing empty-token
  authentication bug through `api/security.py` under AC-07. No new decision
  beyond accepted ADR-0003; later-package changes remain preserved.

### Local contract

- **Inputs and outputs:** Canonical topics feed theme inference; zero or more
  reconciled themes result. The system writes one immutable publication-check
  record containing a consistency result plus total evidence, evidence with a
  canonical topic, evidence without a canonical topic, valid/rejected topic,
  theme, question and distinct-submission counts, thresholds, failures, policy
  version and input hash. Rejected topic attempts remain reviewable but do not
  prevent unrelated valid topics from passing the publication check.
- **Invariants and database-write boundaries:** Themes link only canonical topics;
  no theme is not a failure. Each frozen evidence item contributes exactly once
  to either with-topic or without-topic coverage. Internal cluster outcomes may
  explain missing membership but are not extra coverage categories or input
  states. Attestation remains computed-only and immutable.
- **State transitions, leases, idempotency and concurrency:** Existing theme and
  quality leases apply. Retry cannot replace theme decisions or attestation.
- **Authorization, private/public data exposure:** Aggregate attestation is
  protected operational data; no raw evidence or prompts in public errors.
- **Failure/retry/recovery and rollout:** Unfinished processing or internally
  contradictory stored data cannot publish. A rejected topic attempt or
  evidence without a topic produces an attested partial result rather than
  blocking valid topics.
- **Compatibility and downstream package impacts:** PTR-5 database publication
  consumes the new attestation version. Old attestations remain valid history
  but cannot satisfy the new automatic policy.

### Work and acceptance

- [x] PTR-4-A1–A3: Move theme inputs to canonical topics, preserve
  related-not-equivalent semantics, and make zero-theme materialization valid.
- [x] PTR-4-A4–A6: Define run-level coverage counts, implement immutable gate
  v3 input/hash, and remove coverage percentage, 0.80 accepted-attempt, and
  minimum-theme conditions as publication blockers.
- [x] PTR-4-A7/A8: Verify partial coverage, full coverage and inconsistent-data
  results,
  retries, immutability, privacy, and compatibility.

| Acceptance ID | Observable condition (including relevant failure case) | Verification command/test | Result / date / environment / revision or dirty-tree context |
| --- | --- | --- | --- |
| PTR-4-A1 | Theme inference sees canonical topics and their bounded evidence, never duplicate provisional antecedents | Structured-client and PostgreSQL tests | Passed 2026-10-08: Q2 structured-client packet contains only canonical revisions and their canonical representative evidence; Q1 verifies deterministic bounds |
| PTR-4-A2 | Related topics can share a theme without being merged; equivalent topics appear once | Deterministic fixture tests | Passed 2026-10-08: Q2 merges two provisional antecedents once before a two-topic broader theme; related canonical topics remain distinct |
| PTR-4-A3 | One canonical topic or no related topic groups yields zero themes without publication failure | Pure and PostgreSQL tests | Passed 2026-10-08: Q1 isolated neighborhoods; Q2 single-topic/no-theme replay and zero-theme materialization; Q3 verifies materialization after 047 without 048 |
| PTR-4-A4 | Total evidence = evidence with a canonical topic + evidence without a canonical topic, with every frozen item counted once | Pure/PostgreSQL aggregate tests | Passed 2026-10-08: Q1 arithmetic/negative/missing count failures; Q2 full 4=4+0 and partial 50=4+46 coverage |
| PTR-4-A5 | Distinct submissions and questions are reported separately from evidence count | PostgreSQL tests | Passed 2026-10-08: Q2 reports 50 evidence items, two questions and two source/form-scoped known submissions separately |
| PTR-4-A6 | At least one valid canonical topic can pass publication checks regardless of the topic-coverage percentage, the number of rejected topic attempts, or the absence of a theme; rejected attempts remain recorded for review | Publication-check tests | Passed 2026-10-08: Q2 8% evidence coverage, two accepted and 20 rejected naming attempts, zero themes pass; all rejected attempts remain stored |
| PTR-4-A7 | Publication stops if processing is unfinished, a topic links to evidence outside this candidate, a required trace record is absent, or coverage counts do not add up | Failure/rollback tests | Passed 2026-10-08: Q2 unfinished stage, absent antecedent, exact audit context mismatch and foreign membership corruption fail; insertion guards also reject foreign evidence; Q1 inconsistent coverage fails |
| PTR-4-A8 | One immutable attestation survives retry and exposes only bounded aggregate diagnostics | PostgreSQL immutability/API tests | Passed 2026-10-08: Q2 concurrent/repeated quality, immutable row/hash, stale claims, protected API and empty/wrong/unconfigured credentials; Q3 preserves old version/result; no raw model/evidence payloads in diagnostics |

### Documentation and handoff

- **Delivered behaviour and interfaces:** Themes consume canonical
  `topic_revisions` and their membership-checked representatives under
  `partial-theme-inference/v1`. Deterministic two-to-five-topic neighborhoods
  include each anchor, deduplicate equivalent packets and supply at most two
  whole answers per topic within 32,768 compact UTF-8 JSON bytes. Created
  themes select at least two distinct supplied canonical IDs; one/isolated
  topics and model no-theme decisions yield zero themes. Attempts and exact
  theme reconciliation replay immutably. Automation source, `.env.example`
  and Compose prompt defaults agree.
- **Computed contract:** Migration 047 owns
  `taxonomy_publication_facts(bigint)` and optional
  `materialize_taxonomy_theme_revisions(bigint)`. It also aligns provisional
  name uniqueness with the question scope, matching the existing naming
  writer. Exact snapshot/cluster/antecedent/model/theme trace checks feed
  `taxonomy-release-gate-v3`; only at least one nonempty canonical topic and
  internal consistency are required. Evidence coverage and naming success
  rates are informational. Count meanings: total frozen items; items with any
  canonical membership; remaining items; distinct question IDs; known
  `(source, form_key, submission_key)` submissions; canonical revisions;
  accepted/rejected naming attempts; candidate/reconciled themes. Every frozen
  item belongs to exactly one of the two coverage counts. Unknown submission
  keys do not create fictitious submissions.
- **Replay/compatibility/security:** One immutable attestation binds all
  aggregate metrics, thresholds and version in its hash. Replayed quality
  returns its stored facts and preserves old gate-v2 rows. Claimed quality must
  match the run and stage; lost claims persist nothing. Model calls remain
  outside transactions and theme writes validate ownership. AC-07 correction
  prevents an absent presented token matching an unused empty token slot;
  review-only, mutation-only and unconfigured credentials are verified.
  Protected diagnostics exclude raw prompts/model output/evidence.
- **Evidence context:** All checks below ran on 2026-10-08 against HEAD
  `8b3910acdf88bddb87e4f10a41819c6bfad595b6` plus the preserved dirty tree
  and this session's changes. Q1 uses the local backend environment; Q2–Q4
  use disposable PostgreSQL 17 + pgvector. No scoped acceptance check skipped.
  Fresh test stack recreated using
  `docker compose -f compose.test.yaml down` then
  `docker compose -f compose.test.yaml up -d --build postgres api public-web`;
  all services initialized healthy with matching rebuilt API source and fresh
  `init.sql`. Each PostgreSQL fixture also expands that schema in a new isolated
  namespace. `docker compose -f compose.test.yaml config --quiet` passed.
- **Q1:** From `backend/`,
  `env UV_CACHE_DIR=/tmp/triage-uv-cache uv run python -m unittest discover -s tests -p 'test_taxonomy*.py' -v`
  — 81 passed, no skips. Replaced old gate-v2 and singleton/duplicate theme
  expectations with meaningful partial/full/failure/hash and packet tests.
- **Q2:** From repository root,
  `docker compose -f compose.test.yaml run --rm tests python -m unittest discover -s tests/integration -p test_partial_taxonomy_quality_postgres.py -v`
  — final 12 passed, no skips. Includes actual structured-client transport,
  canonical/provisional distinction, full/8%-coverage fixtures, distinct
  counts, corruption/trace failures, replay/concurrency, stale theme and quality
  claims, and protected HTTP routing via ASGI. Initial nine-case run had one
  fixture error from rewriting a terminal stage and one empty-token security
  failure. Corrected the fixture/shared auth owner, expanded the cases and
  reran the entire file. Test fixture import supports both root and isolated
  integration discovery.
- **Q3:** From repository root,
  `docker compose -f compose.test.yaml run --rm tests python -m unittest discover -s tests/integration -p test_migration_upgrade_postgres.py -k 047 -k marker -k linted -v`
  — three passed, no skips. Populated 046 upgrades to 047 while preserving an
  old gate-v2 row byte-for-byte and leaving publication function definitions
  unchanged; zero-theme materialization/replay succeeds before 048. Fresh
  migration markers/reapplication and transactional migration lint pass.
- **Q4:** From repository root,
  `docker compose -f compose.test.yaml run --rm tests python -m unittest discover -s tests/integration -p test_topic_reconciliation_postgres.py -v`
  — 16 passed, no skips on the completed PTR-4 schema and shared fixture.
- **Broader check / next work:** From `backend/`,
  `env UV_CACHE_DIR=/tmp/triage-uv-cache uv run python -m unittest discover -s tests -v`
  — final 280 tests, one failure, three errors and 90 environment-dependent
  DB/edge skips. The remaining failures are the preserved PTR-5 changes:
  three `InputApiTests` still expect removed `taxonomy_state`, and
  `test_dashboard_api.py::test_summary_returns_taxonomy_and_article_counts`
  expects the old payload. An initial run additionally found the new fixture
  import error, which was fixed before rerunning. Required PTR-4 PostgreSQL
  criteria are proved by Q2/Q3, not by local skips. PTR-3's recorded migration
  048 publication-fixture failure remains PTR-5 work; the whole migration suite
  is not claimed passing here.
- **Documentation checks:** `git diff --check` passed. The documented
  `rg --files docs -g '*work*package*.md' -g '!**/archive/**' -g '!**/templates/**' -g '!**/reviews/**'`
  command returned only `docs/work-packages.md`. Python path-existence review
  checked 49 local Markdown link targets in changed documents with none broken.
  Reviewed feature contract, pipeline, package checklist and current references
  for consistent PTR-4 completion/PTR-5 readiness.
- **References/rollout:** Architecture, AC-03/04/07, API and operations gate
  contracts, root README, documentation guide, ADR-0003 and this plan updated.
  Current-state reference receives only a source/package-status correction;
  no live publication behaviour is claimed. 047 has no deployment evidence.
  Stop the scheduler and take a backup before migrations; 048 and matching
  publication consumers require PTR-5 acceptance before enabling production.
  Failure recovery preserves the prior publication; schema rollback requires
  the backup. Older runs/attestations are never upgraded in place.
- **Risks/decisions:** Deterministic transport fixtures prove the protocol and
  durable checks, not live-model semantic accuracy. PTR-8 still owns the full
  lifecycle and model journey. No live deployment, publication or application
  data changes occurred in this package.
- **Next package / concrete inputs:** PTR-5 is ready with the shared SQL facts
  schema, one immutable gate-v3 attestation, coverage definitions, bounded
  failures and optional theme materializer. 048 now consumes the materializer
  from 047 instead of redefining it. Verify current-version gate enforcement,
  atomic publication/rollback/replay, association readers and API regressions
  with new evidence; retain historical gate-v2 attestations as history.
- **Completion reconciliation:** Objective, all three work bullets and
  PTR-4-A1–A8 are implemented and verified in this dirty checkout. Not merged
  or deployed. PTR-5–PTR-8 and feature-level integrated acceptance remain open.

## Package PTR-5: Publish partial runs and project current associations

### Entry and scope

- **Objective and non-goals:** Atomically publish one cumulative run with full
  or partial topic coverage; remove the computed input `taxonomy_state`; and make input
  topics/themes a projection of exactly one published run. Preserve evidence-
  processing, taxonomy-run, worker and editorial statuses. Do not build admin
  UI.
- **Dependency outputs verified:** PTR-4 attestation/coverage contract and
  optional themes; current rollback/publication invariants.
- **Expected modules/files and owners:** New numbered migration replacing manual
  and automatic publication functions, `taxonomy_automation.py`,
  `taxonomy_status.py`, dashboard queries/routes/schemas, inputs, operations,
  generation, article validation as needed, migration/readiness checks, tests.
- **Applicable AC IDs / decisions:** AC-01–AC-09, ADR-0001 and ADR-0003.
- **Baseline rechecked on / drift discovered / resolution:** Resumed 2026-10-08
  at `8b3910acdf88bddb87e4f10a41819c6bfad595b6`, with 52 modified and 12
  untracked files retained from PTR-0–PTR-4 and unfinished downstream work.
  Reader projections already remove `taxonomy_state`; publication fixtures still
  use historical gate versions. Revalidate these against migration 048 and
  computed v3 facts in disposable PostgreSQL. Resumed 2026-10-09 after server
  interruptions: HEAD remains unchanged and all changes are preserved. The
  completed focused runs were inspected before any rerun. Live data is untouched.

### Local contract

- **Inputs and outputs:** A ready run with a matching passing v3 attestation and
  durable automatic decision atomically supersedes the prior run and becomes
  the one publication. Run responses expose with-topic/without-topic coverage.
  Input responses retain evidence-processing `status`, the ID of the published
  taxonomy used for the response, and stable canonical topics/themes;
  association lists may be empty. These response fields are read from the
  published run's association tables; publication does not copy topics or
  themes into `original_inputs` or `segment_inputs`.
- **Invariants and transaction boundaries:** One published run; no direct status
  writes; publication decision, aliases/lineage/materialization and swap are
  atomic. The input itself stores no taxonomy classification. Every input topic
  or theme derives from the captured published run; absence of membership is an
  empty list, including for evidence outside that run. A single response never
  mixes topics or themes from different published taxonomies. Preserve the
  current behaviour that combines all segment associations under their original
  input, removes duplicates, and returns a stable order.
- **State transitions, leases, idempotency and concurrency:** Preserve current
  ready→published and published→superseded/rollback transitions, automatic
  idempotency and concurrent publication rejection.
- **Authorization, private/public data exposure:** Human mutation remains
  token-protected/default-off; automatic DB gate remains authoritative.
  Empty associations expose no raw model failure publicly.
- **Failure/retry/recovery and rollout:** Apply new migration with matching
  application images. Prior publication remains served until atomic success.
  Failed replacement remains inert; explicit rollback remains available.
- **Compatibility and downstream package impacts:** Removing `taxonomy_state`
  is an intentional API contract change. Update the Pydantic response, SQL
  projection, OpenAPI tests, TypeScript contract, documentation and every known
  consumer together. Retain `published_taxonomy_run_id` for provenance. PTR-6
  consumes the new association and coverage contracts.

### Work and acceptance

- [x] PTR-5-A1/A2: Replace DB manual/automatic publication and optional-theme
  materialization safely; preserve one-run swap/audit/rollback.
- [x] PTR-5-A3/A4: Remove input `taxonomy_state`; continue deriving deduplicated,
  stably ordered input topics/themes only from the published run; update the
  dashboard with-topic/without-topic coverage. Do not add current-taxonomy
  columns to source evidence rows.
- [x] PTR-5-A5: Update candidate/operations status so useful partial
  publication is not reported quality-blocked.
- [x] PTR-5-A6: Permit topic-targeted generation with zero themes while freezing
  run and evidence provenance.
- [x] PTR-5-A7: Verify fresh/populated upgrade, concurrency, rollback and all
  backend contracts.

| Acceptance ID | Observable condition (including relevant failure case) | Verification command/test | Result / date / environment / revision or dirty-tree context |
| --- | --- | --- | --- |
| PTR-5-A1 | Passing partial run atomically supersedes prior publication; failed/incompatible attestation cannot publish | PostgreSQL publication tests | **passed**, 2026-10-09; P1/P2/P5: computed v3 partial/manual/automatic gates and inert failures; disposable dirty checkout |
| PTR-5-A2 | Zero-theme partial run publishes; aliases/lineage/audit are complete; rollback restores prior run | PostgreSQL tests | **passed**, 2026-10-09; P1/P5: zero themes, aliases, retirement lineage, immutable audits and rollback; disposable dirty checkout |
| PTR-5-A3 | Input responses have no `taxonomy_state`; retain processing `status` and published-taxonomy ID; topics/themes are derived from that taxonomy's stored associations, not copied onto source rows; split-answer associations remain combined, deduplicated and stably ordered, with empty lists when none exist | Inputs API/PostgreSQL regression tests | **passed**, 2026-10-09; P1/P2/P5/P6: real SQL, OpenAPI, split segments and typed client contracts; disposable dirty checkout |
| PTR-5-A4 | Dashboard reports total evidence, evidence with a canonical topic, and evidence without one; the two coverage counts reconcile exactly to the run snapshot | Dashboard API/PostgreSQL tests | **passed**, 2026-10-09; P1/P2/P5: exact published snapshot total = with topic + without topic; disposable dirty checkout |
| PTR-5-A5 | Operations/candidate status distinguishes partial publication, running replacement and integrity failure with bounded codes | API tests | **passed**, 2026-10-09; P1/P2/P5: partial publication, running replacement and bounded integrity failures; disposable dirty checkout |
| PTR-5-A6 | Topic generation succeeds from canonical evidence with no theme; evidence outside the selected canonical topic is rejected | Generation worker/API tests | **passed**, 2026-10-09; P1/P5: actual API/worker, foreign evidence 422, concurrent swap and frozen topic tags; disposable dirty checkout |
| PTR-5-A7 | Fresh init, populated upgrade, concurrent swap, replay and rollback pass against disposable PostgreSQL+pgvector | Isolated Compose integration commands | **passed**, 2026-10-09; P1/P3/P4/P5: fresh/populated pg17+pgvector, competing swap/retry and replay/rollback; disposable dirty checkout |

### Verification record — 2026-10-09

All commands use HEAD `8b3910acdf88bddb87e4f10a41819c6bfad595b6` plus
preserved PTR-0–PTR-4 work and this package's uncommitted changes. PostgreSQL
uses `compose.test.yaml` project `triage-verification`, pg17+pgvector and tmpfs;
model calls are deterministic fixtures, not a live model quality claim.

- **P1:** `docker compose -f compose.test.yaml run --rm tests python -m unittest discover -s tests/integration -p test_partial_taxonomy_publication_postgres.py -v`
  — **10 passed, no skips**. Tests current failed/old/mismatched gates and
  changed facts, partial zero-theme publication, exact coverage/OpenAPI,
  immutable source rows, replacement/rollback/replay, aliases, theme retirement
  lineage, audit failure rollback, competing human/automatic swaps and retry,
  same-run concurrent replay, and topic generation during publication. The
  latter swaps after target lookup and splits the old topic before the worker
  saves: job, evidence and article topic tags keep the original run. Evidence
  outside the selected topic returns 422.
- **P2:** `docker compose -f compose.test.yaml run --rm tests python -m unittest discover -s tests/integration -p test_dashboard_postgres.py -v`
  — **42 passed, no skips**. Published-only input associations combine split
  segments, deduplicate and sort topics/themes; no source/legacy fallback.
  Coverage, bounded candidate/operations states, protected/default-off mutation,
  article/public projections and real scheduler owners pass. Older fake passing
  attestations were replaced with computed current gates; the cumulative
  scheduler fixture now executes actual clustering/naming/reconciliation/theme/
  quality/readiness owners with deterministic model responses.
- **P3:** `docker compose -f compose.test.yaml run --rm tests python -m unittest discover -s tests/integration -p test_migration_upgrade_postgres.py -v`
  — **13 passed, no skips**. Populated 048 preserves historical publication
  decisions byte-for-byte, rejects their old attestations for new publication,
  and supports explicit rollback. Fresh markers, transaction lint and no-op
  migration reapplication also pass.
- **P4:** `docker compose -f compose.test.yaml down`, then
  `docker compose -f compose.test.yaml up -d --build postgres api public-web`
  — disposable tmpfs database recreated; fresh init through 048 and rebuilt
  API/public-edge services started healthy. No application volumes were touched.
- **P5:** `docker compose -f compose.test.yaml run --rm tests python -m unittest discover -s tests -v`
  — **290 passed, no skips**, 2026-10-09, 54.100 seconds. Includes all pure,
  PostgreSQL, populated-upgrade, API, worker and real public-edge regressions.
  The earlier 288-test run also passed before the final two boundary cases.
- **P6:** `npm test` and `npm run typecheck` in `frontend/admin`
  — **9 test files passed**, build and TypeScript checks passed, no skips.
  The client fixture now expects the current bounded publication-check message.
- **P7:** `git diff --check` and a Python local Markdown-link check of changed
  reference files — **passed**: 11 changed Markdown files, 49 local targets.
  One active work-package plan; guide, current state, ADR/contracts and all
  package/feature status records agree. Final `git diff --check` is clean.

Initial focused attempts exposed fixture-only stale timestamp casts, unsupported
placeholders, wrong lease argument and an incorrect article-revision column;
those were corrected. They also exposed two real generation defects: ambiguous
text/bigint parameter typing in job insertion and topic validation against the
current publication instead of the frozen job run. Both were fixed in their
existing owners. The first local pure run passed 288 tests with 98 database/edge
skips; it is not used as integration evidence. The final Compose suite is the
boundary acceptance. No requested criterion is satisfied by a skipped DB test.

### Documentation and handoff

- **References updated:** Architecture/current-state, AC-03/04/05/06/08/09,
  ADR-0003, API, operations, root README, admin compatibility, documentation
  guide and migration/readiness markers agree on the completed backend boundary.
- **Delivered behaviour and interface changes:** Migration 048 owns the current
  gate checks and atomic swap. Its shared `lock_taxonomy_publication` rejects
  a waiting different-candidate request if publication changed, permits retry,
  and lets same-candidate delivery return the existing result. Audit, optional
  theme projection/retirement and aliases commit with the swap. Explicit rollback
  retains historical runs and records one decision per transition.
  `/inputs` removes `taxonomy_state`; `status`, required question context,
  published-run ID and sorted deduplicated topic/theme arrays remain. Empty lists
  are normal. Dashboard exact total/with/without counts and full/partial coverage
  match the published snapshot. Operations adds published-run ID, with/without
  counts and nullable full/partial coverage; existing bounded states/codes remain.
- **Decisions/drift:** Generation now uses `repeatable_read` for target/evidence/
  run capture and resolves article topic tags against that recorded run. This
  implements AC-03/05 and ADR-0003's existing frozen-generation boundary; it
  changes no editorial approval or public exposure. Historical upgrade fixtures
  now test the historical transition before 048, then preservation/rollback after
  the upgrade; new partial transitions have separate computed-v3 evidence.
- **Next package / concrete inputs:** PTR-6 receives InputResponse/OpenAPI and
  TypeScript contracts without `taxonomy_state`, stable run provenance and empty
  associations; dashboard full/partial coverage counts; protected candidate
  coverage/publication failure codes from PTR-4; operations coverage plus existing
  automation states; and proven zero-theme canonical-topic generation. No new
  admin UI was added by this package. PTR-6 must revalidate actual readers and
  use its own operator/UI evidence; PTR-7 owns broader historical-isolation
  acceptance, and PTR-8 owns the integrated real journey and rollout handoff.
- **Deployment / recovery limits:** Not merged, committed or deployed. Live
  publication and application data remain unchanged. Apply matching migration
  and images with scheduler stopped after a backup; retain prior publication on
  failure and use explicit rollback for restoration. Schema recovery uses the
  pre-upgrade backup. Deterministic models do not prove production model quality.
- **Completion reconciliation:** All five work bullets and PTR-5-A1–A7 have
  acceptance evidence. PTR-5 is implemented and verified in the preserved dirty
  checkout; PTR-6 is ready, PTR-7/PTR-8 and feature-level acceptance remain open.
  No merge, live deployment or application-data mutation was performed.


## Package PTR-6: Make partial taxonomy reviewable and usable in admin

### Entry and scope

- **Objective and non-goals:** Show accepted canonical topics, unresolved
  clusters, reconciliation provenance and truthful coverage in admin; keep
  article generation usable without themes. Do not expose protected candidate
  evidence or taxonomy internals at the public edge.
- **Dependency outputs verified:** PTR-5 backend association schemas,
  operational status codes, coverage counts and
  generation contract; PTR-3 protected review provenance.
- **Expected modules/files and owners:** Taxonomy review/operations schemas and
  routes as required, `frontend/admin/src/api/`, navigation/pages/components,
  dashboard/generation state, frontend tests, public-edge denial tests.
- **Applicable AC IDs / decisions:** AC-03, AC-05–AC-07, AC-09; ADR-0003.
- **Baseline rechecked on / drift discovered / resolution:** 2026-10-09 at
  `8b3910acdf88bddb87e4f10a41819c6bfad595b6`; 58 modified and 14 untracked
  paths from PTR-0–PTR-5 are preserved. Coverage and state-free input types
  exist; protected review lacks a UI and readable antecedents. Theme defaults
  hide useful zero-theme topics. Reuse existing API/client/components/queues;
  verify all ten acceptance criteria with new package evidence. Resumed after
  interruption on the same revision with the earlier PTR-6 code/tests preserved;
  Compose services and prior focused results revalidated. The interrupted full
  command had not run: Docker socket access required execution-environment
  escalation, separate from standing user authorization. The rerun passed.

### Local contract

- **Inputs and outputs:** Typed API exposes partial/full topic coverage, canonical
  topics, protected provisional/rejected cluster summaries, equivalence
  antecedents, optional themes, and bounded failure codes. Input views show the
  published run's topic/theme associations without inventing taxonomy states;
  empty associations are normal. Operational views still distinguish taxonomy
  processing, publication and failure states.
- **Invariants and transaction boundaries:** UI never treats a cast as runtime
  proof; stale requests cannot overwrite newer state; candidate evidence stays
  behind operator authorization; public edge remains projection-only.
- **State transitions, leases, idempotency and concurrency:** Read-only review;
  existing generation mutation invalidation/revision safeguards remain.
- **Authorization, private/public data exposure:** Candidate review uses review
  or mutation token. Public pages receive only approved article projection and
  immutable theme display snapshots.
- **Failure/retry/recovery and rollout:** Missing operator credentials fail
  closed without breaking ordinary partial taxonomy browsing. Empty themes are
  rendered as a normal state.
- **Compatibility and downstream package impacts:** Update TypeScript contracts
  with backend schemas in the same package. PTR-7 consumes the visible journey.

### Work and acceptance

- [x] PTR-6-A1–A3: Remove the TypeScript input taxonomy-state contract; render
  with-topic/without-topic run totals and normal empty associations.
- [x] PTR-6-A4–A6: Add protected candidate review for accepted topics, rejected
  clusters and merge provenance without exposing raw audit payloads by default.
- [x] PTR-6-A7–A9: Make topic browsing/recommendations/generation work with zero
  themes and preserve loading/empty/error/stale-response behavior.
- [x] PTR-6-A10: Prove public edge cannot reach candidate/admin routes and
  approved projections remain unchanged.

| Acceptance ID | Observable condition (including relevant failure case) | Verification command/test | Result / date / environment / revision or dirty-tree context |
| --- | --- | --- | --- |
| PTR-6-A1 | Overview shows total evidence, evidence with topics, and evidence without topics, and labels partial publication accurately | U3 component overview partial-total rendering | passed 2026-10-09; preserved dirty checkout, U1–U4 |
| PTR-6-A2 | Input/evidence views use published-run topic/theme arrays, contain no taxonomy-state label, and handle empty arrays normally | U1 partial input arrays + U3 Inputs rendering/stale state | passed 2026-10-09; preserved dirty checkout, U1–U4 |
| PTR-6-A3 | Empty theme collection is normal while accepted topics remain browseable | U1 empty theme/published topic API + U3 normal theme empty view | passed 2026-10-09; preserved dirty checkout, U1–U4 |
| PTR-6-A4 | Authorized operator can inspect canonical topic evidence and antecedent provisional topics | U1 readable merged antecedents/exact canonical evidence + U3 operator screen | passed 2026-10-09; preserved dirty checkout, U1–U4 |
| PTR-6-A5 | Rejected/unresolved clusters show bounded reasons and support counts without implying their evidence is invalid | U1 bounded geometry/rejected naming reasons + U3 retained-evidence copy | passed 2026-10-09; preserved dirty checkout, U1–U4 |
| PTR-6-A6 | Missing/incorrect token fails closed and raw prompt/model payloads are absent | U1 review-only/mutation-only/unconfigured auth and payload privacy + U3 credential/error states | passed 2026-10-09; preserved dirty checkout, U1–U4 |
| PTR-6-A7 | Recommendations include valid canonical topics from a partial run | U1 both recommendation strategies + U3 topic recommendation links | passed 2026-10-09; preserved dirty checkout, U1–U4 |
| PTR-6-A8 | Topic-targeted generation freezes only canonical evidence and completes with no themes | U1 HTTP job/worker frozen scope through replacement + U3 full generation screen steps | passed 2026-10-09; preserved dirty checkout, U1–U4 |
| PTR-6-A9 | Loading, partial, empty, error, refresh and stale-response states are deterministic | U3 component states, ownership guards, typecheck/test/build | passed 2026-10-09; preserved dirty checkout, U1–U4 |
| PTR-6-A10 | Public edge denies candidate/admin/API paths and approved article rendering remains projection-only | U2 test_public_edge_isolation HTTP denials + test_public_site_e2e approval projection | passed 2026-10-09; preserved dirty checkout, U1–U4 |

### Documentation and handoff

- **Delivered objective:** Accepted canonical topics, unresolved clusters,
  readable merge provenance and truthful coverage are reviewable; generation
  works with zero themes; protected evidence remains unreachable at the public
  edge. All four work bullets and PTR-6-A1–A10 are reconciled above.
- **Delivered interfaces / owners:** Existing protected review route/schema
  gains readable antecedents (IDs, names, descriptions, question/support counts,
  relationship and decision ID) limited to the displayed canonical topics.
  Review reads share one repeatable-read snapshot. Existing 50-run list and
  50-row canonical evidence reader are consumed by the typed ApiClient.
  `/taxonomy-review?run=<id>` adds read-only review, explicit evidence paging,
  truncation notice, manual refresh/retry, safe text and in-memory credentials;
  credentials are neither cached nor persisted. `/inputs` adds bounded paging
  and normal published-run arrays independently of processing status. The
  obsolete input-state wording is removed from TypeScript documentation.
  Overview and Generate default to topics; explicit theme links remain valid.
  Late target/evidence/template/job/poll results in generation now validate
  their original request ownership before updating the screen.
- **Evidence context:** 2026-10-09, HEAD
  `8b3910acdf88bddb87e4f10a41819c6bfad595b6` plus preserved PTR-0–PTR-5 and
  PTR-6 changes. Only disposable `compose.test.yaml` PostgreSQL 17/pgvector
  and rebuilt API/public nginx were used; the local application was not started
  or changed. No PTR-6 migration, new setting or architecture boundary change.
- **U1 (final API/database scope):**
  `docker compose -f compose.test.yaml run --rm tests python -m unittest discover -s tests/integration -p test_partial_taxonomy_admin_postgres.py -v`
  — six passed, zero skips. Covers exact merged evidence and readable antecedents;
  bounded 100-cluster truncation; rejected naming without raw model/prompt data;
  missing/incorrect/review-only/mutation-only/unconfigured credentials; canonical
  recommendations and normal empty published associations; HTTP generation,
  foreign-evidence rejection, publication during job creation and worker
  persistence against the frozen prior run with no themes. Initial five cases
  also passed before adding the sixth privacy case.
- **U2 (broader integration / public edge):**
  `docker compose -f compose.test.yaml up -d --build postgres api public-web`
  and `docker compose -f compose.test.yaml run --rm tests python -m unittest discover -s tests -v`
  — 295 tests passed, zero skips, including populated upgrades, publication,
  readers, operator routing, HTTP denial of candidate detail/evidence, admin,
  review and API paths, and approved article publication/withdrawal/reapproval.
  U2 ran before the sixth U1 test was added; U1 then verified the final file.
  An initial redirected command failed on Docker socket sandbox permissions
  before tests ran; execution-environment escalation allowed the successful
  rerun. User authorization remained in effect throughout.
- **U3 (frontend):** From repository root,
  `npm run typecheck --prefix frontend/admin`,
  `npm test --prefix frontend/admin` (includes `npm run build`), and
  `node frontend/admin/tests/partial-taxonomy-components.test.mjs`
  — typecheck/build passed, all ten test files passed, all seven explicit
  component cases passed, zero skips. Production components execute in a small
  native-DOM harness; tests cover coverage, optional themes, published input
  arrays, protected review, safe source text, credentials, loading/empty/error,
  refresh/retry/stale responses, deep-link bounds, topic generation through
  evidence/template/confirmation/job creation, and ignored late generation
  target after navigation. This is component/state evidence, not browser-layout
  or live-model semantic evaluation. Early harness assertions were corrected
  for option text and DOM spacing; all final checks pass.
- **U4 (references / consistency):** API, admin README, root README, architecture,
  current state, operations, documentation guide and this plan describe the
  delivered source behavior. `git diff --check`, active-plan uniqueness and
  relative Markdown link checks passed (37 targets across eight affected
  references, none broken). AC-03/05/06/07/09 and ADR-0003 boundaries
  remain unchanged; no additional ADR or schema migration is needed.
- **Rollout / limits:** Not committed, merged or deployed. Apply the existing
  backup-first 044–048 procedure with matching API/admin/scheduler images.
  Review errors fail closed; ordinary topic browsing does not require operator
  credentials. UI truncation is explicit; raw audit inspection is not exposed.
  Production-model accuracy and complete Sheets-to-publication journey remain
  PTR-8 work. No application volumes or live publication were changed.
- **Next package / concrete inputs:** PTR-7 is ready with the Inputs page and
  state-free typed arrays, protected run/evidence review and merge provenance,
  deterministic partial/zero-theme fixtures and visible topic generation.
  Revalidate successive-run addition/removal/replacement/empty associations,
  segment deduplication/order, earlier-run and approved-display immutability,
  failed/competing successor and explicit rollback using its own evidence.
- **Completion reconciliation:** Objective, all four work bullets and all ten
  acceptance criteria have current package evidence. PTR-6 is complete in this
  dirty checkout. PTR-7/PTR-8 and feature-level acceptance remain open; the
  active plan is retained.

## Package PTR-7: Replace current associations without changing history

### Entry and scope

- **Objective and non-goals:** Prove and, where necessary, correct how a newly
  published run replaces the topics and themes shown for each input. Current
  input readers must show only the newest published run, while earlier runs and
  approved article displays remain unchanged. Do not copy current topics or
  themes onto `original_inputs` or `segment_inputs`, rewrite historical runs,
  or redesign the publication lifecycle.
- **Dependency outputs verified:** PTR-5 atomic publication and published-run
  association projection; PTR-6 API/admin reader contracts; existing immutable
  article publication snapshots.
- **Expected modules/files and owners:** Publication SQL functions,
  `api/routes/inputs.py`, article/public projection readers only if a failure is
  found, and focused PostgreSQL/API/public tests.
- **Applicable AC IDs / decisions:** AC-02–AC-06, AC-08, AC-09; ADR-0001 and
  ADR-0003.
- **Baseline rechecked on / drift discovered / resolution:** 2026-10-09 at
  `8b3910acdf88bddb87e4f10a41819c6bfad595b6`, preserving 71 modified and
  19 untracked paths from PTR-0–PTR-6. Inputs uses one SQL statement and one
  published-run CTE for both arrays; article/public readers use stored display
  snapshots. 048 owns manual/automatic swap and rollback. Existing tests lack
  an explicit added/removed/replaced/still-empty matrix and real gated
  replacement public HTTP evidence. Add reusable successive-run fixtures and
  dedicated PostgreSQL/API/edge checks; change runtime only if they reveal a
  defect. Entry criteria were open; completion evidence is recorded below.

### Local contract

- **Inputs and outputs:** Publish a first run with known input topics/themes,
  then publish a successor that adds, removes, replaces or leaves those
  associations empty. Input responses immediately reflect only the successor.
  The first run remains queryable as history, and an article approved against
  it retains its approved topic/theme display.
- **Invariants and database-write boundaries:** Associations remain stored
  against the run that produced them. Source evidence rows are not rewritten
  with the current taxonomy. One successful publication switch selects all
  current input topics and themes; a reader never combines runs. Existing
  split-answer combination, duplicate removal and stable ordering remain.
- **State transitions, leases, idempotency and concurrency:** A successful
  successor changes `published → superseded` and `ready → published` together.
  A failed or competing successor leaves the current publication unchanged.
  Explicit rollback makes the selected earlier run current again without
  changing either run's stored associations.
- **Authorization, private/public data exposure:** Historical candidate evidence
  remains protected. Public articles continue to use their approved display
  snapshots rather than live input associations.
- **Failure/retry/recovery and rollout:** Repeated publication or rollback is
  safe. A failure at any point leaves one complete run current; recovery never
  requires repairing topic/theme fields on source evidence rows.
- **Compatibility and downstream package impacts:** No new API shape. PTR-8
  consumes the verified replacement, history and article-snapshot behaviour.

### Work and acceptance

- [x] PTR-7-A1/A2: Add successive-run fixtures covering topic and theme
  addition, removal, replacement and continued empty associations.
- [x] PTR-7-A3: Verify split-answer associations remain combined, deduplicated
  and stably ordered after the publication changes.
- [x] PTR-7-A4: Verify earlier runs and approved article displays remain
  unchanged after successor publication.
- [x] PTR-7-A5/A6: Verify failed successor, successful successor, replay and
  rollback at the PostgreSQL and API boundaries; correct any reader or
  publication defect the tests expose.

| Acceptance ID | Observable condition (including relevant failure case) | Verification command/test | Result / date / environment / revision or dirty-tree context |
| --- | --- | --- | --- |
| PTR-7-A1 | After a successor is published, each input shows only that run's topic result for added, removed, replaced and still-empty cases | R2 `test_successor_replaces_every_original_and_split_array_then_replay_rollback` | passed 2026-10-09; preserved dirty checkout, disposable PostgreSQL/API/edge, R1–R4 |
| PTR-7-A2 | After a successor is published, each input shows only that run's theme result for added, removed, replaced and still-empty cases | R2 successor matrix and `test_zero_theme_successor_removes_every_current_theme_and_rollback_restores_them` | passed 2026-10-09; preserved dirty checkout, disposable PostgreSQL/API/edge, R1–R4 |
| PTR-7-A3 | Multiple segments of one answer still produce one deduplicated, stably ordered topic/theme list, including when only some segments have a topic | R2 successor matrix with four segments, duplicate memberships and uncovered segment | passed 2026-10-09; preserved dirty checkout, disposable PostgreSQL/API/edge, R1–R4 |
| PTR-7-A4 | The earlier run remains unchanged and queryable, and approved articles retain their frozen historical topic/theme display | R2 protected historical topic/evidence reader and exact frozen rows; R3 approved API/public HTTP projection | passed 2026-10-09; preserved dirty checkout, disposable PostgreSQL/API/edge, R1–R4 |
| PTR-7-A5 | A failed or competing successor leaves every current association on the prior published run; no response mixes runs | R2 `test_failed_gate_and_failed_publication_leave_all_current_arrays_unchanged` and `test_competing_swap_and_inflight_readers_keep_one_complete_run` | passed 2026-10-09; preserved dirty checkout, disposable PostgreSQL/API/edge, R1–R4 |
| PTR-7-A6 | Successful publication and explicit rollback switch all current associations together and are safe to replay | R2 successor/competing/zero-theme replay and rollback; R3 real HTTP projection through SQL publication/rollback | passed 2026-10-09; preserved dirty checkout, disposable PostgreSQL/API/edge, R1–R4 |

### Documentation and handoff

- **Delivered behaviour / existing owners:** The single SQL statement in
  `api/routes/inputs.py` captures one published run for both arrays. Migration
  048's `publish_taxonomy_run`, `publish_taxonomy_run_automatically` and
  `rollback_taxonomy_run` retain the publication lifecycle. Existing article
  topic snapshots and `article_publication_themes.display_name` preserve approved
  displays. No runtime defect was found; no production code, migration, wire
  shape, source taxonomy column or architecture boundary was added by PTR-7.
- **Reusable evidence:** `backend/tests/integration/taxonomy_replacement_fixture.py`
  supplies seven immutable original inputs, including a four-segment answer,
  and audited predecessor outputs for successive two-topic/two-theme runs and
  a zero-theme successor. It uses real reconciliation, server-computed quality
  gates and publication owners. The shared provisional fixture now accepts
  optional segment IDs and derives support counts from its supplied evidence.
- **Historical isolation:** Exact comparisons cover 25 run-scoped tables,
  including frozen evidence, decisions, traces, revisions and attestations;
  run provenance excludes only permitted publication lifecycle fields.
  Superseded runs remain readable through protected topic/evidence HTTP routes.
  Source input/preparation/embedding rows and approved article storage remain
  unchanged. Real rebuilt API/nginx checks preserve historical topic tags,
  approved HTML and frozen public theme displays, and deny private paths.
- **Failure/concurrency/recovery:** A failed computed gate and an injected audit
  failure after materialization leave the previous complete arrays served and
  no partial successor writes. An advisory-lock competitor is rejected after
  the committed switch; an independent HTTP reader sees the old complete run
  while the writer is uncommitted. Reviewed retry, publication replay and
  repeated explicit SQL rollback retain one complete current publication.
- **Exact commands / environment:** On 2026-10-09 at entry revision
  `8b3910acdf88bddb87e4f10a41819c6bfad595b6`, preserving the 71 modified and
  19 untracked predecessor paths, use only `compose.test.yaml`'s disposable
  PostgreSQL 17/pgvector database and rebuilt API/public nginx. R1:
  `docker compose -f compose.test.yaml up -d --build postgres api public-web`
  passed. R2:
  `docker compose -f compose.test.yaml run --rm tests python -m unittest discover -s tests/integration -p test_taxonomy_replacement_postgres.py -v`
  passed all 4 tests in 4.095s, no skips. R3:
  `docker compose -f compose.test.yaml run --rm tests python -m unittest discover -s tests -p test_public_taxonomy_replacement.py -v`
  passed its 1 real API/edge test in 1.034s, no skips. R4: after
  `docker compose -f compose.test.yaml down` and R1 to clear only the test
  database, run
  `docker compose -f compose.test.yaml run --rm tests python -m unittest discover -s tests -v`;
  passed all 301 tests in 67.493s, no failures or skips. Full log:
  `/tmp/ptr7-full.log` (local session artifact). The initial unprivileged Docker socket attempt
  failed before execution; authorized escalated commands succeeded.
- **References / drift:** API and operations now explicitly describe whole-run
  array replacement, normal empty results, stored article displays and the
  existing SQL rollback owner. Guide/current-state and ADR-0003 implementation
  status now reflect package closure; ADR-0003 had still named PTR-5 as next.
  This status drift was corrected; the accepted decision is unchanged. R5:
  `git diff --check` passed; local Markdown link targets in the six updated
  reference/plan files resolved, and active-plan discovery found only
  `docs/work-packages.md`.
- **Limitations and next package:** PTR-8 receives the reusable matrix and both
  new test files, with all prior contracts intact. It must verify fresh and
  populated migration paths, the full Sheets/API evidence-worker/scheduler
  journey, automatic partial/full publication and generation, and final
  feature-level acceptance. Seeded audited predecessor outputs here do not
  prove live model semantics or that full journey. No frontend surface changed;
  PTR-8 retains its own typecheck/test/build requirements. No merge, deployment
  or application-data mutation was performed.
- **Completion reconciliation:** All four work bullets and PTR-7-A1–A6 have
  current evidence. PTR-7 is complete in the preserved dirty checkout; PTR-8
  dependencies remain valid and its eight criteria stay open. The disposable
  verification stack was shut down after acceptance.


## Package PTR-8: Prove the complete partial-taxonomy lifecycle

### Entry and scope

- **Objective and non-goals:** Verify migration, Google Sheets/API ingestion,
  evidence preparation, coherent clustering, provisional labels,
  cross-question reconciliation, optional themes, partial publication, admin
  review and topic generation as one lifecycle. Do not deploy externally or
  delete application data.
- **Dependency outputs verified:** Every PTR-1–PTR-7 interface, migration,
  readiness marker, API/admin contract and test fixture.
- **Expected modules/files and owners:** `compose.test.yaml`, taxonomy journey
  harness/fixtures, migration upgrade tests, current reference documents and
  this plan.
- **Applicable AC IDs / decisions:** AC-01–AC-09; ADR-0001–0003.
- **Baseline rechecked on / drift discovered / resolution:** 2026-10-10,
  `8b3910acdf88bddb87e4f10a41819c6bfad595b6`; preserve 73 modified and
  22 untracked predecessor paths, including unfinished PTR-8 harness, Compose
  and populated-upgrade changes. Migrations 044–048, gate v3, protected review,
  published associations and PTR-7 matrix exist. The Compose journey omitted
  required question context, expected seven stages and lacked integrated partial/
  full, Sheets, generation and public-edge cases. Extend the existing harness
  and deterministic chat fixture using the production owners; no new lifecycle.

### Local contract

- **Inputs and outputs:** Disposable fresh and populated databases plus
  deterministic structured-model fixtures produce observable complete and
  partial journeys, migration/recovery evidence, and final documentation.
- **Invariants and transaction boundaries:** Test databases only; no application
  volume deletion. Journey asserts single published run, immutable provenance,
  exact with-topic/without-topic coverage, state-free input associations, safe
  replacement and public-edge isolation.
- **State transitions, leases, idempotency and concurrency:** Exercise crash
  replay/stale lease at focused boundaries and one complete automatic path.
- **Authorization, private/public data exposure:** Protected review uses fixture
  tokens; public responses exclude evidence/audit data.
- **Failure/retry/recovery and rollout:** Verify prior publication remains served
  through failed replacement and explicit rollback works after successful
  replacement. Document actual deploy order and backup requirements.
- **Compatibility and downstream package impacts:** This is the integration
  owner. Feature closure requires every package and feature-level criterion.

### Work and acceptance

- [x] PTR-8-A1/A2: Prove fresh initialization and populated upgrade with
  matching runtime consumers and no historical mutation.
- [x] PTR-8-A3/A4: Prove partial-coverage and full-coverage automatic journeys,
  including equivalent cross-question merge, related-topic theme, and the
  zero-theme case, using PTR-7's verified replacement boundary.
- [x] PTR-8-A5: Prove eligible Google Sheets/API evidence gains published-run
  associations and supports topic-targeted generation, while ineligible input
  is retained without an embedding.
- [x] PTR-8-A6: Prove failed replacement preserves prior publication and
  rollback/replay/concurrency invariants.
- [x] PTR-8-A7/A8: Update every reference/contract, reconcile all acceptance
  evidence, archive the plan only after feature closure.

| Acceptance ID | Observable condition (including relevant failure case) | Verification command/test | Result / date / environment / revision or dirty-tree context |
| --- | --- | --- | --- |
| PTR-8-A1 | Fresh disposable PostgreSQL initializes all schema/functions and completes the new stage lifecycle | Full isolated Compose suite | J1/J3 passed 2026-10-10; fresh disposable PostgreSQL 17/pgvector, rebuilt runtime, eight completed stages |
| PTR-8-A2 | Populated rows with question identity upgrade without rewriting prior runs, attestations, publications or articles; an unresolved questionless fixture blocks safely without mutation | Populated-upgrade integration test | J1/J2 passed 2026-10-10; 13 upgrade tests, exact history preservation and questionless rollback |
| PTR-8-A3 | Deterministic partial fixture publishes accepted canonical topics, evidence with and without topic membership, zero themes, and no input taxonomy-state field | Automatic taxonomy journey | J3 passed 2026-10-10; 12 evidence items, 6 with topics, 6 without, one canonical topic and zero themes |
| PTR-8-A4 | Cross-question equivalents merge once, related topics remain distinct and can form a theme | Journey fixture assertions | J3 passed 2026-10-10; exact unions across two question identities; full successor has two canonical topics and one shared theme |
| PTR-8-A5 | Question-bound eligible Sheet/API evidence receives published-run topic/theme arrays and supports generation; ineligible input is retained without an embedding; public exposure stays approved-only | Cross-component HTTP acceptance | J3 passed 2026-10-10; real importer/API/workers/generation/approval/edge; frozen article evidence provenance |
| PTR-8-A6 | Failed successor leaves prior publication served; replay/stale claim cannot corrupt it; explicit rollback restores prior run | PostgreSQL/Compose acceptance | J1/J3 passed 2026-10-10; failed successor, unchanged-set suppression, replay/rollback and current concurrency/stale-claim tests |
| PTR-8-A7 | Backend, frontend typecheck/tests/build, and public-edge denial tests pass with no required skips | Exact commands recorded on current working tree | J1/J4 passed 2026-10-10; 302 backend tests and 10 frontend test files, no skips; typecheck/build passed |
| PTR-8-A8 | Architecture/current state/API/operations/README/admin docs and ACs describe implemented behavior; plan evidence is internally consistent | Link review, plan reconciliation, `git diff --check` | J5 passed 2026-10-10; references, links, acceptance reconciliation and diff checks |

### Documentation and handoff

- **Delivered behaviour / owners:** The existing journey now uses the production
  Sheets reader, importer and API sink with fixture auth/values transport,
  question-bound direct API input, eligibility/embedding workers, real
  `nomic-embed-text` question-answer vectors (768 dimensions), all eight
  scheduler stages, gate v3 and `taxonomy-automation-v3`. Structured chat is
  deterministic and controls partial/full/rejected-label scenarios. Real
  generation, editorial approval, protected review and nginx delivery complete
  the lifecycle. No second runtime lifecycle or migration was introduced.
- **Runtime correction:** The integrated generation check exposed missing
  `article_evidence.taxonomy_run_id` on new articles. The shared
  `articles.create_article_record` owner now saves its selected/frozen run on
  evidence rows, matching topic tags and the generation job. The existing
  generation-through-replacement PostgreSQL test now asserts this field after
  the worker finishes against a superseded run. Historical rows are not
  rewritten; API shapes, publication rules and AC boundaries are unchanged.
- **Exact commands / current evidence:** All commands ran on 2026-10-10 at HEAD
  `8b3910acdf88bddb87e4f10a41819c6bfad595b6`, preserving entry's 73 modified
  and 22 untracked paths plus this package's final changes. Only disposable
  PostgreSQL databases and isolated Compose services were used.
  - **J1:** `docker compose -f compose.test.yaml down`, then
    `docker compose -f compose.test.yaml up -d --build postgres api public-web`,
    then `docker compose -f compose.test.yaml run --rm tests python -m unittest discover -s tests -v`.
    Final result: 302 tests passed in 77.640s, no failures or skips. Log:
    `/tmp/ptr8-full.log`. Includes populated upgrades, replacement matrix,
    transaction rollback, crash replay, stale evidence/naming/reconciliation/
    quality claims, competing swaps, real API and public-edge denial checks.
  - **J2:** `docker compose -f compose.test.yaml run --rm tests python -m unittest discover -s tests/integration -p test_migration_upgrade_postgres.py -v`.
    All 13 tests passed, no skips (5.746s); also passed in final J1. Exact
    comparisons cover resolved input, historical run/topic/theme/attestation/
    publication rows and approved article/public snapshots across 044–048.
    The unresolved-question fixture retains its rows and nullable schema and
    creates no preparation-decision table in its isolated schema on failure.
    Log: `/tmp/ptr8-upgrade.log`.
  - **J3:** `docker compose -f compose.taxonomy-journey.yaml down`, then
    `docker compose -f compose.taxonomy-journey.yaml up -d --build --wait`,
    then `docker compose -f compose.taxonomy-journey.yaml --profile acceptance run --rm journey`.
    Passed on fresh tmpfs PostgreSQL with rebuilt API/workers/scheduler/chat/
    public edge and real Ollama. Log: `/tmp/ptr8-journey.log`.
    Final JSON: `{"article_id":1,"failed_run":3,"full_run":2,
    "migration_markers":47,"partial_run":1,"result":"PASS"}`.
    Partial publication has 12 eligible evidence items, six covered and six
    uncovered, two accepted provisional labels merged into one canonical topic
    across two question identities, and zero themes. Generation freezes six
    evidence items and produces a reviewable topic-only article. A cumulative
    full successor has 13 covered items, two distinct canonical topics with
    exact antecedent unions, and one theme linking both. A rejected-label
    successor cannot publish or loop; repeated automatic publication and
    rollback preserve decisions and approved content. Ineligible spam remains
    stored without a vector. Public private-route requests return 404.
  - **J4:** From `frontend/admin`: `npm run typecheck`, `npm test`,
    `npm run build`; all passed, 10 test files, no skips. Existing production
    component/client/state tests cover protected review, partial coverage,
    empty arrays/themes, generation and stale responses. Build log:
    `/tmp/ptr8-frontend-build.log`. Frontend code did not change in PTR-8.
  - **J5:** `git diff --check`, relative Markdown target review across updated
    references and relocated plan, and
    `rg --files docs -g '*work*package*.md' -g '!**/archive/**' -g '!**/templates/**' -g '!**/reviews/**'`.
    Passed; all 52 local Markdown targets resolved. Final active-plan
    discovery returns no paths (expected exit 1).
- **Failures corrected / limitations:** Early journey runs exposed a harness
  `themes` versus `theme_ids` mismatch, a test query using question identity
  from the wrong table, then the real missing article-evidence provenance
  described above. The full-successor fixture also still matched the old
  theme prompt; it now uses the current optional-theme prompt. The harness
  fails immediately on a failed stage rather than waiting for publication.
  An added migration assertion initially resolved the public
  schema through search-path fallback; it now explicitly checks its isolated
  schema. Final affected checks passed. Docker socket denials occurred before
  execution; authorized escalated commands succeeded. External Sheets auth/
  values and chat responses remain fixtures, so live Google credentials and
  production-model semantic accuracy are not claimed. Calibration evidence
  and versioned bounds remain as delivered; model-specific drift is an
  operational risk, not omitted package scope.
- **References / rollout:** Root README, architecture, AC verification guidance,
  current state, API, operations, admin README, documentation guide, ADR-0003
  and archive index now describe the completed source and verification.
  Existing backup-first question audit, scheduler stop, ordered 044–048
  migrations and matching API/evidence-worker/scheduler/generation/admin
  images remain required for deployment. Keep prior publication on candidate
  failure; explicit SQL rollback selects an earlier publication, while schema
  recovery requires the pre-upgrade backup. No application data or application
  volume changed. Disposable stacks are shut down; model cache is retained.
- **Completion reconciliation:** Objective, all five work bullets, PTR-8-A1–A8,
  all predecessor criteria and PTR-F1–F6 have evidence. No next package or
  undelivered authorized scope remains. Feature is archived after closure;
  merge and deployment remain separate actions outside this request.

## Feature closure

| Feature acceptance | Current integrated evidence |
| --- | --- |
| PTR-F1 | J3 accepted the neutral accessible-transit label without lexical overlap; J1 includes synonym/structure/geometry checks. |
| PTR-F2 | J3 checks two question identities, two antecedents per topic and exact evidence-set unions; J1 covers partition/lineage/replay. |
| PTR-F3 | J3 full successor retains two distinct related concepts and links both to one theme; J1 covers invalid/optional theme outcomes. |
| PTR-F4 | J3 exact 6/6 partial coverage and state-free arrays; J1/J4 verify API/admin consumers. |
| PTR-F5 | J3 partial zero-theme publication, protected review, topic generation and approval; J1/J4 verify browsing/client/components. |
| PTR-F6 | J1 real publication concurrency, rollback, stale claims and history isolation; J3 failed successor/replay/rollback and unchanged approved public content. |

- **Temporary paths retired / compatibility retained:** New automatic candidates
  use question-answer vectors, partial naming, cross-question reconciliation,
  optional theme inference, gate v3 and automation v3. Lexical label validation
  and gate-v2 requirements no longer govern new automatic candidates. Immutable
  historical runs, attestations, audit archive, and the explicit manual mixed-
  representation compatibility path remain intentionally readable. They are
  never a publication-reader fallback or rewritten as current-policy passes.
- **Implemented / verified / merged / deployed:** PTR-0–PTR-8 implemented and
  verified in the preserved dirty checkout. None is committed, merged or
  deployed by this package. Installed runtime still needs the documented
  backup/audit/migration/image rollout.
- **Final status / archive reason:** Complete on 2026-10-10; all package and
  feature acceptance criteria verified. Archived because the authorized source
  feature is complete. No undelivered scope remains. Earlier dated resumption
  and package handoffs describe their own completion dates; this section and
  the final pipeline supersede their then-open successor status.
