# Completed plan: streamlined local development

Archived 2026-10-10 because DEV-1 and DEV-A1–A4 are complete, including local
runtime activation. Source remains uncommitted and unmerged.

# Streamlined local development

## Feature contract

- Status: complete, 2026-10-10.
- Authorization: user wants a minimal Compose command, all features including
  Sheets enabled, backend/frontend changes reflected with as few builds as possible.
- Outcome: default `docker compose up` selects the automatically merged local
  development override, includes admin/Sheets, and updates source without image
  rebuilds. Explicit `-f compose.yaml` retains production image/profile behaviour.
- Non-goals: new app processing logic, schema/queue changes, dependency upgrades,
  secrets generation, automatically changing database schema on source edits.
- Baseline HEAD: `8b3910acdf88bddb87e4f10a41819c6bfad595b6`, dirty PTR, token-free
  review and Inputs filtering implementation. Existing compose.yaml, root/docs
  references, frontend API/page/styles/tests and .env.example are modified;
  preserve them and untracked implementation/review/archive files.
- Existing owners: Compose runtime, Uvicorn reload, watchfiles supplied by
  uvicorn[standard], frontend dependency-free build/serve scripts.
- AC IDs: AC-04 (durable restart/recovery), AC-05/07 (internal/public boundary),
  AC-06 (safe frontend), AC-08 (runtime configuration), AC-09 (integration).
- Decision: ADR-0005 makes repository defaults development/all-feature while
  preserving explicit production topology and loopback-only admin exposure.
- Dependencies revalidated: Compose v5.3.1 installed; watchfiles CLI available;
  service-account file exists; production workers use durable claims and existing
  ownership validation. No active predecessor package.
- Compatibility/recovery: no migration/new dependency. First build once, later
  dependency/Docker changes rebuild affected images. Explicit base config is
  rollback to production commands; persistent volumes are unchanged. Existing
  pending migrations still require their backup/audit before local startup.

| Boundary | Change | Consumers / evidence |
| --- | --- | --- |
| Compose discovery | default includes development override and admin/Sheets | resolved config, isolated service smoke checks |
| Python source | read-only mounts + API reload / worker supervision | HTTP changes, worker process restart and existing claim recovery tests |
| Admin runtime | development image target + automatic staged builds | HTTP TS/CSS/HTML edits, failed build preserves prior output, signals |
| Public assets | read-only local asset/config mounts | public-edge allowlist/CSP remain authoritative |

## Pipeline

| Package | Status | Dependencies | Output | Acceptance |
| --- | --- | --- | --- | --- |
| DEV-1 | complete | Existing Compose/build/worker owners | integrated local workflow and references | DEV-A1–A4 |

Next ready package: none. Integration owner: DEV-1; all acceptance is closed.

## Local contract and acceptance

No credentials are logged or committed. Missing Sheets credentials fail the
importer’s readable-file preflight before polling starts; the bind mount also
requests no host-path creation. Startup retains migrations
and model initialization. All backend services use one shared development image.
Source mounting never replaces .venv/node_modules. Python worker reload sends
interrupt and allows cleanup; abandoned durable work follows the existing lease
recovery, possibly delayed until expiry. No worker may save after losing ownership.
Frontend changes build serially into staging and publish only after successful
compilation; failure preserves the last successful output and retries after edits.
Bind-mounted edits are detected on Linux/Docker Desktop through polling. Stop
cleans up supervised processes. Browser refresh loads new frontend output.

- [x] DEV-A1: default resolved model contains all features, one backend image,
  correct source mounts and no added API/database/model host ports. Explicit base
  preserves profile/production behaviour; missing credential files are rejected.
- [x] DEV-A2: real development services reflect TS/CSS/HTML and backend Python
  edits without image builds; invalid TS preserves valid assets and correction
  recovers; worker supervision restarts and stops cleanly.
- [x] DEV-A3: frontend checks, backend queue/public-edge checks and appropriate
  isolated smoke checks pass with exact commands and limitations recorded.
- [x] DEV-A4: ADR/contracts and root/admin/operations/current-state references
  agree, links/diff checks pass, durable handoff and next assumptions recorded.

References: ADR-0005, AC-05/08, architecture, operations, README, admin README,
current state, documentation/archive guide. Deployment/local switch requires
inspection of active installation and pending migration audit before starting it.

## Completion evidence and handoff (2026-10-10)

All evidence uses the dirty working tree at the recorded baseline, including
preserved PTR/filter/review work. No commit or merge was performed.

- DEV-A1: `docker compose config --format json` resolved all 12 services,
  profile-free admin/Sheets, one image for six Python services, a separate admin
  development image, read-only source mounts and no host API/database/model
  ports. Assertions checked loopback admin exposure. `docker compose -f
  compose.yaml --profile admin --profile google-sheets config --format json`
  verified original production profiles, commands and no Python source mounts.
- DEV-A2: `npm run typecheck && npm test` in frontend/admin passed typecheck
  and all 54 tests without skips, including HTTP TypeScript/CSS/HTML edits,
  invalid-TypeScript preservation, correction recovery and process shutdown.
  Initial sandbox execution could not bind the HTTP port and timed out;
  rerunning with local-port permission passed. `python3
  scripts/verify-development.py` passed real Uvicorn HTTP source reload, exactly
  one restarted embedding child, unchanged image IDs, supervised shutdown and
  missing-credential rejection on disposable PostgreSQL/source copies.
- DEV-A3: `docker compose -f compose.test.yaml up --build
  --abort-on-container-exit --exit-code-from tests` exited 0: all 304 backend,
  PostgreSQL, durable queue, API and public-edge tests passed without skips
  (64.929 seconds). The disposable test stack was removed afterward. No
  application database was used by these tests. Two initial smoke attempts
  revealed that this Docker Desktop/Compose 5.3.1 combination creates a missing
  bind directory despite create_host_path=false. Added an explicit readable-file
  preflight before the Sheets watcher; the corrected smoke passed. Missing
  credentials fail polling startup, but host-path noncreation is not guaranteed
  by this environment. The preflight logs no credential values.
- Local activation: `docker compose build api admin-web` built development
  images; the admin was subsequently given its own image tag and rebuilt from
  cache. `docker compose up -d --wait` completed successfully without a build
  flag. Existing taxonomy shutdown used its configured grace period. Before
  startup, migration markers 044–048 were already applied and the questionless
  input count was zero; no new schema migration was needed. Named application
  database/model volumes were preserved. Retired, already-stopped orphan
  containers were left untouched.
- Live checks: `docker compose exec -T <service> python -c ...` inspected
  /proc for the exact module argument: one active child each for Sheets,
  eligibility, embeddings, taxonomy scheduling and article generation.
  HTTP probes from the API container returned 200 for admin health, Inputs
  shell, token-free /api/taxonomy-runs, /api/inputs?limit=1 and public health;
  public review API and Inputs paths returned 404. No application response
  content or secrets were printed. These establish local runtime activation,
  not remote production deployment or fresh Google transport/model evaluation.
- DEV-A4: ADR-0005, AC-05, architecture, operations, root/admin README,
  credential example and current-state/guide/archive references updated.
  `git diff --check` and changed-document relative-link checks passed.
  No active plan remains after archival.

Delivered: ordinary `docker compose up` runs all local features; Python reloads
and staged frontend compilation incorporate source edits without image builds.
Dependencies/Dockerfiles still require an affected-image build, frontend edits
need browser refresh, nginx config needs restart, and migrations retain their
existing backup/startup procedure. Interrupted work can wait for lease expiry.
Production rollback uses explicit -f compose.yaml with its original profiles
and rebuilt production images; persistent volumes do not change.

Next-session inputs: completed runtime/ADR references and scripts/verify-development.py.
No remaining DEV-1 work. Future features must revalidate the dirty checkout and
migration state rather than infer them from HEAD or these historical test counts.
