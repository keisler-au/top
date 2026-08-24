# Remaining dashboard and article work packages

This document is the implementation handoff for work that remains after WP1,
WP2, WP5, WP6, WP7, and the form-source portion of WP10. It preserves the
original work-package numbering so future changes can refer to a stable plan.

## Completed baseline

The following work is complete:

- **WP1:** dashboard product and data contract in
  [`dashboard-product-contract.md`](dashboard-product-contract.md).
- **WP2:** dashboard summary, taxonomy, evidence, and recommendation read APIs.
- **WP5:** form-source administration API.
- **WP6:** framework-free TypeScript/Web Components frontend foundation.
- **WP7:** responsive overview and taxonomy coverage dashboard.
- **WP10 forms:** registration, editing, health display, and polling controls.

The current dashboard is useful for evidence discovery, but article-related
metrics intentionally return zero. `dashboard_queries.py` contains these
transitional zero projections. WP3 must replace them with real aggregates.

The remaining recommended order is:

```text
WP3 ──→ WP4 ──→ WP8 ──→ WP9
  │       │
  │       └────→ WP10 templates
  └────────────→ WP11

WP11 ──→ WP12
```

## Decisions inherited from WP1

Future work must preserve these rules:

- Canonical evidence uses segments for split inputs and the original for
  unsplit inputs. A split original is never counted alongside its segments.
- Generated articles begin in a non-approved state.
- Approval is a separate explicit backend transition.
- Approved articles determine coverage; drafts do not make an item covered.
- Articles must be tagged with at least one theme or topic.
- Article evidence must remain traceable to the untouched source response.
- Themes resolve to canonical live roots; merged aliases are not separate
  dashboard tags.
- The initial deployment remains a trusted single-operator environment until
  authentication is deliberately added.

---

## WP3 — Article persistence, tagging, evidence, and approval state

### Objective

Introduce the durable article model required for real coverage counts,
editorial review, approval, and evidence provenance.

### Database work

Add the next numbered PostgreSQL migration and update the fresh-install
snapshot. The exact filename should follow the latest migration present when
work begins, for example `012_add_articles.sql` if `011` is still latest.

Add an `articles` table with at least:

- `id`;
- `title`;
- `status`: `draft`, `ready_for_review`, `approved`, or `archived`;
- validated structured article content in `JSONB`;
- rendered HTML, nullable until rendering has succeeded;
- optional generation metadata in `JSONB`;
- `created_at` and `updated_at`;
- `approved_at`, present only in `approved` state;
- `archived_at`, present only in `archived` state.

Use database checks for non-empty titles, valid lifecycle states, and
timestamp/state consistency. Approved content must not be mutated in place.
Choose and document one of these revision models before implementation:

1. immutable `article_revisions` with `articles.current_revision_id`; or
2. copying an approved article into a new draft before editing.

The revision-table model is recommended because it gives the cleanest audit
history.

Add article taxonomy links:

- `article_themes(article_id, theme_id)` referencing canonical themes;
- `article_topics(article_id, topic_key, topic_name)` until topics have their
  own normalized table.

Topic keys must use the WP1 normalization rule. Enforce case-insensitive
uniqueness per article. Do not tag a merged theme alias; resolve it to the live
canonical root before insertion.

Add `article_evidence` with:

- `article_id` or revision ID, depending on the revision design;
- exactly one of `original_input_id` or `segment_input_id`;
- deterministic `evidence_order`;
- optional section/citation identifier;
- the evidence topic key used during generation;
- created timestamp.

Prefer `ON DELETE RESTRICT` for referenced evidence. If source deletion is
introduced later, it needs an explicit archival/redaction design rather than
silently breaking approved article provenance.

Add an approval audit table with:

- article/revision ID;
- action such as `submitted`, `approved`, `returned_to_draft`, or `archived`;
- timestamp;
- optional actor field reserved for future authentication;
- optional review note.

### Backend API

Add article schemas and routes following the existing FastAPI conventions:

```text
GET    /articles
POST   /articles
GET    /articles/{id}
PATCH  /articles/{id}
POST   /articles/{id}/submit
POST   /articles/{id}/approve
POST   /articles/{id}/return-to-draft
POST   /articles/{id}/archive
GET    /articles/{id}/evidence
GET    /articles/{id}/history
```

List filters should include lifecycle status, theme, topic, search, page, and
page size. Return bounded, deterministic pagination metadata consistent with
the dashboard APIs.

Approval must run in one transaction and verify that:

- the article is `ready_for_review`;
- structured content and rendered HTML are present;
- at least one theme or topic is tagged;
- every evidence reference still resolves;
- `approved_at` and audit history are written atomically.

### Dashboard integration

Replace all transitional article zeros in
`backend/src/triage_processor/api/dashboard_queries.py`:

- global active article count;
- awaiting-approval count;
- per-theme total and approved counts;
- per-topic total and approved counts.

Counts must use `COUNT(DISTINCT article_id)` and exclude archived articles.
Theme counts must resolve article theme tags to canonical roots. Dashboard
coverage and recommendation order must update immediately after approval or
archival.

Do not add generation failure counts in this package unless generation jobs
are implemented here; WP4 otherwise owns that counter.

### Tests

- Migration tests for lifecycle and exactly-one-evidence constraints.
- Article CRUD and filter tests.
- Canonical theme tag tests.
- Case-insensitive topic tag tests.
- Approval transaction rollback tests.
- Approved-content immutability/revision tests.
- Dashboard aggregation tests proving that multi-tag joins do not inflate
  global or per-taxonomy counts.
- Recommendation tests showing that approval changes least-covered ranking.

### Acceptance criteria

- Every active article has at least one theme or topic tag.
- Evidence provenance is queryable for every generated or approved revision.
- Generated/draft content is never counted as approved coverage.
- Approval is explicit, auditable, and transactional.
- Approved content cannot be silently overwritten.
- Dashboard article and coverage counts are real rather than placeholder
  zeros.

---

## WP4 — Safe templates and asynchronous article generation backend

### Objective

Generate evidence-grounded article drafts using a selected versioned HTML
template without allowing the LLM to author unrestricted executable HTML.

### Template persistence

Add:

- `article_templates`: stable identity, name, description, active/archived
  state, timestamps;
- `article_template_versions`: template ID, monotonically increasing version,
  HTML source, allowed placeholders, timestamps, and optional creator field.

Template versions become immutable once used by an article. A template update
creates a new version instead of modifying history.

Seed one usable starter template so generation works on a fresh installation.

### Template format and security

Define a small documented placeholder grammar, for example:

```text
{{title}}
{{standfirst}}
{{article_body}}
{{published_at}}
```

Do not use arbitrary expression evaluation. Validate templates on creation:

- reject scripts, inline event handlers, unsafe URL schemes, embeds, and
  executable forms;
- require essential placeholders exactly once where appropriate;
- restrict remote assets according to the eventual Content Security Policy;
- render all scalar content with HTML escaping;
- sanitize the final rendered result server-side.

Use a maintained HTML sanitizer rather than regular expressions. Adding that
dependency requires updating `backend/pyproject.toml` and `uv.lock`.

### Structured generation contract

The LLM must return validated JSON, not finished HTML. Define a strict schema
such as:

```json
{
  "title": "...",
  "standfirst": "...",
  "sections": [
    {
      "heading": "...",
      "paragraphs": ["..."],
      "evidence_ids": ["segment:18", "original:42"]
    }
  ],
  "theme_ids": [7],
  "topic_keys": ["cost barriers"]
}
```

Validate that:

- every cited evidence ID was included in the job's frozen evidence set;
- returned tags are within the selected target and allowed related taxonomy;
- every section has usable content;
- length limits are enforced;
- unknown fields or malformed structures fail the job rather than being
  silently accepted.

### Generation jobs

The existing `worker_jobs` table is tied to `original_input_id` and input
pipeline stages. Do not overload it. Add `article_generation_jobs` containing:

- status: `pending`, `processing`, `completed`, `failed`, `dismissed`;
- requested strategy and taxonomy type/key;
- template version;
- optional editorial guidance;
- frozen evidence selection or a job-evidence join table;
- attempt count, lease fields, retry timing, and last error;
- resulting article ID;
- timestamps.

Use the same durable lease, retry, and dead-letter principles as the current
PostgreSQL worker queue. Add an article-generation worker service to Compose.

Generation flow:

1. Validate target and generation eligibility.
2. Resolve canonical evidence in a transaction.
3. Freeze the selected evidence IDs and template version.
4. Enqueue the job.
5. Send structured context to the LLM worker.
6. Validate the response and citations.
7. Render through the frozen template version.
8. Create an article in `ready_for_review` state with tags and evidence in one
   transaction.
9. Mark the job completed with its resulting article ID.

### Backend API

```text
GET    /article-templates
POST   /article-templates
GET    /article-templates/{id}
POST   /article-templates/{id}/versions
POST   /article-templates/{id}/preview
POST   /article-templates/{id}/archive

POST   /article-generation-jobs
GET    /article-generation-jobs/{id}
POST   /article-generation-jobs/{id}/retry
POST   /article-generation-jobs/{id}/dismiss
```

The create-job response should be `202 Accepted` and include a stable job URL.
Retry must be idempotent and unavailable for a processing or completed job.

Update `/dashboard/summary` so `failed_generation_count` counts unresolved
failed jobs.

### Tests

- Template version immutability.
- Placeholder validation and HTML escaping.
- Rejection of scripts, event handlers, unsafe links, and malformed HTML.
- Structured LLM response validation.
- Rejection of citations outside the frozen evidence set.
- Job claiming, lease expiry, retries, and dead-letter behavior.
- Transaction rollback when article, tag, evidence, or render persistence
  fails.
- Job refresh/recovery after a simulated worker restart.

### Acceptance criteria

- The LLM never controls the outer HTML template directly.
- Every generated claim/section can be traced to allowed evidence IDs.
- Generation is asynchronous, retryable, and recoverable after browser or
  worker restart.
- Success creates a reviewable article, never an approved article.
- A template version used by an article cannot change afterward.

---

## WP5 — Form-source administration API

**Status: completed.** The requirements below are retained as the implemented
contract and regression checklist.

### Objective

Expose safe administration of the existing `form_sources` registry so the
frontend no longer requires manual SQL.

### Backend API

```text
GET    /form-sources
POST   /form-sources
GET    /form-sources/{id}
PATCH  /form-sources/{id}
POST   /form-sources/{id}/enable
POST   /form-sources/{id}/disable
```

Return:

- form ID and source;
- spreadsheet ID and sheet name;
- ignored headers;
- polling interval and enabled state;
- `last_read_row`, `last_polled_at`, `next_poll_at`, and `last_error`;
- created and updated timestamps.

Do not accept, persist, or return Google service-account credentials. Those
remain mounted server-side as documented in `google-sheets.md`.

### Validation

- Match current database uniqueness rules for `(source, form_id)` and
  `(spreadsheet_id, sheet_name)`.
- Trim all required text and reject blank array entries.
- Enforce a positive, bounded polling interval.
- Do not allow a UI update to move `last_read_row` backward or edit poller
  health fields directly.
- Return `409` for registry conflicts and useful `422` messages for invalid
  input.

A manual “poll now” endpoint is optional. If implemented, it must coordinate
with the existing `FOR UPDATE SKIP LOCKED` claim behavior and must not start a
second concurrent poll of the same form.

### Tests

- Create/list/update/enable/disable flows.
- Duplicate registry conflicts.
- Health fields remain server-owned.
- Credentials never appear in OpenAPI schemas or responses.
- Disabling a source prevents poller claims.
- Existing questions and inputs remain linked after editable metadata changes.

### Acceptance criteria

- A form can be registered and managed without database access.
- Polling health and errors are visible without exposing secrets.
- API changes cannot corrupt the cursor or create duplicate pollers.

---

## WP8 — Article generation frontend workflow

### Objective

Replace the `/generate` placeholder with a mobile-friendly workflow covering
specific targets, most-evidence recommendations, and least-covered
recommendations.

### Frontend behavior

Implement a route-level Web Component under `frontend/src/pages`. Continue to
use native Web Components, TypeScript, browser modules, and the existing CSS
system; do not introduce React, Vite, or another runtime framework.

The workflow should have progressive steps:

1. **Strategy:** specific target, most evidence, or least covered.
2. **Target:** theme/topic choice with recommendation explanation and counts.
3. **Evidence:** inspect the frozen candidate set and optionally deselect items
   if backend policy allows it.
4. **Template:** select an active template version and preview its structure.
5. **Guidance:** optional bounded editorial instructions.
6. **Confirm:** summarize target, evidence count, template, and tags.
7. **Progress:** submit and poll the durable job.

The existing WP7 links provide query parameters:

```text
strategy=specific
type=theme|topic
key=...
name=...
source_strategy=most-evidence|least-covered   # optional
```

Initialize the workflow from these values, but revalidate the target through
the API. Never trust a name or eligibility value from the URL.

### State and recovery

- Keep step, target, and filters in the URL where practical.
- The backend job ID is the durable source of truth.
- Store the active job ID in the route URL after submission.
- Refreshing or reopening the job URL must resume status polling.
- Stop polling when completed, failed, dismissed, or when the component
  disconnects.
- Use increasing poll intervals and pause/reduce polling when the document is
  hidden.

On success, navigate to the resulting article review route. On failure, show
the backend error, retry eligibility, and a safe path back to editing the
request.

### Accessibility and mobile behavior

- One primary action per step.
- Native form controls and fieldsets for strategy and taxonomy choices.
- Validation summary plus field-associated errors.
- Evidence preview uses the existing provenance card behavior.
- Progress changes use a polite live region.
- Mobile layouts avoid side-by-side mandatory panels and horizontal scrolling.
- Navigation away from an unsubmitted request may ask for confirmation; never
  block navigation merely because a durable job is running.

### Tests

- URL initialization from WP7 generation links.
- Strategy and target changes.
- Stale/ineligible target response.
- Template selection and preview errors.
- Job submission payload.
- Polling completion, failure, retry, refresh recovery, and cancellation on
  disconnect.
- Keyboard and 320px-wide workflow tests in a real browser.

### Acceptance criteria

- All three required generation strategies are usable on mobile and desktop.
- Evidence is inspectable before generation.
- Refreshing during generation does not lose the job.
- Success produces a `ready_for_review` article and opens it for review.
- Generation never performs approval.

---

## WP9 — Article library, editor, provenance, and approval frontend

### Objective

Replace the `/articles` and `/articles/:id` placeholders with the editorial
library and human-review workspace.

### Article library

Provide:

- search;
- lifecycle status filter;
- theme/topic filters;
- deterministic server pagination;
- title, tags, evidence count, status, and updated timestamp;
- clear failed-generation and awaiting-review entry points;
- mobile cards and a desktop table/list.

Filters, sort, and page belong in the URL. Returning from an article should
restore the library view.

### Article workspace

Provide:

- structured content editing rather than raw unrestricted HTML editing;
- rendered template preview in a sandboxed iframe;
- evidence provenance panel/drawer;
- theme and topic tag management;
- save status and recoverable API errors;
- revision/history information;
- submit-for-review action;
- approval confirmation showing what will become approved;
- return-to-draft and archive actions when valid.

Do not inject article HTML directly into the dashboard document. Render it in
a sandboxed iframe using `srcdoc` or a dedicated same-origin preview endpoint
with a restrictive Content Security Policy.

For an approved revision, editing must begin a new revision or copy rather
than mutating approved content.

### Data refresh

After save, approval, return-to-draft, or archive:

- invalidate relevant `QueryStore` keys;
- refresh article detail;
- refresh dashboard summary/taxonomy counts when the user next visits them;
- do not synthesize coverage counts locally.

### Tests

- Library URL state, filters, pagination, empty/error states.
- Structured editor save and conflict handling.
- Evidence drawer and original-source disclosure.
- Preview isolation and script non-execution.
- Approval confirmation and invalid-state rejection.
- Approved revision immutability.
- Dashboard coverage refresh after approval and archival.

### Acceptance criteria

- Editors can find, inspect, edit, and review generated drafts.
- Evidence remains available alongside the article.
- Preview content cannot execute in the main application context.
- Approval is explicit and its audit entry is visible.
- Approved content is revision-safe.

---

## WP10 — Template and form-source administration frontend

**Status: partially completed.** Form-source administration is implemented;
template administration remains outstanding.

### Objective

Replace the `/templates` and `/forms` placeholders after WP4 and WP5 APIs are
available.

### Template screens

Implement:

- template list with active/archived state;
- create-template form;
- new-version editor;
- allowed-placeholder reference;
- server-rendered preview using sample structured content;
- version history and “used by articles” indicators;
- archive action with confirmation.

Use a plain text/code textarea for template HTML initially. Do not add a large
rich-text or code-editor dependency unless explicitly approved. Display server
validation errors at the relevant field and in a summary.

Preview must use the same isolated rendering policy as article preview.

### Form screens

The form screens described below are complete and should be preserved by
future changes.

Implement:

- registered form-source list;
- create/edit form;
- enable/disable controls;
- last poll, next poll, last imported row, and last error;
- clear operational guidance for sharing a sheet with the configured service
  account;
- long spreadsheet IDs and error text that wrap safely on mobile.

Do not add credential upload fields. Explain that credentials are configured
on the server.

### Tests

- Template create/version/archive/preview flows.
- Unsafe-template validation presentation.
- Form create/edit/conflict/enable/disable flows.
- Polling health and error presentation.
- Keyboard operation and 320px layouts.
- Confirmation dialogs return focus to their trigger.

### Acceptance criteria

- Administrators can manage templates without changing code or SQL.
- Administrators can register and monitor forms without changing SQL.
- Unsafe templates never execute in the dashboard context.
- Google credentials remain outside the browser and API.

---

## WP11 — Integration, database, browser, accessibility, and security testing

### Objective

Add the verification layers that are intentionally absent from the current
unit-heavy implementation.

### Current gaps to close

- Dashboard SQL is tested with API fakes and query-contract assertions, but it
  needs execution against a real PostgreSQL schema with representative data.
- Frontend tests cover pure TypeScript modules, but Web Components and user
  flows need real DOM/browser tests.
- There is no automated accessibility scan.
- There is no article/template security corpus yet.

### Database integration tests

Seed cases for:

- split and unsplit evidence;
- multiple segments from one original;
- repeated responses;
- case-variant topics;
- many-to-many theme/topic membership;
- merged theme alias chains and invalid cycles;
- articles carrying several tags;
- draft, approved, and archived articles;
- pagination tie-breakers.

Execute dashboard queries against PostgreSQL and assert exact totals and
ordering. Prove that aliases and join multiplicity do not double-count.

### Browser tests

Use a lightweight real-browser runner such as Playwright only after approval
to add that development dependency. Critical flows:

```text
dashboard → filter/sort/page → inspect evidence
dashboard → recommended target → generate → recover polling → review
review → inspect provenance → approve → dashboard coverage changes
forms → register source → see status
templates → create version → preview → use for generation
```

Run at least at 320px, a tablet width, and a desktop width. Verify keyboard
navigation, focus restoration, responsive table/cards, dialogs, and deep-link
refresh.

### Accessibility

- Automated axe-style scans on every primary route.
- Manual heading and landmark review.
- Keyboard-only completion of critical flows.
- Screen-reader review of loading, error, status, and progress announcements.
- Contrast checks for every token/state.
- Reduced-motion verification.

### Security tests

- Stored and reflected XSS attempts in evidence, article content, names,
  guidance, errors, and form metadata.
- Template scripts, event handlers, SVG payloads, unsafe links, CSS escapes,
  and malformed markup.
- Preview sandbox breakout attempts.
- Oversized generation and template payloads.
- Unauthorized approval tests once authentication exists.

### Acceptance criteria

- Canonical counts are proven against PostgreSQL, not only mocked calls.
- Critical workflows pass in real browsers at required viewport widths.
- Primary routes have no serious automated accessibility findings.
- Unsafe template and generated content cannot execute in the dashboard.

---

## WP12 — Production packaging, deployment, and operations

### Objective

Run the completed frontend and backend as one documented, reproducible stack.

### Frontend dependency reproducibility

The frontend now has `frontend/package-lock.json`. Preserve it and keep it in
sync with `package.json`. CI and container builds must use `npm ci`, not an
unlocked install.

### Production frontend service

Add a multi-stage container build:

1. Node build stage runs `npm ci`, typecheck, tests as appropriate, and
   `npm run build`.
2. Minimal static web server stage serves `dist`.

Production needs:

- History API fallback to `index.html`;
- `/api/*` reverse proxy to FastAPI, stripping the `/api` prefix as the current
  development server does;
- long-lived caching for fingerprinted assets and no-cache for `index.html`;
- compression;
- health check;
- request/body limits;
- security headers and Content Security Policy.

Asset filenames currently are not fingerprinted. Add a small manifest/hash
step or configure conservative caching until fingerprinting exists.

### Compose and documentation

Add a `frontend` service to `compose.yaml`, expose one user-facing port, and
keep PostgreSQL/Ollama/API internal where appropriate for production. Update
root documentation so the normal command starts a usable UI:

```text
docker compose up --build
```

Document development, production, Google Sheets profile, environment
variables, volumes, backup/restore, and model startup behavior.

### Observability

Add structured logging and operational views for:

- article generation queue depth and failures;
- average generation duration;
- form polling failures and cursor age;
- approval transitions;
- API latency/error counts.

Never log complete source responses, generated article bodies, service-account
credentials, or LLM authorization headers by default.

### Authentication decision gate

Before any deployment outside a trusted single-operator environment, add
authentication and authorization. At minimum separate read access from
template/form administration and article approval. This is a release gate,
not something the frontend should simulate.

### Acceptance criteria

- A clean checkout builds reproducibly with locked backend and frontend
  dependencies.
- One documented Compose command starts a working UI and API.
- Deep links, API proxying, caching, and health checks work in the container.
- Security headers are present and preview policy is isolated.
- Operational failures can be diagnosed without exposing sensitive content.

---

## Definition of done for the complete feature set

The dashboard/article initiative is complete when:

- themes and topics show canonical evidence and real article coverage;
- an editor can generate from a specific target, most evidence, or least
  coverage;
- generation uses frozen source evidence and a safe versioned template;
- every article is tagged and evidence-traceable;
- generated drafts can be reviewed, revised, and explicitly approved;
- administrators can manage templates and form sources through the UI;
- critical flows are tested against PostgreSQL and real browsers;
- the complete stack has a reproducible, secure production packaging path.
