# ADR-0001: Cumulative membership for replacement taxonomy runs

- Status: accepted
- Date: 2026-09-22
- Scope/authorization: User decision on evidence continuity for taxonomy replacement; this record does not authorize implementation, deployment, migration, or live recovery.
- Affected AC IDs and packages: AC-02, AC-03, AC-04; TR-2 and TR-3 in [the completed recovery plan](../archive/taxonomy-recovery-and-lifecycle-repair-work-packages.md).
- Supersedes / superseded by: Supersedes the post-cutoff-only replacement membership proposed in the [archived automatic-taxonomy plan](../archive/automatic-taxonomy-work-packages.md); none.

## Context and evidence

Production readers resolve exactly one published run. Current automatic snapshots use the previous publication cutoff to select only newer canonical targets. When such a run replaces the publication, earlier classified evidence disappears from current readers. The [first-run diagnosis](../reviews/taxonomy-first-run-diagnosis-2026-09-22.md#tfr-09--high-design-conflict--replacement-publication-loses-historical-coverage) records this gap. Its TFR-07 finding also shows that evidence prepared after a cutoff can be missed when the target was created earlier.

`taxonomy_snapshots.create_taxonomy_snapshot` owns frozen canonical membership. `taxonomy_automation` owns admission and the durable decision; the clustering and downstream stages build topics from that frozen membership. Published-run readers, stable-ID reconciliation, article generation, and dashboard status consume the resulting single run.

## Decision and alternatives

Every automatic replacement candidate selects all eligible canonical evidence through its database snapshot cutoff. Every selected target must have an embedding available by that cutoff and satisfy the snapshot's model, representation, and dimension validation. Incompatible or missing vectors block the candidate; they are not silently excluded. The candidate reclusters that complete frozen set and derives topics from those clusters. A later publication replaces the served taxonomy only after the existing quality and publication gates pass. The previous publication remains served while a candidate is building or fails.

The previous publication cutoff may determine whether **newly ready evidence** warrants another candidate and when to debounce it. It must not limit replacement snapshot membership. This includes evidence whose input or segment predates the previous cutoff but whose embedding became ready afterward. Existing frozen runs and their audit records remain immutable.

We considered post-cutoff-only membership with explicit carry-forward of previous classifications and taxonomy state. That would need a separate merge and lineage model to preserve historical coverage in one published run. Cumulative replacement matches the current single-run reader contract and lets each topic reflect the latest complete embedding clusters. The cost is reclustering, naming, and quality review over the growing evidence set on every replacement; topic membership and labels can change between runs, with stable identity resolved by existing reconciliation.

## Consequences and transition

TR-2 must separate the new-evidence trigger from cumulative snapshot selection, using the canonical selector for admission and creation. The decision identity and retry path must continue to refer to one immutable cumulative snapshot, suppress unchanged failed evidence, and allow a materially changed complete set to produce a successor. Keep the existing cutoff and decision records for audit; do not rewrite past runs or attestations. Schema or policy-version changes, if needed for safe replay and idempotency, belong to the implementation package with populated-upgrade evidence.

Any currently published delta-only run remains valid historical data but lacks earlier coverage. A future passing cumulative replacement restores current-reader coverage; failed candidates cannot replace it. Deployment and live recovery require a separately authorized, tested change. There is no data deletion or quality-gate bypass in this decision.

## Verification and contract updates

Implementation evidence must show a second automatic candidate includes earlier canonical evidence plus newly ready evidence, including a late embedding for a pre-cutoff target; clustering and topic membership derive from that cumulative snapshot; a failed gate preserves the previous publication; unchanged evidence does not loop; and replay preserves the frozen decision. Use real PostgreSQL+pgvector integration tests and an automatic worker-to-publication journey for the changed lifecycle.

This decision updates [AC-03](../architecture-contracts.md#ac-03--taxonomy-visibility-and-publication) and [the completed recovery plan](../archive/taxonomy-recovery-and-lifecycle-repair-work-packages.md). Architecture, operations, API, and current-state references must be reviewed when implementation changes running behaviour; this accepted design alone does not claim that behaviour is deployed.
