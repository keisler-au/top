# Documentation guide

This directory documents the repository as it exists now. Reference documents
describe implemented behaviour; the one current work-package document describes
the only approved delivery pipeline. Historical plans are retained in the
archive, where they are never instructions for new work.

## Current documentation set

| Document | Use it for | Update when |
| --- | --- | --- |
| [Root README](../README.md) | Project purpose, local development, service startup, and the concise operator entry point. | The supported developer workflow, service topology, or primary documentation entry point changes. |
| [Current state](current-state.md) | Concise deployed batch-taxonomy boundary and remaining programme. | The production taxonomy, publication, archive, or delivery boundary changes. |
| [Architecture](architecture.md) | Components, ownership, persistence boundaries, and processing flows. | A component, data owner, runtime flow, or system boundary changes. |
| [API reference](api.md) | Implemented HTTP endpoints and stable request/response behaviour. | A route, schema, authentication boundary, status, or compatibility behaviour changes. |
| [Operations](operations.md) | Implemented deployment, migration, worker, recovery, backup, and diagnostic procedures. | Compose, configuration, migrations, queues, recovery, or operational security changes. |
| [Admin dashboard README](../frontend/admin/README.md) | Dashboard development, build, test, and user-interface integration guidance. | The admin build, test, routes, or API integration changes. |
| [Current work packages](work-packages.md) | The sole active delivery pipeline, its order, status, and machine-verifiable completion criteria. | Scope, sequence, dependency, status, or completion evidence changes. |
| [Work-package archive](archive/work-packages.md) | Index of completed, deferred, and superseded plans. | A current plan completes, is deferred, or is superseded. |

## Current delivery pipeline

There is exactly one current work-package document:
[work-packages.md](work-packages.md). Its active programme is batch-taxonomy
production and incremental-taxonomy retirement, followed by the public
read-only article library. Batch taxonomy is the sole production taxonomy;
the legacy incremental system survives only as an immutable audit archive.
The public programme begins after BT-WP8.

The operational-reliability and question-context plans are archived. The
public-website source plan is also archived, because its reviewed and revised
PW packages are now incorporated in the current document. The legacy
incremental runtime and source schema have been removed; its immutable archive
remains audit-only. Archive documents are useful background, but are not
implementation instructions.

## Documentation maintenance process

### Work-package lifecycle

1. Keep all approved in-flight work in `docs/work-packages.md`. Add a package
   or revise scope there; do not create a second current plan.
2. Every package states its objective, dependencies, concrete work,
   machine-verifiable acceptance criteria, and status. The document’s pipeline
   table identifies the next package and what blocks each later package.
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
5. Before replacing the current plan, review every package in it. Archive the
   document only when every package is complete and its evidence is recorded.
   If any item remains, extend or revise the current document instead.
6. Move a completed, deferred, or superseded plan to `docs/archive/`, add its
   reason and final status at the top, and update `archive/work-packages.md`.
   Only after that may a replacement become the current work-package document.

A deferred or superseded proposal may be archived only while it is not the
current plan. The current plan cannot be archived or replaced while it has an
incomplete package; merge the new scope into it and revise its pipeline table
instead.

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

Reference text must describe shipped behaviour, not a proposed design. Put
future work only in the current work-package document. Archive documents retain
historical context but do not override current reference documentation.

### Required documentation checks

For a documentation change, verify links and structure with:

```bash
git diff --check
find docs -maxdepth 1 -type f -name '*work*package*.md' -print
```

The second command must output only `docs/work-packages.md`. Review the
current work-package pipeline table and every reference document named by the
change-impact table above.
