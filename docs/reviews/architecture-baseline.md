# Architecture baseline review — 2026-09-21

Scope: repository architecture, implementation boundaries, delivery records and
verification wiring. Baseline: HEAD `157eeb3` **plus existing uncommitted work**,
including taxonomy automation, migrations 039/040, API status and documentation
changes. This is a static boundary review with one isolated authentication
diagnostic, not a complete security audit or certification of runtime tests.

## Established structure

The application has coherent durable boundaries: PostgreSQL owns immutable
evidence/taxonomy/article history and publication transitions; separate workers
own evidence, taxonomy stages and article generation; the admin and public
frontends have different exposure rules. The main risk is losing these choices
between packages, rather than a demonstrated need to replace the stack.

Evidence inspected includes API routes/schemas/security, `job_queue.py`,
snapshot/scheduler/stage/automation modules, article generation and templates,
the public service, frontend client/cache/page conventions, schema bootstrap
and migration runner, integration fixtures, Compose, CI and current/archive
documentation. Ownership is mapped in [AC-01](../architecture-contracts.md#ac-01--component-and-dependency-ownership).

## Findings and disposition

### R1 — High: operator reads can accept missing credentials

In `backend/src/triage_processor/api/security.py`, `require_operator` compares
the presented value with both configured token strings for reads. When exactly
one token is configured, a missing Authorization header produces `""`, which
matches the unconfigured token's `""`. The initial configuration check permits
this case, so authorization reaches the database rate limiter.

Confirmed by invoking the real function with an empty header map, each
single-token configuration, and a mocked successful database rate-limit call:
both calls returned without an authentication error. No real credentials,
network requests or database mutations were used. Exposure remains constrained
by the internal API/loopback topology; this is still a violation of the stated
fail-closed operator boundary.

Follow-up: require nonempty presented and configured values before comparison;
verify absent/empty/malformed credentials against review-only, mutation-only,
both-configured and unconfigured cases, and valid role separation. AC-07 makes
the intended contract explicit. Runtime remediation is not included in this
documentation change.

### R2 — High delivery risk: completion records disagree

At review time `docs/README.md`, `docs/current-state.md` and the archive index
say automatic taxonomy delivery is complete. However,
`docs/archive/automatic-taxonomy-work-packages.md` labels itself an active plan
and AT-WP3 planned. `docs/work-packages.md` is deleted in the working tree.
The archive index also has a link to that absent file. The scheduler's HANDLERS
comment still says no scheduler path can publish, although it now invokes
automation. Architecture prose contains a future rewrite-package statement
followed by the implemented public rewrite description.

These are conflicting records, not proof that the feature is incomplete or
complete. Reconcile the original package acceptance evidence before correcting
its status; this review does not invent a successful test run or restore an
obsolete plan. DC-04, DC-06 and DC-07 require drift checks, durable handoff and
consistent closure. The documentation guide's contradictory requirement for a
work-package file even when no plan is active is corrected in this change.

### R3 — Medium: CI does not follow the current component layout

`.github/workflows/taxonomy-verification.yml` filters `frontend/src/api/**`,
but the application now lives under `frontend/admin/src/`. It runs the Compose
backend/database/public-edge harness and has no admin Node/typecheck job.
Frontend-only changes therefore need not trigger this workflow; changes limited
to shared backend modules such as `articles.py`, `templates.py`, `clients/` or
`workers/` also fall outside its source filters unless other matched paths
change. Public frontend-only changes are not matched either.

Follow-up: align triggers to the actual component/dependency graph and add
frontend verification. Until then, execute and record the applicable checks
locally. The contracts are agent/review obligations; this change does not claim
they are fully enforced by CI.

### R4 — Medium: shared business rules have several potential owners

`api/routes/articles.py` mixes HTTP mapping, SQL and lifecycle orchestration;
`articles.py` and database functions also implement article behaviour.
`api/routes/generation.py` imports taxonomy queries from
`api/dashboard_queries.py`, while the generation worker imports
`api/generation_schemas.py`. New features could copy those rules or deepen
transport-layer dependencies. Environment parsing is similarly distributed
between component settings and a very small `config.py`.

AC-01/08 establish extension owners without imposing a wholesale rewrite.
Extract shared behaviour only when the feature needs it, update every consumer
and test the boundary. Do not add parallel schemas/settings implementations.

### R5 — Medium: public projection wording overstates physical isolation

`public_site/service.py` describes projection-only queries, but joins
`articles` and `article_revisions` for approval/current-revision checks and
approved content, and calls `resolve_published_theme_id`. The projection holds
revision identity, not a full copy of public article content. This is not by
itself a data leak. A literal two-table rule would misdescribe the implementation
and could prompt an unnecessary second content store. AC-05 states the actual
allowable reads and private-data prohibition.

### R6 — Medium: consumer compatibility and verification need explicit handoff

The frontend client casts JSON to manually maintained TypeScript contracts;
types do not validate real responses. Database integration tests skip without
`TRIAGE_TEST_DATABASE_URL`; public lifecycle tests also need a public edge.
Passing local unit tests alone therefore cannot prove cross-component delivery.
AC-06/09 and package acceptance IDs require producer/consumer updates and
boundary-appropriate evidence, including skipped checks.

## Contracts introduced by this review

Root `AGENTS.md` is the agent entry point. Architecture contracts define stable
owners/invariants; delivery contracts define feature decisions, package entry,
daily drift review, evidence and handoff. Templates make both small fixes and
large changes concrete without creating a fictitious active programme.

The findings above are follow-up candidates, not an approved implementation
backlog. No runtime code, schema or deployment was changed by this review.
