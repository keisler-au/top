# Work-package archive

Archived plans are historical context only. There is currently no in-flight
work-package plan; create a new current plan only when approved work begins.
A plan enters this directory only after its final status and archive reason are recorded.

| Archived document | Final status | Archive reason |
| --- | --- | --- |
| [Taxonomy recovery and lifecycle repair](taxonomy-recovery-and-lifecycle-repair-work-packages.md) | Complete | TR-0–TR-3 repaired cumulative automation and lifecycle diagnostics, added full Compose acceptance, and recovered the affected local installation with immutable gate state preserved. |
| [Question-context implementation plan](question-context-implementation-plan.md) | Implemented | Its work shipped; reference behaviour is now in the architecture, API, and operations documents. |
| [Taxonomy operational-reliability plan](taxonomy-operational-reliability-work-packages.md) | Superseded | It stopped short of incremental-taxonomy retirement. |
| [Public website work packages](public-website-work-packages.md) | Superseded and incorporated | Its reviewed, batch-aligned PW packages were incorporated into the completed combined plan. |
| Batch-taxonomy delivery (BT-WP1–BT-WP8) | Complete | Its concise deployed-state record is [Current state](../current-state.md); its subsequent public-website programme also completed. |
| [Batch-taxonomy and public-website work packages](batch-taxonomy-and-public-website-work-packages.md) | Complete | All BT-WP1–BT-WP8 and PW-WP1a–PW-WP6 packages were completed with recorded evidence; automatic taxonomy orchestration is a subsequent programme. |
| [Automatic taxonomy delivery](automatic-taxonomy-work-packages.md) | Complete | AT-WP1–AT-WP3 shipped durable automatic snapshotting, quality-gated promotion, operator status, and delivery verification. |

The detailed dashboard/article and first batch-taxonomy work-package documents
were consolidated because their planned states diverged from the repository and
duplicated current reference material. Their durable historical conclusions are
recorded below.

## Completed or substantially implemented history

- Dashboard and article work introduced read APIs, article revisions and audit
  lifecycle, versioned safe templates, generation jobs, form-source management,
  and the framework-free frontend.
- Navigation was consolidated around Overview, Articles, Forms, and the
  generation flow. Legacy `/taxonomy` and `/templates` frontend routes were
  redirected.
- The original taxonomy direction used per-input topic strings and live themes
  connected through `theme_topics`.

## Superseded batch-taxonomy proposal

The original TAX-WP0 through TAX-WP8 proposal introduced the intended
run-scoped architecture: frozen canonical evidence, embedding clustering,
literal topics, advisory themes, explicit publication, scheduling, rollout,
and quality controls. Parts of it were implemented in migrations 015–022 and
the `taxonomy_*` modules, but it did not pass its required feasibility or
end-to-end operational gates.

The first operational-reliability replacement plan has itself been superseded:
it stopped short of retiring the incremental taxonomy. Its completed successor
plans are indexed above.

## Historical constraints retained in current documentation

- Preserve raw input, segment, question, template, article revision, and
  citation provenance.
- Select segments instead of their parent original when segmenting evidence.
- Keep background work durable and retryable in PostgreSQL.
- Keep article approval separate from generation and retain immutable history.
- Do not treat the candidate batch taxonomy as production-ready until its
  automated reliability gates pass.
