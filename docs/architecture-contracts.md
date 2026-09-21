# Architecture contracts

These are normative requirements for new and changed implementation. The
[architecture reference](architecture.md) describes the running design;
[the baseline review](reviews/architecture-baseline.md) distinguishes verified
structure from known gaps. These contracts do not claim every existing path
already complies. Their initial baseline is the working tree reviewed on
2026-09-21, including uncommitted automatic-taxonomy work.

Keep IDs stable. To change a contract, record the reason, alternatives,
consumer impact, transition, and verification in an architecture decision
under `docs/decisions/`, then update this document in the same change. Existing
user authorization can cover that decision; routine implementation choices do
not need separate approval. A package or archived plan cannot override a
contract by omission.

## AC-01 — Component and dependency ownership

| Capability | Existing owner / extension point | Boundary |
| --- | --- | --- |
| HTTP validation and response mapping | `backend/src/triage_processor/api/`, route schemas | Routes own transport; reusable domain rules must remain callable without HTTP. |
| Domain operations | `articles.py`, `templates.py`, `taxonomy_*.py` | Reuse these modules and their database functions; do not duplicate rules in routes or UI. |
| Database invariants | `infrastructure/postgres/migrations/` | Constraints, triggers and transition functions enforce durable integrity across callers. |
| Model transport | `clients/llm.py`, `clients/ollama.py` | No direct database access; callers validate domain output. |
| Evidence jobs | `job_queue.py`, `workers/eligibility_segmentation.py`, `workers/embeddings.py` | Only eligibility/segmentation and embeddings belong in `worker_jobs`. |
| Taxonomy orchestration | `taxonomy_scheduler.py`, `taxonomy_stages.py`, `taxonomy_automation.py`, `taxonomy_snapshots.py` | Extend the durable run/stage lifecycle. |
| Article generation | `api/routes/generation.py`, `workers/article_generation.py`, `articles.py`, `templates.py` | Separate durable generation jobs; generation does not approve articles. |
| Source integration | `integrations/google_sheets.py` and form-source API | Preserve normal input/question identity and ingestion semantics. |
| Admin UI | `frontend/admin/src/` | Typed API client, page state, shared components, query cache. |
| Public delivery | `public_site/`, `api/routes/public_site.py`, `frontend/public/` | Approved editorial projection and explicit edge allowlist only. |

Direct parameterized SQL in routes is an existing convention; a new ORM,
repository framework, queue, frontend framework, or service is not required
for consistency. New shared business logic belongs below the HTTP layer.
Do not add domain/worker imports of route handlers. Existing worker reuse of
`api/generation_schemas.py` is a known dependency exception; a future extraction
must move the shared schema and its consumers together, without duplicating it.

## AC-02 — Evidence and identity

Original text remains source evidence. Preserve original/segment provenance
and immutable question wording. Question identity is
`(source, form_key, question_key, question_version)`; changed wording requires
a new version. Submission identity is scoped by source and form. Question
context may interpret an answer but must not become invented segment content.

Canonical taxonomy evidence selects segments instead of their parent original
when segments exist. Snapshot selection freezes a database cutoff, membership,
embedding model/representation/dimension, and configuration/prompt provenance.
Never silently combine incompatible vectors or change frozen membership.
Reuse `create_taxonomy_snapshot` and published database readers. Any additional
selector must demonstrate the same canonical semantics with shared fixtures.

## AC-03 — Taxonomy visibility and publication

Production taxonomy readers use one published run, or a bounded unavailable
state before the first publication. Candidates and the legacy archive are not
reader fallbacks. Resolve stable IDs and lineage through the existing database
functions; labels and run-local IDs are not durable identity.

Automatic publication requires the immutable server-computed passing release
attestation and durable automation policy decision. Manual publication and
rollback retain their protected transitions. Use existing publication functions;
do not set publication status directly in a new caller. Publication swaps and
audit decisions must be atomic. Failed candidates preserve the current run;
unchanged failed evidence must not cause an unbounded automatic creation loop.

Each multi-query reader must preserve a consistent published-run view using
the existing transaction/read semantics or an explicitly captured run ID.
Changing cumulative versus post-cutoff evidence membership is a product/data
decision, not an incidental optimization; describe coverage effects first.

## AC-04 — Durable work and transactions

Background work uses its existing PostgreSQL queue or stage owner. Record
claim, lease owner, retry policy and terminal result durably. Work must survive
process restart and repeated delivery. Validate claim ownership before storing
results, and commit result/state/audit changes atomically where they form one
transition. A stale worker must not overwrite a newer claim's result.

For every changed lifecycle, specify legal transitions, idempotency keys,
concurrent-writer behaviour, retryable versus terminal failures, and recovery.
Do not hold a database transaction open during a model/network request. Freeze
inputs, perform external work, then validate the claim and persist the result.
Keep the three existing job lifecycles distinct; a unification requires an
explicit decision and migration, not a package-local abstraction.

## AC-05 — Editorial and public boundary

Article revisions, evidence/citations, template versions and taxonomy display
snapshots retain immutable provenance. Generated articles enter editorial
review. Explicit approval updates `article_publications` and revision-scoped
`article_publication_themes` atomically. Reapproval preserves permanent slug
and first-publication time. Taxonomy changes do not rewrite historical display
snapshots.

Public rendering may read the publication projection, its approved revision
content, article status/current-revision guards, and existing stable-theme
resolution. It must not expose source evidence, prompts, generation metadata,
editorial audit, or administrative JSON. This is an exposure boundary, not a
claim that the renderer queries only two tables. The public nginx allowlist,
scriptless CSP and configured canonical origin remain authoritative; never
derive canonical URLs from the request Host. Admin remains opt-in and bound to
loopback in Compose; internal API/database/model services stay unexposed.

## AC-06 — API and frontend compatibility

Backend HTTP schemas and documented behaviour own the wire contract;
`frontend/admin/src/api/contracts.ts` mirrors it and is not generated or runtime
validated today. A changed payload/status/error updates backend schemas,
`docs/api.md`, typed client, error normalization and affected pages together.
Do not call a TypeScript cast proof of runtime compatibility.

Use parameterized SQL and allowlisted sort expressions. Lists need bounded
inputs, deterministic tie-breaking and the existing endpoint's pagination
convention. Do not standardize distinct pagination/error formats incidentally.
New error codes must be stable and bounded; do not expose raw exceptions.

Admin pages use `ApiClient` through the application context, shared components
and design tokens. Preserve loading, empty, unavailable, error and success
states; prevent stale responses from replacing newer page state. Mutations
invalidate all affected query-cache consumers. Specify deep-link behaviour and
preserve safe text/HTML rendering. Adding dependencies requires a concrete need
and a decision when it changes the established frontend architecture.

## AC-07 — Security, model output and diagnostics

Reuse `api/security.py` for operator authentication and rate limiting. Every
new or changed endpoint states its public/internal/operator classification.
Operator reads require a nonempty configured review or mutation token; mutations
require a nonempty configured mutation token. Missing credentials must never
match an empty configuration value. Internal administrative APIs are not all
token-protected today; do not imply they are safe to expose publicly.

Model output and source text are untrusted. Validate structured output,
citation membership and taxonomy scope before persistence. Escape/sanitize
HTML through the existing template pipeline. Diagnostics use IDs, counts,
bounded codes and durations; exclude secrets and raw evidence/model payloads
from routine logs and public errors. Store necessary audit provenance only in
its intended protected store.

## AC-08 — Schema and configuration evolution

Add numbered migrations; do not rewrite an already applied migration to change
deployed behaviour. The runner tracks filenames, not file checksums. Maintain
both the ordered include list and migration markers in `init.sql`. Verify
fresh installation and upgrade from relevant populated prior schemas.

Schema changes must account for constraints, readers, writers, triggers,
indexes, workers and schema-readiness checks such as
`taxonomy_scheduler.required_migration_filenames`. State deploy order,
backfill/lock impact and recovery. Destructive changes require explicit scope,
retention/backup and restore evidence; do not invent reversible rollback for
irreversible data loss.

Shared configuration belongs in `config.py`; component settings may remain in
their existing validated settings classes. Give each setting one owner and
consistent defaults across code, `.env.example`, Compose and operations docs.
Never persist secrets in plans, tests or example configuration.

## AC-09 — Verification follows the boundary

| Changed boundary | Required evidence |
| --- | --- |
| Pure behaviour / API mapping | Focused backend tests, including invalid inputs and changed error behaviour. |
| Database invariants / publication / leases | Real PostgreSQL+pgvector tests; include atomic rollback, replay/concurrency and stale claims as applicable. |
| Schema | Fresh initialization and populated upgrade tests, plus affected runtime consumers. |
| API consumed by admin | Backend response behaviour and frontend client/state tests, typecheck/build. |
| Public content / nginx exposure | Public-edge tests over HTTP, including denied routes and unpublished/private content. |
| Cross-component feature | A user-visible lifecycle acceptance check across every changed component. |
| Documentation only | Local links, internal consistency and `git diff --check`. |

Use the existing unittest, Node and isolated Compose harnesses. Add meaningful
regression tests for changed behaviour; do not add tests that merely repeat an
implementation. Tests skipped for missing services are unverified. Ensure CI
actually triggers on changed paths; the baseline review records current gaps.
Full commands and package evidence rules are in the delivery contracts.
