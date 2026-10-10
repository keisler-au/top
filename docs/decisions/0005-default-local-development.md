# ADR-0005: Default all-feature local development

- Status: accepted
- Date: 2026-10-10
- Scope/authorization: user requested minimal Compose flags, all features including
  Sheets, and backend/frontend updates with minimal builds.
- Affected AC IDs: AC-04, AC-05, AC-06, AC-07, AC-08, AC-09; DEV-1.
- Supersedes: refines the default local topology described by AC-05; production
  public/private boundaries, credentials and processing rules remain unchanged.

## Context and evidence

The base Compose stack copies source into immutable images and requires admin
and google-sheets profiles. Frontend dev builds only once. Uvicorn already
supplies watchfiles through its standard dependency; no new dependency is needed.
The existing worker/database owners recover interrupted claims and reject stale
writes. Compose automatically merges compose.override.yaml when no file is named.

## Decision and alternatives

Commit compose.override.yaml as the repository's default local development mode.
Reset admin/Sheets profiles there, mount Python source read-only, reload API and
supervise workers using watchfiles. Share one backend development image. Add an
admin development image stage and a dependency-free watcher that stages output
and preserves valid assets on compilation failure. Keep public nginx and its
allowlist, with local read-only assets/config mounts. No extra host API/DB/model
ports and no secret/content exposure through public routes.

An extra dev profile or -f argument would retain the rejected command overhead.
Compose Watch adds a foreground watch command and still needs a separate compiler
for admin TypeScript. Source mounts with in-container watchers let ordinary up
work in either foreground or detached mode.

## Consequences and transition

Initial startup builds the development images once. Code edits reload/recompile
without image rebuilds. Dependencies, Dockerfiles and development tooling can
require explicit rebuild/restart; numbered migrations remain explicit startup
operations. Worker interruption can leave work waiting for its existing lease
expiry. This decision does not redesign recovery or promise immediate retries.

Explicit docker compose -f compose.yaml retains production image targets and
opt-in profiles. Existing named application volumes are preserved. Running a
local switch must first account for pending migrations and the repository's
backup/audit rules. No live migration or startup is established by this decision.

## Verification and contract updates

DEV-A1–A4 in the [completed delivery plan](../archive/streamlined-local-development-work-packages.md)
define acceptance: merged/default and base
config, real source reload, frontend failed-build recovery, process shutdown,
existing durable queue/public-edge checks and consistent references. Closure and
exact evidence are retained in the completed plan; accepted design is not proof
of deployment. Update AC-05 and current runtime references together.
