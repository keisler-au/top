# Batch taxonomy rebuild work packages

**Status: proposed.** This is the successor plan for taxonomy work after the
dashboard/article plan was completed and archived in
[`dashboard-article-work-packages-archive.md`](dashboard-article-work-packages-archive.md).
It does not describe functionality that is already live, and it must not
silently change the published taxonomy while it is being evaluated.

## Re-evaluated conclusion

The proposed architecture is appropriate for this repository's expected
hundreds-to-low-thousands scale:

```text
canonical evidence units
    -> embeddings
    -> input clustering
    -> literal, evidence-grounded topics
    -> topic centroid / candidate neighbourhoods
    -> LLM theme inference
    -> reviewed publication of one taxonomy run
```

It is not an extension of the current per-input workers. It replaces their
classification strategy and requires versioned, publishable taxonomy results.
The existing system is a useful substrate: it preserves source text and
segments, writes embeddings, has durable PostgreSQL queues, has structured LLM
validation, and retains theme-decision evidence. Its data model and scheduling
model are not sufficient for a corpus-wide rebuild.

### Current implementation and resulting change

| Concern | Current implementation | Required batch-taxonomy behavior |
| --- | --- | --- |
| Unit of analysis | An input and its segments are classified as each input completes. | Snapshot the complete canonical evidence corpus for a run. A segmented input contributes its segments; an unsegmented input contributes its original. |
| Topics | An LLM reuses or creates a string stored directly on an input or segment. | Clustering proposes membership; an LLM names and describes a cluster literally; the result has a durable topic identity and centroid. |
| Themes | The worker presents one existing topic at a time and rejects links to other topics. | Embedding similarity creates advisory multi-topic candidate groups; an LLM can select a subset, create overlap, or reject a group. |
| State | `topic` strings and current `theme_topics` links are live state. | A completed run is immutable candidate state. A single approved run is published live state. |
| Trigger | Every completed input queues a theme cycle. | A scheduler or operator starts one corpus snapshot rebuild; its lifecycle is independent of one input. |

The existing dashboard has another important constraint: topic identity is
currently `lower(btrim(topic))`, and article tags snapshot that string. A
rebuild can rename, split, merge, or retire topics. Therefore, converting to
topic IDs and retaining run provenance is required before automated publication.

## Principles and non-negotiable invariants

- Raw inputs, original segment text, question snapshots, and their existing
  embeddings remain immutable source evidence.
- The taxonomy view must use the same canonical-evidence rule as the dashboard:
  segments when an input has segments; otherwise the original. Never cluster an
  original alongside its own segments as separate observations.
- A topic name and description must be literally supported by its member
  evidence. It must not state a cause, explanation, or implication absent from
  that evidence.
- A theme is an explicit inference across topics. It may be supported by a
  subset of a candidate group and may overlap another theme; a clustering result
  never becomes a theme without an LLM decision and validation.
- One run sees a fixed evidence cutoff, embedding model, representation,
  clustering configuration, prompt versions, and model identifiers.
- No candidate run changes the dashboard, input details, recommendations, or
  article-generation scope. Publication is explicit and transactional.
- Existing articles and their frozen evidence/taxonomy snapshots remain
  historically accurate after a later taxonomy publication.

## Decisions to make before implementation

These are design gates, not details to defer until after migrations.

1. **Embedding representation for global clustering.** The current contextual
   vector is `Question: ... Answer: ...`. This is valuable for topic
   disambiguation but may make cross-question topic similarity reflect question
   wording. The prototype must compare it with a separately stored answer-only
   representation (or demonstrate that it is unnecessary). Do not overwrite the
   current embedding to run that comparison.
2. **Clustering policy.** Establish the tested HDBSCAN configuration, minimum
   cluster size, minimum samples, metric, and a defined policy for noise:
   unclustered, reviewed, or conservatively attached. HDBSCAN is a candidate,
   not a guaranteed production dependency.
3. **Publication model.** Adopt one current published run per organisation-wide
   taxonomy initially. Do not mix memberships from several runs in dashboard
   counts. Add filtered views later only with a revised product contract.
4. **Human approval.** The first production releases must require an operator
   to compare a candidate run and explicitly publish or reject it. Automatic
   nightly publishing is a later reliability decision, not the initial design.
5. **Topic continuity.** Decide how a candidate topic maps to a prior canonical
   topic: exact continuation, rename, split, merge, new, or retired. Preserve
   aliases and history; never infer continuity solely from a matching label.

## Delivery sequence

```text
TAX-WP0 experiment and evaluation
          |
          v
TAX-WP1 run-scoped taxonomy persistence
          |
          +--> TAX-WP2 clustering and representative selection
          |             |
          |             v
          |        TAX-WP3 literal topic materialization
          |             |
          |             v
          |        TAX-WP4 advisory theme inference and reconciliation
          |
          v
TAX-WP5 review, publication, and reader migration
          |
          +--> TAX-WP6 scheduled operation and observability
          |
          v
TAX-WP7 controlled rollout and historical migration
          |
          v
TAX-WP8 end-to-end verification and retirement
```

## TAX-WP0 — Offline feasibility experiment

**Status: required first. No live-schema or worker replacement.**

### Objective

Determine whether the embedding space forms sufficiently coherent topic
boundaries for this organisation's real responses, and whether a 4B model can
reliably perform the constrained topic and theme tasks.

### Work

- Export a read-only, reproducible corpus of canonical evidence units, including
  text, question context, existing embedding IDs, and a stable cutoff timestamp.
  Do not export secrets or mutate input status.
- Create a small, manually reviewed evaluation set covering common topics,
  near-boundary examples, multi-segment inputs, short answers, noise, and
  different questions/forms.
- Compare at least the present question-answer vectors with an answer-only
  candidate representation. Record whether question text creates false
  neighbours across topics.
- Trial HDBSCAN and at least one transparent baseline. Sweep only a small,
  documented parameter grid; record noise rate, cluster sizes, stability, and
  rerun agreement.
- For each candidate cluster, select three medoid/central examples plus one
  deliberately diverse member using a diversity method such as maximal marginal
  relevance. Deduplicate by original input.
- Have the LLM produce a literal name and short description. Review unsupported
  labels, over-broad labels, duplicate clusters, and missed semantic groups.
- Construct small, bounded topic-neighbourhood prompts for themes and evaluate
  whether inferred themes are useful, evidence-supported, distinct from broad
  topics, and reproducible.

### Deliverables and gate

- Versioned experiment report, dataset cutoff, configuration, prompts, model
  identifiers, and annotated findings.
- A proposed quality threshold for publication: label support, topic coherence,
  duplicate rate, noise rate, run-to-run stability, and human acceptance.
- A decision to proceed, revise representation/configuration, or retain the
  current incremental model. Do not start TAX-WP1 without this decision.

## TAX-WP1 — Run-scoped taxonomy data foundation

**Status: blocked on TAX-WP0 approval.**

### Objective

Add durable candidate-run storage without changing what the dashboard reads.

### Work

- Add `taxonomy_runs` with an immutable source cutoff; configuration and
  hashes; embedding, clustering, and LLM model identifiers; prompt versions;
  status (`pending`, `running`, `ready_for_review`, `published`, `rejected`,
  `failed`); timestamps; error summary; and operator decision metadata.
- Add run-local evidence membership, so a later arriving input cannot alter a
  completed run.
- Introduce first-class `topics` and run-scoped topic revisions/memberships.
  Store a normalized name, literal description, support count, centroid/vector,
  cluster diagnostics, representative evidence order, and continuity decision.
- Introduce run-scoped candidate themes and theme-to-topic links. Retain their
  LLM request/response, selected topic subset, rationale, and evidence scope.
- Add permanent topic aliases/lineage sufficient to represent rename, split,
  merge, retirement, and new concepts. IDs, not display names, become the
  future relationship key.
- Add an additional embedding representation only if TAX-WP0 demonstrates it
  is necessary. It needs representation/model/version-aware uniqueness; the
  present one-vector-per-target constraints must not be weakened casually.
- Write an additive migration and update the fresh-install snapshot. Keep all
  legacy topic-string data readable until TAX-WP5 completes.

### Acceptance criteria

- A run can be created, resumed after failure, and inspected without changing
  current `topic`, `themes`, or `theme_topics` rows.
- Every generated record points to one run and every decision is reproducible
  from stored evidence IDs and versioned configuration.
- Constraints prevent mixed-run membership and an invalid publication state.

## TAX-WP2 — Deterministic input clustering and representations

**Status: blocked on TAX-WP1.**

### Objective

Turn one frozen corpus into repeatable topic-cluster candidates.

### Work

- Implement a batch runner that loads only the run's canonical evidence and
  selected embedding representation. Validate dimensions, model identity, and
  missing vectors before clustering.
- Add the selected clustering library and its pinned transitive dependencies to
  the Python project and reproducible container build. Keep clustering logic
  independently unit-testable from PostgreSQL and the LLM.
- Persist clusters, membership confidence/probability where available, and
  explicit noise decisions. Use deterministic ordering and a seeded algorithm
  wherever the library supports it.
- Compute a normalized topic centroid from member input vectors; retain the
  original vectors as the source of truth. Never derive a topic vector by
  embedding only the LLM's label.
- Persist representative evidence: three central members and one diverse member
  by default, capped and deduplicated by original input. Preserve question and
  source context for interpretation.
- Make every threshold and sampling policy a recorded run configuration rather
  than an environment default with no provenance.

### Acceptance criteria

- Re-running the same frozen corpus/configuration produces equivalent
  persisted membership and representative selection, subject only to documented
  library nondeterminism.
- Noise, singleton, duplicate-source, missing-vector, and segmented-input cases
  have explicit tests and observable outcomes.

## TAX-WP3 — Literal topic naming, validation, and continuity proposals

**Status: blocked on TAX-WP2.**

### Objective

Materialize useful topics while preventing the model from turning labels into
analytical explanations.

### Work

- Send each cluster a bounded context: cluster statistics, question context,
  representative examples, and no untrusted instructions from raw evidence.
- Require a concise topic name and literal description. Validate structured
  output, label length, duplicate normalized names, direct support, and
  appropriate granularity. Retain the current topic reviewer pattern as a
  starting point, but make review cluster-aware.
- Detect near-duplicate candidate topics using centroid similarity and evidence
  overlap; send only candidate conflicts to a constrained reconciliation step.
- Propose, but do not automatically apply, continuity links to topics from the
  currently published run. Use evidence overlap and centroid similarity in
  addition to names.
- Mark poor, mixed, or unsupported clusters for review/noise rather than forcing
  a topic label.

### Acceptance criteria

- Every accepted topic has representative evidence that directly supports its
  name and description.
- Topic output contains no causal or outcome inference; failed validation is
  durable and reviewable rather than silently corrected in place.

## TAX-WP4 — Advisory theme grouping, inference, and reconciliation

**Status: blocked on TAX-WP3.**

### Objective

Infer themes from related topics without treating a geometric cluster as a
theme definition.

### Work

- Build bounded candidate neighbourhoods from normalized topic centroids. A
  topic may occur in several neighbourhoods; do not create a mandatory
  partition. Include topic name, literal description, count, and representative
  evidence, normally 3--5 items per topic.
- Ask the LLM to identify the higher-order message, implication, tension, need,
  or pattern; select exactly the supporting topic subset; and decline to create
  a theme when there is no meaningful inference.
- Allow one topic to support multiple themes. Permit a theme to contain a
  non-contiguous subset of a candidate neighbourhood.
- Validate that links reference only topics supplied to the prompt, that the
  rationale is supported by those topics/evidence, and that a theme adds
  explanatory value beyond merely rephrasing a topic label.
- Reconcile duplicates and overlaps in a final bounded pass. This may merge
  candidate themes, but it must retain all antecedent decisions and never
  destroy candidate records.
- Replace the current single-topic theme-worker constraint only after this run
  model is proven. Its existing `new`/`reuse`/`update`/`merge` live mutations
  are not an appropriate first-stage candidate workflow.

### Acceptance criteria

- A theme decision records the whole candidate context, selected topics, and
  explanation.
- Tests prove subset selection, topic overlap across themes, rejection of an
  incoherent neighbourhood, and prevention of unsupported topic links.

## TAX-WP5 — Review, publication, and reader migration

**Status: blocked on TAX-WP4. This is the highest-risk package.**

### Objective

Make one reviewed candidate run the live taxonomy without corrupting existing
dashboard counts or article provenance.

### Work

- Add operator APIs and a minimal review surface to compare a candidate run with
  the published run: cluster/topic counts, noise, lineage proposals, changed
  membership, candidate themes, representative evidence, and validation flags.
- Support explicit approve/publish and reject actions with optimistic state
  checks. Publishing must be a short transaction; LLM calls and clustering
  never occur inside it.
- Move dashboard, input-detail, recommendation, and generation target queries
  from topic strings to topic IDs in the published run. Preserve legacy string
  reads during a staged compatibility period.
- Migrate `theme_topics` to topic-ID links or replace it with a published-run
  projection. Do not depend on case-insensitive string joins after publication.
- Extend article tags to retain a stable topic ID and a display-name snapshot.
  Existing article rows retain their historical string snapshots; approved
  articles are never retagged merely because a later run publishes.
- Define downstream behavior for evidence that is present but not published:
  it remains visible as unclassified/pending and is excluded from live taxonomy
  aggregates until a published run covers it.

### Acceptance criteria

- Rejecting or failing a candidate run cannot alter live API responses.
- Publishing updates all live taxonomy readers consistently, without mixed-run
  counts.
- Historical article detail and evidence provenance remain unchanged after a
  topic rename, split, merge, or retirement.

## TAX-WP6 — Scheduled rebuild operation and observability

**Status: blocked on TAX-WP5.**

### Objective

Replace per-input topic/theme work with a durable corpus-run scheduler.

### Work

- Add a taxonomy-run queue or scheduler; do not overload `worker_jobs`, whose
  identity and uniqueness are `(job_type, original_input_id)`.
- Provide an operator-triggered run and a configured nightly schedule. Enforce
  one active run with a database lock/constraint, leases, retries, and safe
  recovery after a worker restart.
- Define the ingestion boundary: eligibility, segmentation, and embeddings stay
  incremental; completed vectors wait for the next batch run. Retire the
  per-input topic and theme queue triggers only after the published-run reader
  path is live.
- Expose bounded operational metrics: active run state and age, snapshot size,
  embedding completeness, cluster/noise counts, validation failures, candidate
  themes, review backlog, publication age, and last successful run. Never
  expose raw responses or prompts in the operations endpoint.
- Document configuration, manual recovery, cancel/retry policy, model upgrades,
  and rollback to the prior published run.

### Acceptance criteria

- A late input is either wholly outside a run or wholly inside it; it never
  enters a run halfway through.
- Concurrent services cannot run or publish two taxonomy rebuilds at once.
- The previous published run can be restored without recomputing source data.

## TAX-WP7 — Controlled rollout and legacy migration

**Status: blocked on TAX-WP5 and TAX-WP6.**

### Objective

Adopt the batch pipeline without breaking existing taxonomy readers or hiding
quality regressions.

### Work

- Backfill a first candidate run from the current corpus and compare it with the
  legacy string taxonomy. Produce explicit new/renamed/split/merged/retired
  mappings and unresolved cases for review.
- Run the new pipeline in shadow mode for multiple scheduled cycles. Compare
  run stability, review acceptance, taxonomy drift, and user-facing coverage
  metrics before first publication.
- Publish a reviewed run, retain the legacy workers and data behind a rollback
  path for an agreed observation period, then remove obsolete workers, queue
  jobs, prompts, and string-only writes in a later migration.
- Revise the dashboard product contract, architecture, operations guide,
  API schemas, and article-generation contract to reflect topic IDs, run scope,
  publication semantics, and taxonomy history.

### Acceptance criteria

- The first published run has a signed-off comparison report and a tested
  rollback path.
- There is no interval in which a live reader combines legacy topic strings
  with a partial candidate-run result.

## TAX-WP8 — Verification and quality governance

**Status: spans all packages; final release gate.**

### Required coverage

- Database migrations, run-state constraints, membership provenance, lineage,
  publication atomicity, rollback, and legacy-data preservation.
- Deterministic clustering fixtures, representative-selection tests, noise and
  segmentation behavior, vector/model mismatch handling, and centroid
  normalization.
- Topic and theme structured-output validation, prompt-injection resistance,
  support/granularity checks, subset/overlap behavior, and reconciliation.
- Dashboard, input-detail, recommendation, and article-generation integration
  tests against a real PostgreSQL schema for both the legacy and published-run
  paths during migration.
- Operator review and publish user-flow tests, accessibility checks, and
  confirmation that source text is not exposed in aggregate operations output.
- Quality monitoring after publication: acceptance rate, taxonomy drift,
  cluster stability, noise rate, duplicate-topic rate, stale publication age,
  and sampled human evidence review.

### Release gate

The old incremental topic and theme workers may be retired only when the new
pipeline has passed the TAX-WP0 thresholds, produced stable shadow runs, been
published and rolled back successfully in a representative environment, and
has all live taxonomy readers on the run-scoped topic-ID model.

## Explicitly retained and replaced components

| Retain | Replace or evolve |
| --- | --- |
| Immutable inputs, segmentation, question snapshots, and evidence provenance | Per-input LLM topic assignment as the source of truth |
| Embedding client and vector storage, subject to representation experiment | `topic` string as the taxonomy identity |
| Structured LLM client and validation/audit patterns | One-topic-at-a-time theme context and its single-topic validation rule |
| PostgreSQL transactions, advisory-lock patterns, retry principles, and operations hygiene | Input-scoped `themes` queue as the rebuild scheduler |
| Article frozen-evidence and revision guarantees | Case-insensitive string joins between inputs, themes, dashboard queries, and article tags |

## Not in scope until this plan is established

- Per-form or per-question published taxonomies.
- Automatic, unreviewed nightly publication.
- Rewriting historic approved articles to use current topic names.
- Treating HDBSCAN output, cosine thresholding, or an LLM label as sufficient
  evidence of a theme without the review and publication model above.
