# ADR-0003: Partial taxonomy publication and cross-question topic reconciliation

- Status: accepted
- Date: 2026-09-28
- Scope/authorization: The user selected partial publication (scope 2),
  cross-question topic reconciliation, required question context for every
  input, and published-run topic/theme associations without an input taxonomy
  state. This decision authorizes planning and future implementation packages;
  it does not claim that the running application already implements the design.
- Affected AC IDs and packages: AC-02, AC-03, AC-04, AC-06, AC-08, AC-09;
  PTR-0 through PTR-8 in [the completed plan](../archive/partial-taxonomy-and-reconciled-topic-work-packages.md).
- Supersedes / superseded by: Refines the whole-run quality policy without
  changing ADR-0001's cumulative single-run membership or ADR-0002's current
  compatibility rules; none.
- Implementation status: PTR-0 through PTR-8 are complete in source.
  Migration 044 and the matching runtime passed fresh, populated,
  fail-closed, worker-concurrency, pgvector, and public-edge verification in
  the disposable Compose stack on 2026-09-30. PTR-3's bounded partition,
  membership union, lease/replay/concurrency and lineage checks plus populated
  migration 046 passed on 2026-10-08. PTR-4 optional themes, gate-v3 coverage,
  exact trace checks, protected diagnostics and populated migration 047 passed
  on 2026-10-08. PTR-5 publication/readers and PTR-6 admin/generation passed
  their disposable checks on 2026-10-09. PTR-7 replacement, rollback and
  historical isolation passed 301 tests without skips on fresh disposable
  PostgreSQL and rebuilt API/public edge on 2026-10-09. PTR-8 completed on
  2026-10-10 with 302 backend tests without skips, 13 populated-upgrade checks,
  frontend typecheck/tests/build, and the full Sheets/API ingestion, real-
  embedding, automatic partial/full publication, generation, approval and
  public-edge journey. Failed successor, publication replay, rollback and
  generated article evidence provenance passed; all PTR-F1–F6 criteria closed. These are
  preserved dirty-checkout results, not merge or live deployment evidence.

## Context and evidence

The running pipeline freezes one cumulative evidence snapshot, clusters every
selected vector, asks an LLM to name each cluster, infers themes, and publishes
the run only when one aggregate release attestation passes. Release gate v2
requires at least 80% of naming attempts to be accepted and at least one
reconciled theme. A failure therefore withholds every accepted topic.

Read-only inspection of local run 2 found 38 clustered evidence items in three
clusters and no noise. One name was accepted and two were rejected, so the
whole run remained unavailable. The two rejections were caused by exact token
overlap between each generated description and four representatives, not by an
individual review of all 28 affected evidence items. The accepted housing
label also passed partly through incidental words such as `and` and `the`, even
though its ten-member cluster contained several distinct project reactions.
Exact word overlap therefore produces both false rejection and false
acceptance and is not a semantic-quality boundary.

Each observed cluster corresponded exactly to one form question. Current
contextual embeddings include the complete question and answer, so repeated
question text can dominate similarity. The current run nevertheless had high
member-to-centroid similarity and separated centroids. A radius check over the
same representation would not alone prove that clusters are specific answer
concepts. The implementation must evaluate an answer-focused, question-aware
clustering representation before fixing thresholds.

`topic_revisions` already materializes only accepted naming attempts, while
rejected attempts remain durable. The missing boundaries are provisional-topic
reconciliation, run-level topic coverage, optional themes, and input readers
that derive topic and theme associations only from the published run. The
current `taxonomy_state` field adds a second interpretation layer that is not
needed: an input either has associations in the published run or it does not.

## Decision and alternatives

Retain one immutable cumulative taxonomy run as the publication, rollback, and
reader-consistency boundary. A run may be published with partial topic coverage
when it has at least one publishable canonical topic. The percentage of evidence
with a topic is reported but is not a publication threshold. Publication
exposes only validated canonical topics and their memberships. Run-level coverage is
queryable as total evidence, evidence with a canonical topic, evidence without
a canonical topic, topic, question, and distinct-submission counts. Internal
cluster outcomes may record why evidence has no topic, but they are not input
states or separate reader-facing coverage categories. Full topic coverage means
that every evidence item in the run has a topic; partial topic coverage means
that at least one does not. Both are finished runs and may be published.

Every input has immutable question context. Ineligible inputs remain recorded
but receive no embedding and never enter taxonomy snapshots. Eligible evidence
is embedded once per selected representation and reused by cumulative taxonomy
runs; routine runs recluster it rather than embedding it again.

Inputs have no taxonomy classification state. `topics` and `themes` are a
projection of exactly one published run and may be empty. Evidence created
after that run's cutoff simply has no association in that run; it does not need
a `pending` label. A later publication may add, remove, or change an input's
topic and theme associations without mutating the input or historical runs.

Topic construction has two levels:

1. Form answer-discriminating clusters within a question scope using the
   selected contextual embedding space. A calibrated, versioned policy checks cluster cohesion,
   separation, membership confidence, and stability before labelling. Question
   context remains available to the labelling model, but the clustering
   representation must demonstrate that identical question text does not hide
   distinct answer concepts.
2. Ask the configured structured LLM to label each passing cluster from a
   deterministic bounded evidence packet. Supply every member when the cluster
   has at most 40 eligible evidence items; otherwise prefer up to 30 central
   and 10 farthest-first diverse members, deduplicating original inputs where
   possible and respecting a 32,768-byte serialized evidence-object limit. A
   complete at-most-40 packet or the required 30 central items fails closed
   when it cannot fit; evidence is not silently truncated. The LLM owns semantic
   interpretation. Deterministic validation owns JSON shape,
   non-empty and bounded fields, a 1-to-8-word name, exact normalized-name
   collisions, evidence links, and traceability to the model request. It does
   not use shared wording as a proxy for meaning.

After provisional topics exist, a durable topic-reconciliation stage considers
plausible cross-question equivalents. Deterministic centroid/name similarity
shortlists bounded neighborhoods; the LLM sees names, descriptions, question
context, support counts, and bounded evidence. It may merge only equivalent
topics that can share one label without losing a meaningful distinction.
Merely related topics remain separate and may later share a theme. The backend
validates a non-overlapping partition, preserves every provisional topic and
decision as immutable antecedent provenance, assigns one canonical identity,
and unions the antecedents' evidence memberships without copying or inventing
evidence.

For reconciliation, the same specific concept is equivalent when one neutral
canonical label can preserve its evidence, even when respondents express
opposing positions about that concept. The positions remain visible in the
antecedent descriptions and evidence. Different concepts in the same domain
are merely related and remain separate; concepts in different domains are
distinct. The model applies this semantic rubric, while deterministic code
validates the resulting non-overlapping partition and links.

Theme inference consumes canonical topics. Themes express broader relationships
between distinct topics and are optional: no-theme is a valid result when too
few related canonical topics exist. The release attestation remains immutable
and server-computed. It blocks publication only when processing is incomplete
or its stored results contradict one another: for example, a topic refers to
evidence outside the run, a required trace record is absent, or coverage counts
do not add up. It reports topic coverage but does not require a minimum coverage
percentage, accepted-attempt ratio, or theme count.

PTR-0 selected `partial-topic-policy/v1`: reuse the current 768-dimensional
`question-answer` vectors, cluster only within one immutable question using
HDBSCAN (`min_cluster_size=2`, `min_samples=1`), and require mean centroid
cohesion >=0.95, nearest-centroid separation >=0.08 when another cluster
exists, membership-probability p10 >=0.60, and HDBSCAN density persistence
>=0.05. The [calibration record](../reviews/ptr0-representation-policy-calibration-2026-09-29.md)
defines the formulae, sensitivity, packet bound, evidence and limitations.
Changing the model or representation requires a new calibrated policy version.

We considered merely lowering or removing the 0.80 threshold. That would make
the current input API retain a redundant taxonomy state, retain the mandatory-
theme database failure, and leave question-dominated clusters unexamined. We
considered keeping `classified`, `unclassified`, and `pending` input states,
but those labels duplicate facts already expressed by the published run and
its memberships. We considered independent per-topic publication across runs.
That would require readers to combine mutable mixtures of snapshots and would
substantially complicate lineage, rollback, article provenance, and consistent
reads. A single partial run preserves the existing atomic snapshot boundary.

We also considered one global LLM merge over every provisional topic. That
does not scale predictably and encourages broad over-merging. Similarity-based
shortlisting plus bounded reconciliation neighborhoods keeps model work near
the plausible equivalence graph instead of all topic pairs.

## Consequences and transition

The stage sequence gains durable provisional-topic and topic-reconciliation
outputs before theme inference. Existing frozen runs, naming attempts,
attestations, publications, article snapshots, and the immutable legacy archive
remain unchanged. A numbered migration must add the new provenance and
publication/coverage contracts and replace database publication functions;
already-applied migrations are never edited. Old application images must not
write the new lifecycle after that migration, so deploy order is migration plus
matching scheduler/API/admin images, followed by a new versioned cumulative
candidate. Recovery keeps the prior publication until the successor passes its
new attestation; a failed partial candidate remains inert.

PTR-0 selected the existing contextual vector within an immutable question
scope, so no second vector or representation backfill is required. PTR-1 must
still version the policy and reject vectors whose model, dimension, or
representation does not match it.
Question wording and original answers remain immutable evidence. Model prompts
and selected evidence IDs remain bounded, durable provenance; arbitrary source
or model text must not enter routine logs or public errors.

The input API removes `taxonomy_state`, retains evidence-processing `status`,
and returns topic/theme associations plus published-run provenance. Requiring
question context needs request validation, an audit of existing questionless
rows, and a numbered migration before making `original_inputs.question_id`
non-null; historical wording must never be invented. Dashboard coverage reports
run-level evidence with and without canonical topics. Topic generation may
target a canonical topic with evidence even when the run has no themes.
Approved article projections remain immutable and public rendering continues
to expose only approved articles and their revision-scoped display snapshots.

## Verification and contract updates

PTR-0 must produce a reproducible, privacy-safe evaluation showing cluster
cohesion, separation, question concentration, stability, representative
coverage, and the chosen thresholds/representation on representative corpora.
Pure tests must cover deterministic selection, prompt bounds, structural
validation, candidate shortlisting, equivalence partition validation, and
coverage arithmetic. PostgreSQL+pgvector tests must cover required question
identity, immutable antecedent provenance, membership union, no double
assignment, replay, stale leases, partial publication, optional themes,
rollback, replacement, distinct submission counts, empty associations, and
association changes across published runs. The isolated Compose journey must
prove Sheets/API evidence through partial publication, topic browsing, and
topic-targeted article generation.

Implementation packages update AC-02, AC-03, AC-04, AC-06, AC-08, and AC-09,
plus architecture, current state, API, operations, root README, and admin
documentation in the same changes as their affected consumers. This accepted
design is not evidence that any runtime behaviour has shipped.

PTR-5 implementation evidence records migration 048's current v3 attestation
checks, serialized atomic swaps with competing-candidate rejection/retry,
same-run replay and idempotent audited rollback. The input
wire contract now removes `taxonomy_state`; dashboard/operations expose exact
published-run coverage. Generation reads one database snapshot during job
creation and validates persisted topic tags against its recorded run after
replacement. This implements the accepted publication/reader boundary without
changing editorial approval or public exposure. See the active work-package
plan for commands, outcomes and deployment limits.
