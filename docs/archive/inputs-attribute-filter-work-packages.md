Archived 2026-10-10: complete in source; attribute filtering and references verified.
Not committed, merged or deployed. No undelivered filter scope.

# Inputs attribute filtering

## Feature contract

- Status: complete, 2026-10-10.
- Authorization: user requested attribute filters on Inputs.
- Outcome: filter all stored inputs through the existing list owner, preserve
  filters in URLs and paging, and clear/apply filters from labelled controls.
- Non-goals: editing inputs, new taxonomy states, authentication changes,
  new pagination conventions, migration, deployment or analysis-policy changes.
- Baseline: HEAD `8b3910acdf88bddb87e4f10a41819c6bfad595b6`, extensive existing
  dirty PTR implementation plus token-free taxonomy review. Inputs route,
  API contracts/client and references are modified; Inputs page and component
  tests are untracked. Preserve them and the untracked taxonomy examples.
- Existing owner: `api/routes/inputs.py` and its published-run association CTEs;
  `ApiClient.inputs`, `InputsPage` and existing native component harness.
- AC IDs: AC-03 (published-run associations), AC-06 (API/UI compatibility),
  AC-07 (safe text/SQL), AC-09 (database/API and frontend verification).
- Assumptions: existing source/form/question/submission identity validation
  remains authoritative; additional filters combine with AND. Topic/theme
  names match current published associations, including split-answer unions.
- Compatibility: optional query parameters; unchanged list payload, ordering,
  limit/offset bounds and private/public boundary. Deploy matching API/admin
  through normal process; recover with prior images; no database migration.

| Interface | Before → after | Consumers / verification |
| --- | --- | --- |
| `GET /inputs` | Existing identity scope → adds search, status, topic/theme name, topic presence and inclusive UTC dates | Admin client/page, PostgreSQL HTTP tests |
| `ApiClient.inputs` | Offset only → optional typed filters while retaining existing calls | Native component/client tests and typecheck |
| `/inputs` | Unfiltered cards → URL-backed filter form, paging and contextual attributes | State/component tests, build |

## Pipeline

| Package | Status | Dependencies | Outputs | Evidence |
| --- | --- | --- | --- | --- |
| IF-1 | complete | Existing list/API/published-run CTEs inspected | Integrated Inputs filters and references | IF-A1–A3 verified below |

Integration owner: IF-1. No downstream package.

## IF-1 local contract and acceptance

Optional search and topic/theme text use case-insensitive literal substring
matching; whitespace-only text is rejected by the API. Processing statuses use
existing input status values. Topic presence describes published associations,
not evidence eligibility. Received dates are inclusive UTC calendar dates;
reversed dates return 422. Identity filters keep their existing dependencies.
Filtering precedes pagination in the same SQL statement as published arrays.
Original answers and historical runs remain unchanged. URL state, apply/clear,
refresh, paging and navigation retain request ownership to reject stale results.
Errors remain visible and retryable; source/model text is rendered as text.

- [x] IF-A1: PostgreSQL HTTP tests prove combined filters, literal search,
  inclusive dates, taxonomy association filtering, empty/prepublication and
  invalid filters; existing input contracts continue to pass.
- [x] IF-A2: Typed client encodes only nonempty filters. State tests verify
  URL round trips and bounds. Production component tests verify apply/clear,
  pagination reset/preservation, deep links and stale-result cancellation.
- [x] IF-A3: Frontend typecheck/tests/build and affected PostgreSQL suite pass;
  references, links and `git diff --check` pass.

References: API, admin README, architecture Inputs description, root README.
Closure will record exact commands, results/skips, limitations and handoff here.

## Closure evidence and durable handoff

Verified 2026-10-10 on the dirty checkout recorded above:

- `cd frontend/admin && npm run typecheck`: passed.
- `cd frontend/admin && npm test`: all 11 test files passed, no skips; includes
  build. Client, state and production component tests cover typed filter
  encoding, deep links, identity/date validation, apply/clear, pagination reset
  and preservation, and stale refresh responses.
- `docker compose -f compose.test.yaml up -d --build --wait postgres api public-web`:
  fresh disposable PostgreSQL and matching API/public edge ready.
- `docker compose -f compose.test.yaml run --rm tests python -m unittest
  discover -s tests -v`: 304 tests, 303 passed, no skips, one error in the new
  prepublication fixture's direct transition of an immutable final run. All
  earlier filter assertions passed. Fixed this test to use the existing
  transaction-local disposable rollback fixture procedure. Production code
  and database rules needed no correction.
- `docker compose -f compose.test.yaml run --rm tests python -m unittest
  discover -s tests/integration -p test_dashboard_postgres.py -v`: all 44
  affected PostgreSQL/API tests passed in 24.734 seconds with no skips after
  the fixture correction. Includes both new filter tests and existing inputs,
  publication, generation, authentication and dashboard readers.
- `git diff --check`: passed. Relative links in changed references, this archive
  and the threshold review resolve. No active work-package file remains.
- Disposable test containers removed with `docker compose -f compose.test.yaml down`.

Delivered interface: optional search, status, topic/theme name, topic presence,
UTC date filters on the existing list; identity filters and response shape are
unchanged. Admin filters the whole dataset, preserves URL/query selections,
resets paging on apply/clear and displays the response attributes being filtered.
References updated: API, admin README, architecture, root README, current state
and documentation/archive guide. IF-A1–A3 and all objective/work items have
acceptance evidence. No downstream package or changed schema assumptions.

The user's additional request to explain and review clustering thresholds was
addressed in [the threshold review](../reviews/topic-quality-threshold-review-2026-10-10.md).
It assesses existing source/calibration and official HDBSCAN definitions; no
live group inspection, new model calibration or threshold changes were made.

No deployment, data migration or new dependencies. Applying filters to a running
installation requires matching API/admin builds. Browser layout was not tested.
No remaining implementation work or unresolved product decision for this package.
Next package: none. Archive reason: the requested filter feature is complete.
