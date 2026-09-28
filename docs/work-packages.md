# Partial taxonomy and reconciled-topic work packages

## Concise pipeline reference

```text
Prepare evidence
→ cluster similar answers within each question
→ reject incoherent or insufficiently distinct clusters
→ label each passing cluster with an LLM using up to 40 representative answers
→ validate structure and provenance, not meaning by word matching
→ merge equivalent topics across questions while retaining their evidence
→ infer optional themes from related, distinct topics
→ publish one immutable taxonomy with explicit classified/unclassified coverage
```

The design gives semantic work to embeddings and the LLM, and gives
deterministic code the facts it can prove: cluster geometry, valid identifiers,
bounded output, immutable provenance, non-overlapping reconciliation, truthful
coverage, and safe publication. Equivalent topics merge; merely related topics
remain distinct and may share a theme. Valid topics are useful even when other
evidence remains unclassified or no broader theme exists.

## Feature contract: PTR — partial taxonomy with reconciled topics

- **Status / last updated:** Planned; 2026-09-28. PTR-0 is ready. No runtime
  implementation has started.
- **User request and authorized scope:** Plan future implementation of scope 2:
  publish valid topics from an incomplete candidate with explicit coverage;
  replace lexical topic validation with cluster-quality plus LLM semantic
  labelling; provide all evidence up to 40 or 30 central plus 10 diverse; and
  reconcile equivalent topics across questions before theme inference. This
  turn authorizes documentation and planning only, not implementation or live
  data changes.
- **Outcome and feature-level acceptance IDs:**
  - PTR-F1: A coherent cluster can produce a canonical topic without exact
    word overlap between its description and every evidence item.
  - PTR-F2: Equivalent provisional topics from different questions become one
    canonical topic whose evidence union and antecedents are durable.
  - PTR-F3: Related but non-equivalent topics remain distinct and can share an
    optional theme.
  - PTR-F4: One published run may be explicitly partial; every reader reports
    classified, unclassified-in-snapshot, and pending evidence truthfully.
  - PTR-F5: A run with at least one publishable topic and no themes can be
    published and used for topic browsing and topic-targeted generation.
  - PTR-F6: Replacement, rollback, replay, concurrency, audit, article
    provenance, and public exposure remain safe at the single-run boundary.
- **Non-goals:** Independent topic publication from multiple runs; manual
  mutation of model output inside an immutable candidate; automatic merging of
  merely related concepts; changing approved article snapshots; changing the
  Google Sheets identity/import contract; selecting numerical similarity
  thresholds without evaluation evidence.
- **Baseline revision and relevant uncommitted work:** Clean
  `466275729316274d7d0a55414d8b02293f5a92b1` before this documentation-only
  plan and ADR were added. There was no pre-existing `docs/work-packages.md`.
- **Current behaviour and evidence:** `taxonomy_clustering.make_cluster_plan`
  runs HDBSCAN over normalized frozen embeddings with three central and one
  diverse representative. `taxonomy_topics.validate_topic_response` accepts or
  rejects one immutable attempt per cluster and uses exact-token overlap as a
  semantic proxy. `taxonomy_stage_quality` requires topic acceptance >= 0.80
  and at least one reconciled theme. PostgreSQL publication requires that
  passing whole-run attestation and materializes themes. Dashboard taxonomy
  readers require exactly one `published` run; `/inputs` marks any input present
  in that run `classified`, even when no topic membership exists. Read-only run
  2 evidence is recorded in ADR-0003.
- **Proposed behaviour and existing owners to extend:** Extend embeddings and
  snapshots under AC-02; clustering in `taxonomy_clustering.py`; structured
  model transport in `clients/llm.py`; provisional naming in
  `taxonomy_topics.py`; add durable topic reconciliation beside existing theme
  reconciliation; extend scheduler stages and automation rather than adding a
  queue; replace publication functions by numbered migration; update dashboard,
  inputs, operations, generation, admin contracts/pages, and existing test
  harnesses together.
- **Applicable AC IDs and decision records:** AC-01 through AC-09 as applicable,
  especially AC-02, AC-03, AC-04, AC-06, AC-08 and AC-09; ADR-0001,
  ADR-0002, and [ADR-0003](decisions/0003-partial-taxonomy-and-topic-reconciliation.md).
- **Open decisions, assumptions and risks:** PTR-0 must select the clustering
  representation and calibrated cohesion/separation/stability thresholds. It
  must define topic equivalence as subject identity versus position/finding,
  settle the prompt byte/token bound beneath the 40-item cap, define retry
  policy for structurally invalid model output, and establish representative
  evaluation fixtures without putting raw evidence in the repository. Risks
  include question text dominating similarity, broad clusters passing a simple
  radius, LLM over-merging related topics, transitive merge inconsistency,
  double-counting one submission across questions, and prompt/audit truncation.
- **Migration/deploy order, compatibility window and recovery:** PTR-0 has no
  production mutation. If PTR-0 selects a second durable embedding identity,
  PTR-1 delivers its compatibility migration and backfill; otherwise PTR-1
  retains the current schema. Subsequent storage changes use new numbered
  migrations and update `init.sql` plus scheduler readiness markers.
  Deploy migrations with matching scheduler/API/admin images; do not run an old
  scheduler against the new stage lifecycle. Preserve the prior publication
  through candidate construction. Create a new versioned cumulative candidate;
  never rewrite run 2 or its attestation. On failure, stop the new scheduler,
  retain the old publication, and diagnose immutable stage records. Rollback of
  a successful replacement uses the existing explicit run rollback boundary.

| Interface / data / setting | Owner | Before → after | Producers and consumers | Compatibility / verification |
| --- | --- | --- | --- | --- |
| Embedding representation and snapshot provenance | `workers/embeddings.py`, `taxonomy_snapshots.py`, `taxonomy_automation.py`, `input_embeddings` | Current answer-only/question-answer compatibility → calibrated answer-focused cluster representation with question context retained for labelling | Embedding worker → snapshot admission → clustering | PTR-0-A1, PTR-1-A1–A3; fresh and populated upgrade if storage identity changes |
| Cluster plan and diagnostics | `taxonomy_clustering.py`, run configuration, `taxonomy_cluster_*` | HDBSCAN with 3 central + 1 diverse and no release cohesion/separation contract → versioned per-question clustering, calibrated checks, all <=40 or 30 central + 10 diverse | Scheduler clustering stage → topic labelling, review, quality | PTR-1-A4–A7; pure fixtures and PostgreSQL persistence/replay |
| Provisional naming | `taxonomy_topics.py`, `taxonomy_topic_naming_attempts`, model audit | Exact lexical overlap can accept/reject meaning → LLM owns semantics; code validates shape, bounds, identity, membership, and provenance | Topic naming stage → reconciliation and operations review | PTR-2-A1–A6; adversarial shape/provenance tests and real stored fixtures |
| Canonical topic reconciliation | New owner beside `taxonomy_reconciliation.py`; new migration/tables; scheduler stage | Every accepted cluster immediately acts as a topic; only exact-name collision exists → immutable provisional topics are reconciled into non-overlapping canonical equivalence groups with unioned memberships | Provisional naming → theme inference, taxonomy readers, lineage, generation | PTR-3-A1–A8; PostgreSQL atomicity/replay/concurrency tests |
| Theme inference | `taxonomy_themes.py`, `taxonomy_reconciliation.py`, theme identity functions | Consumes accepted cluster topics; at least one reconciled theme required → consumes canonical topics; zero themes is a valid outcome | Canonical topics → themes → quality/publication/readers | PTR-4-A1–A4 |
| Release attestation and publication | `taxonomy_stage_quality.py`, `taxonomy_automation.py`, publication SQL functions | Acceptance ratio >=0.80 and >=1 theme gate the whole run → immutable policy reports topic integrity and explicit coverage; >=1 publishable topic can produce a partial run | Quality stage/automation/API → PostgreSQL transition → all readers | PTR-4-A5–A8, PTR-5-A1–A7; migration, gate, rollback tests |
| Input taxonomy state | `api/routes/inputs.py`, API/admin contracts | Snapshot membership implies `classified`; otherwise pending/unavailable → topic membership is classified, frozen without canonical membership is unclassified, after-cutoff is pending | API → admin and external consumers | PTR-5-A3, PTR-6-A1–A3 |
| Dashboard/operations/generation | Dashboard queries/routes, operations, generation, admin | No publication returns 503; summaries count classified evidence only; themes assumed available → partial publication is readable, coverage is explicit, zero-theme topic generation works | API → admin; generation worker → articles | PTR-6-A4–A9 |
| Public projection | `articles.py`, article approval, `public_site/` | Approved immutable article/theme snapshots | Same projection; partial taxonomy state and unclassified evidence remain private; topic-origin articles remain valid | Editorial approval → public edge | PTR-6-A10, PTR-7-A5 |

## Pipeline

| Package | Status | Dependencies and required outputs | Outputs / consumers | Completion evidence |
| --- | --- | --- | --- | --- |
| PTR-0 — representation and policy calibration | ready | Current clean baseline, ADR-0003, frozen privacy-safe evaluation method | Selected representation, topic semantics, thresholds, prompt bound, reconciliation rubric consumed by PTR-1–PTR-4 | PTR-0-A1–A6 pending |
| PTR-1 — coherent clusters and bounded evidence packets | planned | PTR-0 selected representation/thresholds/bounds | Durable cluster diagnostics and deterministic <=40/30+10 packets consumed by PTR-2 | PTR-1-A1–A7 pending |
| PTR-2 — structurally validated provisional topics | planned | PTR-1 cluster eligibility and packets | Immutable provisional topic attempts with no lexical semantic gate consumed by PTR-3 | PTR-2-A1–A6 pending |
| PTR-3 — cross-question canonical topic reconciliation | planned | PTR-2 provisional identities/memberships; PTR-0 equivalence rubric | Canonical topics, antecedents, unioned evidence and lineage consumed by themes/readers | PTR-3-A1–A8 pending |
| PTR-4 — optional themes and coverage attestation | planned | PTR-3 canonical topics; PTR-0 calibrated publication policy | Themes over canonical topics; immutable partial/complete coverage attestation consumed by publication | PTR-4-A1–A8 pending |
| PTR-5 — partial publication and truthful backend readers | planned | PTR-4 attestation; numbered migration; stable coverage vocabulary | Database transition and API semantics consumed by admin/generation | PTR-5-A1–A7 pending |
| PTR-6 — admin review, coverage, and topic generation | planned | PTR-5 backend contracts | Operator-visible partial topics, unresolved clusters, coverage and zero-theme generation | PTR-6-A1–A10 pending |
| PTR-7 — integrated lifecycle, migration, and handoff | planned | PTR-1–PTR-6 complete outputs | Full Sheets-to-partial-publication journey, upgrade/recovery evidence, current references | PTR-7-A1–A8 pending |

Next ready package: **PTR-0**, because it is read-only/investigative, depends
only on the current checkout and ADR-0003, and must prevent implementation from
hard-coding uncalibrated geometry or an ambiguous equivalence rule.
Integration owner/package: **PTR-7**, which verifies the complete journey from
Google Sheets/API evidence through canonical topics, optional themes, partial
publication, admin visibility, and topic-targeted generation.

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
- **Baseline rechecked on / drift discovered / resolution:** Recheck on entry;
  baseline currently `4662757` plus this documentation change.

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

- [ ] PTR-0-A1/A2: Compare representations on multiple question types,
  including terse answers, repeated questions, synonyms, opposing positions,
  and cross-question equivalent concepts.
- [ ] PTR-0-A3: Define and calibrate cohesion, separation, membership, and
  stability metrics; demonstrate why each rejects a known bad cluster without
  hiding supported small clusters.
- [ ] PTR-0-A4: Define `topic` as subject versus position/finding and document
  equivalent-versus-related examples for reconciliation.
- [ ] PTR-0-A5: Measure <=40/all and 30-central+10-diverse coverage and select a
  deterministic serialized-input bound compatible with configured models and
  full audit reconstruction.
- [ ] PTR-0-A6: Record the selected policy/version and update downstream package
  inputs; do not mark ready while a required product decision is unresolved.

| Acceptance ID | Observable condition (including relevant failure case) | Verification command/test | Result / date / environment / revision or dirty-tree context |
| --- | --- | --- | --- |
| PTR-0-A1 | Evaluation separates identical-question/different-concept answers while retaining contextual meaning for terse answers | Focused experiment command recorded with dataset/config hashes | pending |
| PTR-0-A2 | Equivalent concepts across different questions remain reconcilable | Synthetic/approved cross-question fixture report | pending |
| PTR-0-A3 | Versioned metrics and thresholds distinguish cohesion and separation and include sensitivity analysis | Focused pure evaluation tests/report | pending |
| PTR-0-A4 | Equivalence rubric distinguishes same subject, opposing position, and broader related theme cases | Reviewed ADR examples and deterministic rubric fixtures | pending |
| PTR-0-A5 | Evidence packet selection covers all <=40 cases, 30+10 cases, duplicate originals, and prompt-bound exhaustion | Pure selection/budget experiment tests | pending |
| PTR-0-A6 | ADR/plan contain concrete outputs sufficient for PTR-1 entry | `git diff --check` and documentation link review | pending |

### Documentation and handoff

- **References to update:** ADR-0003 and this plan only; runtime references wait
  for implementation.
- **Delivered behaviour and interface changes:** None; policy evidence only.
- **Tests passed/failed/skipped and unverified criteria:** Record exact commands
  and any unavailable model/hardware comparison.
- **Decisions/drift and unresolved risks:** Record threshold sensitivity and
  model-specific limits; never generalize one corpus result silently.
- **Next package and concrete inputs:** PTR-1 receives the selected
  representation, metric formulae, thresholds, scope rule, and prompt bound.
- **Completion reconciliation:** All six outputs and downstream assumptions
  must agree before PTR-0 becomes complete.

## Package PTR-1: Produce coherent clusters and bounded evidence packets

### Entry and scope

- **Objective and non-goals:** Implement the selected answer-focused,
  question-aware cluster representation; persist calibrated diagnostics; and
  select every member up to 40 or deterministic 30 central plus 10 diverse.
  Do not call the topic LLM or change publication.
- **Dependency outputs verified:** PTR-0 representation, scope, metrics,
  thresholds, and serialized-input bound.
- **Expected modules/files and owners:** `workers/embeddings.py`,
  `taxonomy_snapshots.py`, `taxonomy_automation.py`, `taxonomy_clustering.py`,
  configuration/Compose, migrations only if vector identity changes, and
  clustering/snapshot tests.
- **Applicable AC IDs / decisions:** AC-01, AC-02, AC-04, AC-08, AC-09;
  ADR-0001–0003.
- **Baseline rechecked on / drift discovered / resolution:** Recheck on entry.

### Local contract

- **Inputs and outputs:** Frozen canonical evidence plus selected versioned
  vectors produce per-question cluster candidates, noise/unresolved evidence,
  member probabilities, centroid, cohesion/separation/stability diagnostics,
  eligibility decision, and ordered evidence packet metadata.
- **Invariants and transaction boundaries:** One representation/model/dimension
  per run; no silent vector mixing; cluster plan and diagnostics commit under
  the existing stage lease; every selected representative belongs to the
  cluster and is reconstructable from immutable evidence.
- **State transitions, leases, idempotency and concurrency:** Preserve the
  clustering stage's claim/lease/replay rules. A reclaimed committed plan is a
  no-op. A failing geometry policy produces a durable unresolved/noise outcome,
  not a model call.
- **Authorization, private/public data exposure:** Raw evidence remains internal
  to the model packet and protected review; routine diagnostics are aggregate.
- **Failure/retry/recovery and rollout:** Model transport is not involved.
  Representation migration/backfill must be retryable and retain current
  embeddings until the new candidate is verified.
- **Compatibility and downstream package impacts:** PTR-2 consumes only
  eligible clusters and their ordered packets. Existing frozen runs remain
  readable and immutable.

### Work and acceptance

- [ ] PTR-1-A1–A3: Implement/version representation production, storage,
  admission, snapshot provenance, backfill/upgrade, and mismatch rejection.
- [ ] PTR-1-A4/A5: Implement per-question clustering plus calibrated cohesion,
  separation, membership and stability diagnostics with deterministic failure.
- [ ] PTR-1-A6: Implement all<=40 or 30 central + 10 iterative farthest-first
  diverse selection, original-input deduplication, and prompt bound.
- [ ] PTR-1-A7: Persist and replay the complete plan atomically under leases.

| Acceptance ID | Observable condition (including relevant failure case) | Verification command/test | Result / date / environment / revision or dirty-tree context |
| --- | --- | --- | --- |
| PTR-1-A1 | Selected representation is generated once per canonical target with immutable provenance | Focused worker/PostgreSQL tests | pending |
| PTR-1-A2 | Admission and snapshot reject missing/incompatible vectors without partial membership | PostgreSQL+pgvector integration tests | pending |
| PTR-1-A3 | Fresh install and populated upgrade preserve prior vectors/runs and produce the new representation safely | Disposable Compose migration tests | pending |
| PTR-1-A4 | Same-question distinct concepts split on calibrated fixtures; terse contextual answers remain interpretable | Pure clustering fixtures | pending |
| PTR-1-A5 | Cohesion/separation/stability failures are durable, bounded, and make no topic-model request | Scheduler/PostgreSQL tests | pending |
| PTR-1-A6 | <=40 selects all; >40 selects deterministic 30 central and up to 10 farthest-first diverse within the size bound | Pure representative-selection tests | pending |
| PTR-1-A7 | Crash replay and stale lease cannot duplicate or overwrite a committed plan | PostgreSQL lease/replay tests | pending |

### Documentation and handoff

- **References to update:** Architecture, operations, root README and AC-02/04/08
  if the representation/storage/config boundary changes.
- **Delivered behaviour and interface changes:** Record exact vector identity,
  diagnostics schema and packet contract.
- **Tests passed/failed/skipped and unverified criteria:** Record pure,
  PostgreSQL, migration and configured-model limitations.
- **Decisions/drift and unresolved risks:** Recheck model dimension/context and
  threshold sensitivity.
- **Next package and concrete inputs:** PTR-2 receives eligible cluster IDs,
  immutable membership, diagnostics, and ordered bounded evidence packets.
- **Completion reconciliation:** All seven acceptance outputs and PTR-2 inputs
  must be verified.

## Package PTR-2: Create structurally valid provisional topics

### Entry and scope

- **Objective and non-goals:** Let the structured LLM name coherent clusters
  from the full bounded packet and validate only structure/provenance. Do not
  perform cross-question merges, infer themes, or publish.
- **Dependency outputs verified:** PTR-1 eligible cluster and packet contracts;
  PTR-0 topic semantics and prompt bound.
- **Expected modules/files and owners:** `taxonomy_topics.py`,
  `clients/llm.py` only if transport bounds need extension, model audit tables,
  topic schemas/migrations if provisional identity must be separated from
  canonical revisions, and focused tests.
- **Applicable AC IDs / decisions:** AC-01, AC-02, AC-04, AC-07, AC-08, AC-09;
  ADR-0003.
- **Baseline rechecked on / drift discovered / resolution:** Recheck on entry.

### Local contract

- **Inputs and outputs:** One eligible cluster and its packet produce one
  immutable accepted or structurally rejected provisional naming attempt with
  versioned model/prompt/request/response provenance.
- **Invariants and transaction boundaries:** The LLM cannot add evidence or
  change membership. Validation requires JSON strings, nonblank bounded name
  and description, 1–8 name words, no exact normalized collision, and matching
  evidence provenance. No lexical/semantic token-overlap check remains.
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

- [ ] PTR-2-A1/A2: Version the prompt and pass the complete PTR-1 packet with
  question context and explicit topic-semantics instructions.
- [ ] PTR-2-A3: Remove all lexical evidence-overlap decisions; retain and test
  structural, bound, duplicate and provenance validation.
- [ ] PTR-2-A4: Define durable provisional identity distinct from final
  canonical identity without rewriting old migrations.
- [ ] PTR-2-A5/A6: Prove lease-safe external call persistence, bounded failures,
  retry semantics and audit reconstruction at the maximum packet size.

| Acceptance ID | Observable condition (including relevant failure case) | Verification command/test | Result / date / environment / revision or dirty-tree context |
| --- | --- | --- | --- |
| PTR-2-A1 | Model receives all members for <=40 and the exact selected bounded packet for >40 | Structured-client fixture tests | pending |
| PTR-2-A2 | Prompt distinguishes topic subject from stance and requests no broader theme merge | Prompt/version fixture review | pending |
| PTR-2-A3 | Synonyms and inflections are not rejected by code; malformed/blank/oversized/duplicate output is rejected | Pure validator tests | pending |
| PTR-2-A4 | Accepted/rejected provisional attempts and source clusters remain immutable and independently auditable | PostgreSQL tests | pending |
| PTR-2-A5 | Stale worker cannot store a response; replay does not duplicate a committed attempt | PostgreSQL lease/concurrency tests | pending |
| PTR-2-A6 | Maximum packet audit can be reconstructed or hash-verified without leaking evidence to logs | Audit-bound tests | pending |

### Documentation and handoff

- **References to update:** Architecture/operations prompt and audit contract;
  AC-04/07/08 where affected.
- **Delivered behaviour and interface changes:** Record provisional topic
  schema, prompt version, validation codes, retry policy and packet limit.
- **Tests passed/failed/skipped and unverified criteria:** Record exact commands
  and live-model limitations separately from deterministic fixtures.
- **Decisions/drift and unresolved risks:** Model quality is evaluated at the
  lifecycle level; structural validation does not claim semantic proof.
- **Next package and concrete inputs:** PTR-3 receives immutable provisional
  topics plus their cluster geometry, questions, memberships and bounded
  evidence.
- **Completion reconciliation:** All provisional outputs and retry/provenance
  conditions must hold.

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
- **Baseline rechecked on / drift discovered / resolution:** Recheck on entry.

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

- [ ] PTR-3-A1/A2: Implement deterministic candidate shortlisting and bounded
  reconciliation packets; avoid global all-pairs LLM work.
- [ ] PTR-3-A3/A4: Define structured equivalence/no-merge response and validate
  complete non-overlapping canonical partition plus canonical label shape.
- [ ] PTR-3-A5/A6: Persist canonical identity, antecedents, rationale and exact
  unioned memberships atomically; preserve question/evidence provenance.
- [ ] PTR-3-A7/A8: Integrate durable stage, replay/concurrency/recovery, stable
  identity/lineage, and scale fixtures across at least 50 question scopes.

| Acceptance ID | Observable condition (including relevant failure case) | Verification command/test | Result / date / environment / revision or dirty-tree context |
| --- | --- | --- | --- |
| PTR-3-A1 | Only geometrically/name-plausible neighbors enter an LLM packet; isolated topics bypass model comparison | Pure shortlist tests | pending |
| PTR-3-A2 | Packet size/candidate count is bounded and deterministic for hundreds of provisional topics | Scale-focused pure tests | pending |
| PTR-3-A3 | Equivalent cross-question fixtures merge; related, homonymous and opposing-position fixtures obey the PTR-0 rubric | Structured-client fixture tests | pending |
| PTR-3-A4 | Overlapping, unknown, duplicate or incomplete model groups are rejected without writes | PostgreSQL rollback tests | pending |
| PTR-3-A5 | Canonical membership equals the deduplicated union of antecedent memberships and contains no foreign evidence | PostgreSQL invariant tests | pending |
| PTR-3-A6 | Evidence, distinct-submission and question counts remain separately derivable after merge | PostgreSQL aggregate tests | pending |
| PTR-3-A7 | Crash replay, stale lease and concurrent worker cannot create a second partition or identity | PostgreSQL concurrency tests | pending |
| PTR-3-A8 | New and replacement runs retain stable topic lineage or record explicit split/merge/new relationships | PostgreSQL replacement tests | pending |

### Documentation and handoff

- **References to update:** Architecture and AC-02/03/04/08, schema/operations,
  API review contract if exposed.
- **Delivered behaviour and interface changes:** Record tables/functions,
  canonical identity, antecedent relationship, request version and scale bound.
- **Tests passed/failed/skipped and unverified criteria:** Record exact pure,
  PostgreSQL and migration commands.
- **Decisions/drift and unresolved risks:** Report over/under-merge evaluation;
  do not call theme similarity equivalence.
- **Next package and concrete inputs:** PTR-4 receives the one canonical topic
  partition, memberships, counts and lineage for the run.
- **Completion reconciliation:** All eight criteria and PTR-4 inputs must agree.

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
- **Baseline rechecked on / drift discovered / resolution:** Recheck on entry.

### Local contract

- **Inputs and outputs:** Canonical topics feed theme inference; zero or more
  reconciled themes result. Quality writes one immutable attestation containing
  integrity result plus total/classified/unclassified/noise evidence,
  provisional/canonical topic, theme, question and distinct-submission counts,
  thresholds, failures, policy version and input hash.
- **Invariants and transaction boundaries:** Themes link only canonical topics;
  no theme is not a failure. Classified evidence has canonical membership;
  unclassified evidence is frozen without one; categories reconcile to the
  frozen total. Attestation remains computed-only and immutable.
- **State transitions, leases, idempotency and concurrency:** Existing theme and
  quality leases apply. Retry cannot replace theme decisions or attestation.
- **Authorization, private/public data exposure:** Aggregate attestation is
  protected operational data; no raw evidence or prompts in public errors.
- **Failure/retry/recovery and rollout:** Integrity violations fail closed;
  incomplete semantic coverage produces an attested partial state rather than
  pretending completion or blocking every valid topic.
- **Compatibility and downstream package impacts:** PTR-5 database publication
  consumes the new attestation version. Old attestations remain valid history
  but cannot satisfy the new automatic policy.

### Work and acceptance

- [ ] PTR-4-A1–A3: Move theme inputs to canonical topics, preserve
  related-not-equivalent semantics, and make zero-theme materialization valid.
- [ ] PTR-4-A4–A6: Define coverage categories/counts, implement immutable gate
  v3 input/hash, and remove 0.80 accepted-attempt and minimum-theme conditions
  as publication blockers.
- [ ] PTR-4-A7/A8: Verify partial, complete and integrity-failure attestations,
  retries, immutability, privacy, and compatibility.

| Acceptance ID | Observable condition (including relevant failure case) | Verification command/test | Result / date / environment / revision or dirty-tree context |
| --- | --- | --- | --- |
| PTR-4-A1 | Theme inference sees canonical topics and their bounded evidence, never duplicate provisional antecedents | Structured-client and PostgreSQL tests | pending |
| PTR-4-A2 | Related topics can share a theme without being merged; equivalent topics appear once | Deterministic fixture tests | pending |
| PTR-4-A3 | One canonical topic or no related topic groups yields zero themes without publication failure | Pure and PostgreSQL tests | pending |
| PTR-4-A4 | Total = classified + unclassified + noise under the documented category rules | Pure/PostgreSQL aggregate tests | pending |
| PTR-4-A5 | Distinct submissions and questions are reported separately from evidence count | PostgreSQL tests | pending |
| PTR-4-A6 | At least one valid canonical topic can receive a passing partial attestation without 0.80 acceptance or a theme | Quality boundary tests | pending |
| PTR-4-A7 | Missing provenance, foreign membership, incomplete stage, or inconsistent counts fail closed | Failure/rollback tests | pending |
| PTR-4-A8 | One immutable attestation survives retry and exposes only bounded aggregate diagnostics | PostgreSQL immutability/API tests | pending |

### Documentation and handoff

- **References to update:** Architecture, AC-03/04/07/08, API/operations quality
  contract; current state waits for publication package.
- **Delivered behaviour and interface changes:** Record theme input identity,
  optional-theme behavior, metric/category definitions and gate version.
- **Tests passed/failed/skipped and unverified criteria:** Record exact commands.
- **Decisions/drift and unresolved risks:** Revalidate publication functions and
  current reader assumptions before PTR-5.
- **Next package and concrete inputs:** PTR-5 receives immutable passing
  partial/complete attestations and optional materialized theme revisions.
- **Completion reconciliation:** All coverage arithmetic and downstream gate
  assumptions must be verified.

## Package PTR-5: Publish partial runs and make backend states truthful

### Entry and scope

- **Objective and non-goals:** Atomically publish one cumulative partial or
  complete run and update backend readers to distinguish classified,
  unclassified-in-snapshot and pending evidence. Do not build admin UI.
- **Dependency outputs verified:** PTR-4 attestation/category contract and
  optional themes; current rollback/publication invariants.
- **Expected modules/files and owners:** New numbered migration replacing manual
  and automatic publication functions, `taxonomy_automation.py`,
  `taxonomy_status.py`, dashboard queries/routes/schemas, inputs, operations,
  generation, article validation as needed, migration/readiness checks, tests.
- **Applicable AC IDs / decisions:** AC-01–AC-09, ADR-0001 and ADR-0003.
- **Baseline rechecked on / drift discovered / resolution:** Recheck all
  publication and reader consumers on entry.

### Local contract

- **Inputs and outputs:** A ready run with a matching passing v3 attestation and
  durable automatic decision atomically supersedes the prior run and becomes
  the one publication. Responses expose publication coverage state and stable
  canonical topics; themes may be empty.
- **Invariants and transaction boundaries:** One published run; no direct status
  writes; publication decision, aliases/lineage/materialization and swap are
  atomic. Only evidence with canonical membership is classified. Frozen
  evidence without membership is unclassified; evidence outside the run is
  pending. Multi-query readers capture one run.
- **State transitions, leases, idempotency and concurrency:** Preserve current
  ready→published and published→superseded/rollback transitions, automatic
  idempotency and concurrent publication rejection.
- **Authorization, private/public data exposure:** Human mutation remains
  token-protected/default-off; automatic DB gate remains authoritative.
  Unclassified status exposes no raw model failure publicly.
- **Failure/retry/recovery and rollout:** Apply new migration with matching
  application images. Prior publication remains served until atomic success.
  Failed replacement remains inert; explicit rollback remains available.
- **Compatibility and downstream package impacts:** Add stable bounded API
  vocabulary rather than silently changing existing meanings. PTR-6 mirrors it
  in TypeScript and UI.

### Work and acceptance

- [ ] PTR-5-A1/A2: Replace DB manual/automatic publication and optional-theme
  materialization safely; preserve one-run swap/audit/rollback.
- [ ] PTR-5-A3/A4: Correct input taxonomy state and dashboard total/coverage
  queries; keep classified taxonomy lists limited to canonical memberships.
- [ ] PTR-5-A5: Update candidate/operations status so useful partial
  publication is not reported quality-blocked.
- [ ] PTR-5-A6: Permit topic-targeted generation with zero themes while freezing
  run and evidence provenance.
- [ ] PTR-5-A7: Verify fresh/populated upgrade, concurrency, rollback and all
  backend contracts.

| Acceptance ID | Observable condition (including relevant failure case) | Verification command/test | Result / date / environment / revision or dirty-tree context |
| --- | --- | --- | --- |
| PTR-5-A1 | Passing partial run atomically supersedes prior publication; failed/incompatible attestation cannot publish | PostgreSQL publication tests | pending |
| PTR-5-A2 | Zero-theme partial run publishes; aliases/lineage/audit are complete; rollback restores prior run | PostgreSQL tests | pending |
| PTR-5-A3 | Frozen evidence with canonical membership is classified; frozen evidence without it is unclassified; post-cutoff evidence is pending | Inputs API/PostgreSQL tests | pending |
| PTR-5-A4 | Dashboard reports total, classified, unclassified and noise without silently dropping categories | Dashboard API/PostgreSQL tests | pending |
| PTR-5-A5 | Operations/candidate status distinguishes partial publication, running replacement and integrity failure with bounded codes | API tests | pending |
| PTR-5-A6 | Topic generation succeeds from canonical evidence with no theme; foreign/unclassified evidence is rejected | Generation worker/API tests | pending |
| PTR-5-A7 | Fresh init, populated upgrade, concurrent swap, replay and rollback pass against disposable PostgreSQL+pgvector | Isolated Compose integration commands | pending |

### Documentation and handoff

- **References to update:** Architecture, current state, AC-03/04/06/08/09,
  API, operations, root README and migration markers.
- **Delivered behaviour and interface changes:** Record migration, response
  vocabulary, status codes, transition functions and deployment order.
- **Tests passed/failed/skipped and unverified criteria:** Record focused and
  isolated Compose outcomes; skipped DB tests are not acceptance.
- **Decisions/drift and unresolved risks:** Revalidate admin contract and public
  projection before PTR-6.
- **Next package and concrete inputs:** PTR-6 receives exact schemas/status
  codes, coverage counts, candidate details and generation behavior.
- **Completion reconciliation:** All DB/API consumers and PTR-6 assumptions
  must agree.

## Package PTR-6: Make partial taxonomy reviewable and usable in admin

### Entry and scope

- **Objective and non-goals:** Show accepted canonical topics, unresolved
  clusters, reconciliation provenance and truthful coverage in admin; keep
  article generation usable without themes. Do not expose protected candidate
  evidence or taxonomy internals at the public edge.
- **Dependency outputs verified:** PTR-5 backend schemas/status codes and
  generation contract; PTR-3 protected review provenance.
- **Expected modules/files and owners:** Taxonomy review/operations schemas and
  routes as required, `frontend/admin/src/api/`, navigation/pages/components,
  dashboard/generation state, frontend tests, public-edge denial tests.
- **Applicable AC IDs / decisions:** AC-03, AC-05–AC-07, AC-09; ADR-0003.
- **Baseline rechecked on / drift discovered / resolution:** Recheck on entry.

### Local contract

- **Inputs and outputs:** Typed API exposes partial/complete coverage, canonical
  topics, protected provisional/rejected cluster summaries, equivalence
  antecedents, optional themes, and bounded failure codes. UI differentiates
  published, partial, unclassified, pending, processing and failed states.
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

- [ ] PTR-6-A1–A3: Mirror taxonomy/coverage states and render totals plus clear
  partial/unclassified explanations.
- [ ] PTR-6-A4–A6: Add protected candidate review for accepted topics, rejected
  clusters and merge provenance without exposing raw audit payloads by default.
- [ ] PTR-6-A7–A9: Make topic browsing/recommendations/generation work with zero
  themes and preserve loading/empty/error/stale-response behavior.
- [ ] PTR-6-A10: Prove public edge cannot reach candidate/admin routes and
  approved projections remain unchanged.

| Acceptance ID | Observable condition (including relevant failure case) | Verification command/test | Result / date / environment / revision or dirty-tree context |
| --- | --- | --- | --- |
| PTR-6-A1 | Overview shows total/classified/unclassified/noise and labels partial publication accurately | Frontend state/component tests | pending |
| PTR-6-A2 | Input/evidence views distinguish classified, unclassified-in-snapshot and pending | Backend response + frontend tests | pending |
| PTR-6-A3 | Empty theme collection is normal while accepted topics remain browseable | Backend/frontend tests | pending |
| PTR-6-A4 | Authorized operator can inspect canonical topic evidence and antecedent provisional topics | Protected API + frontend tests | pending |
| PTR-6-A5 | Rejected/unresolved clusters show bounded reasons and support counts without implying their evidence is invalid | API/UI tests | pending |
| PTR-6-A6 | Missing/incorrect token fails closed and raw prompt/model payloads are absent | Security/API tests | pending |
| PTR-6-A7 | Recommendations include valid canonical topics from a partial run | API/frontend tests | pending |
| PTR-6-A8 | Topic-targeted generation freezes only canonical evidence and completes with no themes | Backend/frontend integration tests | pending |
| PTR-6-A9 | Loading, partial, empty, error, refresh and stale-response states are deterministic | Frontend tests/typecheck/build | pending |
| PTR-6-A10 | Public edge denies candidate/admin/API paths and approved article rendering remains projection-only | Public HTTP edge tests | pending |

### Documentation and handoff

- **References to update:** API reference and admin README; architecture/public
  docs only where exposure behavior changes.
- **Delivered behaviour and interface changes:** Record typed payloads, routes,
  auth, UI routes and empty/partial states.
- **Tests passed/failed/skipped and unverified criteria:** Record backend,
  frontend typecheck/test/build and public-edge HTTP evidence.
- **Decisions/drift and unresolved risks:** Revalidate the integrated journey and
  external-facing copy before PTR-7.
- **Next package and concrete inputs:** PTR-7 receives all deployed-local
  contracts and acceptance fixtures.
- **Completion reconciliation:** All ten criteria and exposure boundaries must
  be proven.

## Package PTR-7: Prove the complete partial-taxonomy lifecycle

### Entry and scope

- **Objective and non-goals:** Verify migration, Google Sheets/API ingestion,
  evidence preparation, coherent clustering, provisional labels,
  cross-question reconciliation, optional themes, partial publication, admin
  review and topic generation as one lifecycle. Do not deploy externally or
  delete application data.
- **Dependency outputs verified:** Every PTR-1–PTR-6 interface, migration,
  readiness marker, API/admin contract and test fixture.
- **Expected modules/files and owners:** `compose.test.yaml`, taxonomy journey
  harness/fixtures, migration upgrade tests, current reference documents and
  this plan.
- **Applicable AC IDs / decisions:** AC-01–AC-09; ADR-0001–0003.
- **Baseline rechecked on / drift discovered / resolution:** Recheck all
  predecessor evidence and current checkout before integration.

### Local contract

- **Inputs and outputs:** Disposable fresh and populated databases plus
  deterministic structured-model fixtures produce observable complete and
  partial journeys, migration/recovery evidence, and final documentation.
- **Invariants and transaction boundaries:** Test databases only; no application
  volume deletion. Journey asserts single published run, immutable provenance,
  truthful coverage, safe replacement and public-edge isolation.
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

- [ ] PTR-7-A1/A2: Prove fresh initialization and populated upgrade with
  matching runtime consumers and no historical mutation.
- [ ] PTR-7-A3/A4: Prove partial and complete automatic journeys, including
  equivalent cross-question merge, related-topic theme, and zero-theme case.
- [ ] PTR-7-A5: Prove Google Sheets/API ingestion to visible partial topic and
  topic-targeted generated article.
- [ ] PTR-7-A6: Prove failed replacement preserves prior publication and
  rollback/replay/concurrency invariants.
- [ ] PTR-7-A7/A8: Update every reference/contract, reconcile all acceptance
  evidence, archive the plan only after feature closure.

| Acceptance ID | Observable condition (including relevant failure case) | Verification command/test | Result / date / environment / revision or dirty-tree context |
| --- | --- | --- | --- |
| PTR-7-A1 | Fresh disposable PostgreSQL initializes all schema/functions and completes the new stage lifecycle | Full isolated Compose suite | pending |
| PTR-7-A2 | Populated pre-feature schema upgrades without rewriting prior runs, attestations, publications or articles | Populated-upgrade integration test | pending |
| PTR-7-A3 | Deterministic partial fixture publishes accepted canonical topics, explicit unclassified evidence and zero themes | Automatic taxonomy journey | pending |
| PTR-7-A4 | Cross-question equivalents merge once, related topics remain distinct and can form a theme | Journey fixture assertions | pending |
| PTR-7-A5 | Sheet/API evidence becomes a visible partial topic and supports evidence-grounded generation while public exposure stays approved-only | Cross-component HTTP acceptance | pending |
| PTR-7-A6 | Failed successor leaves prior publication served; replay/stale claim cannot corrupt it; explicit rollback restores prior run | PostgreSQL/Compose acceptance | pending |
| PTR-7-A7 | Backend, frontend typecheck/tests/build, and public-edge denial tests pass with no required skips | Exact commands recorded on current working tree | pending |
| PTR-7-A8 | Architecture/current state/API/operations/README/admin docs and ACs describe implemented behavior; plan evidence is internally consistent | Link review, plan reconciliation, `git diff --check` | pending |

### Documentation and handoff

- **References to update:** `README.md`, `docs/current-state.md`,
  `docs/architecture.md`, `docs/architecture-contracts.md`, `docs/api.md`,
  `docs/operations.md`, `frontend/admin/README.md`, ADR-0003 verification, and
  archive index at closure.
- **Delivered behaviour and interface changes:** Record final stage sequence,
  migrations, configuration/policy versions, schemas, UI and recovery.
- **Tests passed/failed/skipped and unverified criteria:** Record exact commands,
  dates, environment and working-tree revision; no inherited results.
- **Decisions/drift and unresolved risks:** Reconcile against PTR-F1–F6 and every
  package criterion. Extend the plan rather than silently omitting gaps.
- **Next package and concrete inputs:** None after verified feature closure;
  otherwise name the exact incomplete package and next action.
- **Completion reconciliation:** Feature closes only after all PTR packages,
  PTR-F1–F6, references, migration evidence and integrated journey pass.

## Feature closure

- **Integrated acceptance evidence:** Pending PTR-7-A1–A8 and reconciliation of
  PTR-F1–F6.
- **Temporary paths retired / intentional compatibility retained:** Pending.
  Historical immutable runs/attestations and the single-run reader boundary are
  intentionally retained; old lexical validation and gate-v2 behavior retire
  only for new versioned candidates after verified rollout.
- **Implemented / verified / merged / deployed status, separately:** Planned;
  none implemented, verified, merged or deployed by this documentation change.
- **Final status and archive reason/date, including any undelivered scope:**
  Active planned feature; archive only under DC-07 after completion, explicit
  deferral, cancellation or supersession.
