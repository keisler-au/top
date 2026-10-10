# Current state

The application is a batch-taxonomy editorial system. Inputs are prepared by
eligibility/segmentation and embedding workers; the scheduler automatically
snapshots eligible evidence, builds a leased candidate, and publishes only
after its immutable quality gate passes. Exactly one published run serves every
taxonomy reader and article-generation target. Before first publication,
taxonomy readers return a bounded first-run status; a failed gate reports a
bounded quality-blocked status while retaining any prior published run.
First-run dashboard and protected operations status follow the newest candidate,
so an older failure does not hide a newer active run.
The current source requires immutable question context for new inputs and
creates one question-answer embedding per original or segment target. New
automatic candidates use cumulative membership and question-scoped
`partial-topic-policy/v1` clustering with durable geometry diagnostics and
bounded evidence packets. Eligible clusters use `partial-topic-naming/v1`;
validation checks response shape, bounds, duplicate names, and exact packet
evidence IDs without using word overlap as a meaning test. Accepted labels are
immutable provisional topics, separate from canonical topic revisions. The older `mixed` representation remains a manual
snapshot compatibility path for frozen data. A changed complete evidence set can create a successor
after a failed quality candidate; an unchanged failed set remains blocked.
Migrations 041–043 and matching application/admin images were deployed to the
affected local installation on 2026-09-24 after physical and logical backups.
Its stranded first candidate is now durably failed and truthfully
quality-blocked; its nonpassing attestation remains immutable and no run was
published. Fresh, populated-upgrade, and production-shaped Compose acceptance
all pass.

Migration 044 is the required-question and cluster-policy boundary. It fails
closed when historical questionless rows remain, so each deployment must audit
them before upgrading. Evidence model calls run outside database transactions;
only the worker that still owns the queue job can atomically save the decision
or vectors and complete it. Migration 045 adds the provisional-topic identity
and is required by scheduler health. Migration 046 adds the durable
`topic_reconciliation` stage, immutable decisions and canonical antecedents.
The source now reconciles plausible cross-question equivalents in bounded
packets, then atomically stores canonical revisions, the exact evidence union,
and stable identity/lineage. Fresh PostgreSQL and populated migration 046
verification passed on 2026-10-08; at that verification point these changes had not been deployed to the
local application; see the local runtime update below. Optional themes and coverage attestation are now implemented in source and
passed PTR-4 fresh/populated disposable verification on 2026-10-08. Migration
047 supplies the shared consistency/coverage facts and zero-theme materializer;
gate v3 requires a nonempty canonical topic and consistent completed processing,
while allowing rejected naming attempts and low coverage. Migration 048 and
PTR-5 implement atomic partial publication, replacement/replay/rollback and
published-run reader associations. Input `taxonomy_state` is removed while
processing status and run provenance remain. Dashboard and protected operations
report exact with-topic/without-topic counts. Topic generation needs no theme
and freezes its run and evidence through replacement. Disposable PostgreSQL
verification is recorded in the archived PTR plan. Local activation is recorded
below; publication remains controlled by the existing automatic quality gate. Admin source now defaults to
published topics for browsing/recommendations/generation, displays exact partial
coverage and state-free input associations, and offers internal read-only run
review with readable antecedents, cluster outcomes and canonical evidence.
Review now loads without a token; raw model audit payloads remain absent.
Taxonomy mutations, operations and legacy archive reads remain protected.
The token-free review boundary is recorded in [ADR-0004](decisions/0004-token-free-taxonomy-review.md).
PTR-6 has disposable API/PostgreSQL/public-edge and frontend component evidence;
local activation is recorded below. PTR-7 now verifies topic/theme replacement
for added, removed, replaced and empty results, split-answer aggregation,
failed/competing swaps, replay and rollback, protected frozen history and
unchanged approved article displays. All 301 backend/PostgreSQL/API/public-edge
tests passed without skips on a fresh disposable stack on 2026-10-09.
PTR-8 completed on 2026-10-10 with all 302 tests passing without skips on a
fresh disposable stack, 13 populated-upgrade checks, frontend typecheck/tests/
build, and the complete Sheets/API-to-publication journey with real embeddings.
It verified partial zero-theme publication, merged cross-question equivalents,
a full successor with distinct related topics and a shared theme, topic
generation and approval, failed successor preservation, replay and rollback.
Newly created article evidence records its selected/frozen taxonomy run, as do
its topic tags and generation job. Sheets auth/values transport and structured
chat are fixtures; no production-model semantic accuracy or live deployment is
claimed. All feature criteria and references are reconciled in the
[completed PTR plan](archive/partial-taxonomy-and-reconciled-topic-work-packages.md).
There is no next package in this feature.

Inputs now supports server-side combined attribute filters and URL-backed
admin selections for text, processing status, published topic/theme associations,
received dates and source/form/question/submission scope. The existing response
shape and bounded pagination remain unchanged. Verification at source closure
is recorded in [the completed filter plan](archive/inputs-attribute-filter-work-packages.md).

Incremental per-input topic assignment and live theme materialisation have
been removed. `worker_jobs` is limited to evidence preparation. Historical
incremental classifications and retired rollout records exist only in the
immutable, protected `taxonomy_legacy_archive`; they are never a reader
fallback.

Human publication defaults off and requires a configured mutation token. The
automatic transition is database-gated by an immutable passing attestation and
durable policy decision. Rollback remains explicit and preserves publication
decisions. See [Architecture](architecture.md),
[API reference](api.md), and [Operations](operations.md) for the supported
contracts and procedures.

Local runtime update, 2026-10-10: the default `docker compose up` now includes
admin and Google Sheets through `compose.override.yaml`. The API reloads and
workers restart on Python edits; dashboard TS/CSS/HTML rebuilds automatically,
with browser refresh. Dependencies/Dockerfiles still require image builds.
The local stack was switched successfully using `up -d --wait`, preserving
its database/model volumes. Migrations 044–048 were already present, so no
schema upgrade was performed. All background children and web health checks
passed; token-free review and the filtered Inputs API are active locally.
This records local activation of the current dirty sources, not a remote
production deployment. Explicit `-f compose.yaml` retains production images
and optional profiles. Verification, corrections and handoff are in the
[completed local development plan](archive/streamlined-local-development-work-packages.md)
and [ADR-0005](decisions/0005-default-local-development.md).

Historical plans are in [the archive](archive/work-packages.md).
