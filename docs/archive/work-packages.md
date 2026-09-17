# Work-package archive

Archived plans are historical context only. They are not instructions for new
implementation; all approved in-flight work is in
[the current work packages](../work-packages.md). A plan enters this directory
only after its final status and archive reason are recorded.

| Archived document | Final status | Archive reason |
| --- | --- | --- |
| [Question-context implementation plan](question-context-implementation-plan.md) | Implemented | Its work shipped; reference behaviour is now in the architecture, API, and operations documents. |
| [Taxonomy operational-reliability plan](taxonomy-operational-reliability-work-packages.md) | Superseded | It stopped short of incremental-taxonomy retirement. |
| [Public website work packages](public-website-work-packages.md) | Superseded and incorporated | Its reviewed, batch-aligned PW packages are now part of the current plan. |
| Batch-taxonomy delivery (BT-WP1–BT-WP8) | Complete | Its concise deployed-state record is [Current state](../current-state.md); the shared current plan remains active for the PW programme. |

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
it stopped short of retiring the incremental taxonomy. The active replacement
is the [current work-package plan](../work-packages.md).

## Historical constraints retained in current documentation

- Preserve raw input, segment, question, template, article revision, and
  citation provenance.
- Select segments instead of their parent original when segmenting evidence.
- Keep background work durable and retryable in PostgreSQL.
- Keep article approval separate from generation and retain immutable history.
- Do not treat the candidate batch taxonomy as production-ready until its
  automated reliability gates pass.
