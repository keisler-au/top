# ADR-0004: Token-free internal taxonomy review

- Status: accepted
- Date: 2026-10-10
- Scope/authorization: The user explicitly requested removal of the access
  barrier from taxonomy review after encountering unconfigured credentials.
- Affected AC IDs: AC-05, AC-06, AC-07, AC-09.
- Supersedes / superseded by: Refines AC-07 for the three taxonomy review reads;
  no other authentication boundary changes.

## Context and evidence

The review page required a shared operator token even though other internal
admin browsing did not. Missing server configuration made the entire page
unusable. Existing owners are the taxonomy review router and admin page/client.
Starting revision: `8b3910acdf88bddb87e4f10a41819c6bfad595b6`.
The checkout already contains extensive uncommitted PTR changes, including
modified review router, client and references, plus untracked review page/state,
component tests and partial-taxonomy integration tests. Those changes are
preserved; HEAD alone is not the implementation baseline.

## Decision and alternatives

The page automatically loads runs and contains no credential controls. Run list,
run detail and topic evidence GET endpoints are internal admin reads without
operator authentication or credential-based rate limiting. Remove the now-unused
frontend operator-token option and header plumbing. Keep existing response
schemas, pagination, request cancellation and read-only behaviour.

Configuring a token would retain the rejected user workflow. Making tokens
optional would leave unnecessary branching. Removing all API authentication
would expand scope beyond viewing: taxonomy writes, operations and legacy
archive reads retain the existing security owner and checks.

## Consequences and transition

Anyone who can reach the internal API can read these run records and their
explicitly requested source evidence, just as internal input browsing already
allows. The public nginx allowlist continues to deny review pages and APIs.
No schema, data migration, new login system or deployment configuration is
required. Deploy matching API/admin images through the existing process;
this source change does not authorize deployment. Recovery is an application
rollback to the prior matching images; no data recovery is needed.

## Verification and contract updates

This is a bounded access change. It adds no editing or publication controls,
changes no stored data, and does not redesign either tab. The existing router,
client and page remain the capability owners. No follow-on package depends on
this change.

Acceptance: automatic credential-free frontend loading and evidence reads;
no-token API reads against real PostgreSQL with configured and unconfigured
operator credentials; writes and operations still reject anonymous requests;
public HTTP requests to review routes remain denied. Check frontend typecheck,
tests/build, affected PostgreSQL/API tests, public-edge tests and documentation
links. AC-07, API, operations, architecture, current state, root README and admin
README are updated together. Verification results are recorded below on closure.

### Completion evidence and handoff

Verified on 2026-10-10 against the dirty checkout described above, with this
access change layered on the existing PTR implementation:

- `cd frontend/admin && npm run typecheck`: passed.
- `cd frontend/admin && npm test`: all 10 test files passed, zero skips;
  this command includes the frontend build. Rerun after the generic operator
  error text update also passed.
- `docker compose -f compose.test.yaml up -d --build --wait postgres api public-web`:
  built matching API and edge images on a fresh disposable PostgreSQL instance.
- Initial `docker compose -f compose.test.yaml run --rm tests python -m unittest
  discover -s tests -v`: 302 tests, one failure from the old quality-test
  expectation that anonymous review must return 401. Updated that expectation;
  no production behaviour change was needed.
- The next full run reused the stack and had two failures and two errors in
  worker/public-page checks. Reset only the disposable stack with
  `docker compose -f compose.test.yaml down`, then recreated it with
  `docker compose -f compose.test.yaml up -d --wait postgres api public-web`.
- Final `docker compose -f compose.test.yaml run --rm tests python -m unittest
  discover -s tests -v`: all 302 tests passed in 72.384 seconds, no skips.
  Includes credential-free review, unchanged mutation/operations protection,
  private model payload omission and public HTTP denial of review routes.
- `git diff --check`: passed. Relative file links in all eight changed/new
  reference and decision documents resolved. The active work-package search
  returned no files (expected exit 1); this bounded change has no active package.

Delivered: automatic token-free review, no frontend credential controls/header
plumbing, unchanged read schemas, and matching current reference contracts.
No migration, application-data change, commit or deployment was performed.
No implementation work remains in this request. Applying it to a running
installation requires matching API/admin images through the normal deployment
process. Browser layout was not tested. Other usability findings from the
review are outside this change and remain outstanding.
