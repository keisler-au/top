# ADR-0003: Partial taxonomy publication and cross-question topic reconciliation

- Status: accepted
- Date: 2026-09-28
- Scope/authorization: The user selected partial publication (scope 2) and
  requested a future implementation plan coordinating semantic cluster
  labelling with cross-question topic reconciliation. This decision authorizes
  planning and future implementation packages; it does not claim that the
  running application already implements the design.
- Affected AC IDs and packages: AC-02, AC-03, AC-04, AC-06, AC-08, AC-09;
  PTR-0 through PTR-7 in [the current plan](../work-packages.md).
- Supersedes / superseded by: Refines the whole-run quality policy without
  changing ADR-0001's cumulative single-run membership or ADR-0002's current
  compatibility rules; none.

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
reconciliation, explicit partial coverage, optional themes, and reader states
that distinguish classified, unclassified-in-snapshot, and not-yet-snapshotted
evidence. Current input readers incorrectly treat any evidence present in a
published snapshot as classified even if it has no topic membership.

## Decision and alternatives

Retain one immutable cumulative taxonomy run as the publication, rollback, and
reader-consistency boundary. A run may be published with partial topic coverage
when it has at least one publishable canonical topic. Publication exposes only
validated canonical topics and their memberships. Evidence in the frozen run
without a canonical topic remains explicitly unclassified; evidence after the
cutoff remains pending. Coverage is truthful and queryable as total,
classified, unclassified, noise, topic, question, and distinct-submission
counts. A partial run must never be presented as complete.

Topic construction has two levels:

1. Form answer-focused clusters within a question scope using one versioned
   embedding space. A calibrated, versioned policy checks cluster cohesion,
   separation, membership confidence, and stability before labelling. Question
   context remains available to the labelling model, but the clustering
   representation must demonstrate that identical question text does not hide
   distinct answer concepts.
2. Ask the configured structured LLM to label each passing cluster from a
   deterministic bounded evidence packet. Supply every member when the cluster
   has at most 40 eligible evidence items; otherwise prefer up to 30 central
   and 10 farthest-first diverse members, deduplicating original inputs where
   possible and respecting a configured serialized-input limit. The LLM owns
   semantic interpretation. Deterministic validation owns JSON shape,
   non-empty and bounded fields, a 1-to-8-word name, exact normalized-name
   collisions, evidence membership, and provenance. It does not use lexical
   overlap as a proxy for meaning.

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

Theme inference consumes canonical topics. Themes express broader relationships
between distinct topics and are optional: no-theme is a valid result when too
few related canonical topics exist. The release attestation remains immutable
and server-computed, but it reports topic validity and coverage instead of
requiring an aggregate accepted-attempt ratio or at least one theme. Exact
policy thresholds and the clustering representation are calibration outputs of
PTR-0 and must be versioned; this ADR does not invent them.

We considered merely lowering or removing the 0.80 threshold. That would make
the current input API misreport rejected evidence as classified, retain the
mandatory-theme database failure, and leave question-dominated clusters
unexamined. We considered independent per-topic publication across runs. That
would require readers to combine mutable mixtures of snapshots and would
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

The implementation must decide, from PTR-0 evidence, whether answer-focused
clustering replaces the current taxonomy vector or requires a second durable
representation. If another vector per target is required, its identity,
backfill, storage, and compatibility migration must be delivered together.
Question wording and original answers remain immutable evidence. Model prompts
and selected evidence IDs remain bounded, durable provenance; arbitrary source
or model text must not enter routine logs or public errors.

API consumers gain an explicit partial-coverage state and an unclassified
in-snapshot evidence state. Dashboard totals must not silently count only
classified evidence. Topic generation may target a canonical topic with
evidence even when the run has no themes. Approved article projections remain
immutable and public rendering continues to expose only approved articles and
their revision-scoped display snapshots.

## Verification and contract updates

PTR-0 must produce a reproducible, privacy-safe evaluation showing cluster
cohesion, separation, question concentration, stability, representative
coverage, and the chosen thresholds/representation on representative corpora.
Pure tests must cover deterministic selection, prompt bounds, structural
validation, candidate shortlisting, equivalence partition validation, and
coverage arithmetic. PostgreSQL+pgvector tests must cover immutable antecedent
provenance, membership union, no double assignment, replay, stale leases,
partial publication, optional themes, rollback, replacement, distinct
submission counts, and truthful input states. The isolated Compose journey must
prove Sheets/API evidence through partial publication, topic browsing, and
topic-targeted article generation.

Implementation packages update AC-02, AC-03, AC-04, AC-06, AC-08, and AC-09,
plus architecture, current state, API, operations, root README, and admin
documentation in the same changes as their affected consumers. This accepted
design is not evidence that any runtime behaviour has shipped.
