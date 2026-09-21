# Documentation guide

Reference documents describe implemented behaviour. The architecture and
delivery contracts govern new work; when a delivery plan is active,
`docs/work-packages.md` records its approved scope and sequence. Historical plans
are retained in the archive and are never instructions for new work.

Agents start with [AGENTS.md](../AGENTS.md). For a new feature, read the
[architecture contracts](architecture-contracts.md) and
[delivery contracts](delivery-contracts.md), then use the
[feature/package template](templates/feature-plan.md). Small changes use the
short contract in the delivery guide. Boundary changes use the
[architecture decision template](templates/architecture-decision.md).

## Current documentation set

| Document | Use it for | Update when |
| --- | --- | --- |
| [Root README](../README.md) | Project purpose, local development, service startup, and the concise operator entry point. | The supported developer workflow, service topology, or primary documentation entry point changes. |
| [Current state](current-state.md) | Concise deployed batch-taxonomy boundary and remaining programme. | The production taxonomy, publication, archive, or delivery boundary changes. |
| [Architecture](architecture.md) | Components, ownership, persistence boundaries, and processing flows. | A component, data owner, runtime flow, or system boundary changes. |
| [Architecture contracts](architecture-contracts.md) | Stable AC IDs, implementation owners, invariants and verification obligations. | An architectural decision changes a boundary or invariant. |
| [Delivery contracts](delivery-contracts.md) | Feature planning, package entry, daily resumption, evidence and handoff. | The delivery workflow changes. |
| [Architecture baseline review](reviews/architecture-baseline.md) | Evidence and known alignment gaps as of 2026-09-21; not an active backlog. | Preserve as a dated review; link subsequent resolution evidence when available. |
| [API reference](api.md) | Implemented HTTP endpoints and stable request/response behaviour. | A route, schema, authentication boundary, status, or compatibility behaviour changes. |
| [Operations](operations.md) | Implemented deployment, migration, worker, recovery, backup, and diagnostic procedures. | Compose, configuration, migrations, queues, recovery, or operational security changes. |
| [Admin dashboard README](../frontend/admin/README.md) | Dashboard development, build, test, and user-interface integration guidance. | The admin build, test, routes, or API integration changes. |
| [Work-package archive](archive/work-packages.md) | Index of completed, deferred, and superseded plans. | A current plan completes, is deferred, or is superseded. |

## Current delivery pipeline

There is no active work-package document. Current-state references describe
automatic taxonomy delivery as implemented: eligible evidence creates a durable candidate, the
scheduler processes it, and a passing immutable quality attestation promotes it
without routine operator action. Batch taxonomy remains the sole production
taxonomy; the legacy incremental system survives only as an immutable audit archive.
The [baseline review](reviews/architecture-baseline.md#r2--high-delivery-risk-completion-records-disagree)
records conflicting completion metadata in the archived automatic-taxonomy
plan. Its status must be reconciled against acceptance evidence before being
used as proof of completion.

The completed batch-taxonomy/public-website delivery plan, its source public
website proposal, and the operational-reliability and question-context plans
are archived. The legacy incremental runtime and source schema have been
removed; its immutable archive remains audit-only. Archive documents are
useful background, but are not implementation instructions.

## Documentation maintenance process

### Work-package lifecycle

1. When approved in-flight work begins, create one `docs/work-packages.md` and
   do not create a second current plan.
2. Follow [the delivery contracts](delivery-contracts.md). Establish a feature
   contract before decomposition; every package records its local interfaces,
   affected AC IDs, dependency outputs, work, acceptance criteria and status.
   The pipeline identifies the next ready package and blockers. Revalidate it
   at the start of each session.
3. Before marking a package complete, verify every acceptance criterion against
   the implemented repository and record the evidence in the package: test or
   CI job, migration/version where applicable, and the change that delivered
   it. A package is not complete merely because its code was written.
4. A request to complete a package authorizes all work in its objective, work,
   and acceptance criteria. Do not stop at a foundation, partial implementation,
   or intermediate test pass: continue until every criterion is verified and
   evidence is recorded, unless an external blocker prevents further work.
   Maintain an explicit checklist of every Objective, Work, and automated
   acceptance-criteria bullet; reconcile it before any final response. A
   passing focused test, completed migration, coherent implementation slice,
   or progress update is only a checkpoint. If an item remains without an
   external blocker, continue implementation rather than reporting the gap.
5. Before replacing the current plan, review every package in it. Normal
   completion requires every package and the integrated feature acceptance to
   have recorded evidence. If any item remains, extend or revise the plan.
   Explicit user cancellation or supersession follows DC-07: retain the
   undelivered scope and do not mark it complete.
6. Move a completed, deferred, or superseded plan to `docs/archive/`, add its
   reason and final status at the top, and update `archive/work-packages.md`.
   Only after that may a replacement become the current work-package document.

Do not silently archive an incomplete plan to make room for a new one. Merge
new authorized scope into the current plan unless the user explicitly cancels
or supersedes it; record that decision and transferred or undelivered scope.

### Reference-document lifecycle

Every implementation change includes a documentation-impact review before it
is merged. Update each affected reference document in the same change; state
in the change description that no reference document changed only when none is
affected. In particular:

| Change | Required documentation review |
| --- | --- |
| Runtime, storage, workers, data flow, or ownership | Architecture and root README |
| HTTP contract, public/private boundary, or compatibility behaviour | API reference and any affected frontend README |
| Compose, environment variables, migrations, queues, backup, recovery, alerts, or deployment | Operations and root README |
| Scope, dependency, status, completion evidence, or future work | Current work packages |
| Completion, deferral, or replacement of a plan | Current work packages and archive index |

Reference text must describe implemented behaviour, not a proposed design. Put
future implementation scope in the current work-package document; proposed
decisions and review findings must be clearly labelled as such. Archive documents retain
historical context but do not override current reference documentation.

### Required documentation checks

For a documentation change, verify links and structure with:

```bash
git diff --check
rg --files docs -g '*work*package*.md' -g '!**/archive/**' -g '!**/templates/**' -g '!**/reviews/**'
```

The second command must output only `docs/work-packages.md` when a plan is
active, or no output (exit status 1) when none is active. Check relative links
in changed documents. Review the current pipeline if present and every
reference document named by the change-impact table above.
