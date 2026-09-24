# ADR-0002: Mixed answer representations in automatic taxonomy

- Status: accepted
- Date: 2026-09-23
- Scope/authorization: TR-2 repair of the generic/contextual first-run failure under the user's package-completion instruction.
- Affected AC IDs and packages: AC-02, AC-03, AC-08; TR-2 and TR-3 in [the completed recovery plan](../archive/taxonomy-recovery-and-lifecycle-repair-work-packages.md).
- Supersedes / superseded by: Clarifies the representation field described in the [question-context plan](../archive/question-context-implementation-plan.md); none.

## Context and evidence

The embedding worker records `answer-only` for generic inputs and `question-answer` for contextual inputs. Both use the configured embedding model and vector dimension. The [first-run diagnosis](../reviews/taxonomy-first-run-diagnosis-2026-09-22.md) found that automatic admission counted only `question-answer` rows while snapshot validation rejected a mix. Generic-only installations could not begin, and mixed installations could fail after admission. The prior question-context contract treats representation as descriptive within one embedding space.

## Decision and alternatives

Automatic snapshots use the versioned `mixed` representation policy. It accepts exactly `answer-only` and `question-answer` embeddings when the configured embedding model and dimension match. It freezes every eligible canonical target, including both forms. Other representation values remain invalid. The run records `mixed` as its validation policy; each source embedding retains its actual representation for provenance. Manual snapshots that request a specific representation continue to require an exact match.

We considered filtering generic evidence or creating separate taxonomies. Both would make one published taxonomy incomplete. We also considered dropping representation validation entirely, which would admit unknown formats without evidence of compatibility. The explicit two-value policy preserves coverage and a bounded validation boundary.

## Consequences and transition

TR-2 changes admission, snapshot validation, and clustering's frozen-run reader together. The automatic policy defaults to version 2, with a minimum of three rows, `min_cluster_size=3`, and `min_samples=2`. Existing frozen runs and old reserved decisions retain their original provenance and membership mode; migration 042 adds replay metadata without rewriting them. A new cumulative passing run can replace a prior delta-only publication through the existing database gate. TR-3 deployed a matching image and migrations 042–043 after separate live-recovery authorization; this decision itself authorized no live mutation.

## Verification and contract updates

TR-2's PostgreSQL+pgvector tests cover generic-only, mixed, and incompatible vectors; the clustering reader accepts the frozen mixed set. A real three-row clustering check verifies the configured minimum does not raise before the quality stage. The package record holds fresh-install, populated-upgrade, backend, and frontend verification evidence.

[AC-02](../architecture-contracts.md#ac-02--evidence-and-identity) is updated for this compatibility rule. Reference documents describe the implemented source after verification; this decision alone is not deployment evidence.
