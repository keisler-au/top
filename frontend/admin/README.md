# Administrative dashboard frontend

This is a framework-free TypeScript application built with native Web
Components, browser ES modules, and CSS. TypeScript is the only development
dependency; there are no runtime packages and no bundler.

## Commands

```bash
npm run typecheck
npm run build
npm test
npm run dev
```

`npm run build` compiles TypeScript and copies the static shell and styles to
`dist/`. `npm run dev` watches TypeScript, CSS and HTML, stages successful
builds, and serves the latest valid output at `http://localhost:4173`. Refresh
the browser after edits. Compilation errors preserve the previous valid build;
fixing source retries automatically. The first build must succeed before the
server starts. It also proxies `/api/*` to `API_BASE_URL`, which defaults to
`http://localhost:8000`.

The taxonomy verification workflow runs `npm test` and `npm run typecheck` for
changes under `frontend/admin/`; the full automatic-taxonomy Compose journey is
documented in [Operations](../../docs/operations.md#automatic-taxonomy-acceptance).

Override either port when needed:

```bash
FRONTEND_PORT=3000 API_BASE_URL=http://localhost:8080 npm run dev
```

The default `docker compose up` starts `admin-web` with mounted sources and
the development watcher, bound to `127.0.0.1:${ADMIN_PORT:-8081}`. The initial
switch needs one image build; later source edits need a browser refresh.
Dependencies require `docker compose build admin-web` followed by startup.
Explicit production mode uses `docker compose -f compose.yaml --profile admin
up -d --build` and the nginx image. The public website retains its separate edge.

The server falls back to `index.html` for unknown static paths so History API
routes remain refreshable and deep-linkable.

## Source layout

- `src/api` contains typed backend contracts, fetch behavior, and normalized
  errors.
- `src/components` contains reusable native Web Components.
- `src/pages` contains route-level light-DOM components.
- `src/state` contains the request-deduplicating query cache.
- `src/styles` contains mobile-first design tokens and global styles.
- `scripts` contains the dependency-free build and static development server.

The Overview route uses dashboard endpoints for summary metrics,
URL-backed coverage exploration, recommendations, editorial attention states,
and paginated evidence provenance. Forms registers and manages Google Sheets
poller sources. Generate provides the durable article-generation workflow, and
Articles provides the filterable library plus revision-safe editorial review,
provenance, preview, and approval workspace. Template administration is nested
inside the generation workflow’s Template step. Legacy `/templates` URLs redirect
with history replacement to `/generate`, discarding template-page query/hash
state so users start with a validated generation request.

Every input now has immutable question context. The typed input contract treats
`question_id` and `question_context` as required; historical rows must pass the
migration 044 audit before the matching API/admin images are started.

Taxonomy views and generation targets use the one published batch run. Before
the first publication the dashboard renders a bounded first-run recovery
message; a terminal candidate failure renders a bounded failed-stage message,
and a failed automatic gate renders a bounded quality-blocked message. Newer
candidate progress takes precedence over stale failed history. It
never falls back to retired incremental topic/theme data. Historical classifications are
available only through the protected archive audit API, not this dashboard.
First-run errors also distinguish a processing candidate, blocked automation,
and an unavailable scheduler with bounded messages. The protected operations
API holds the policy failure code; it is not included in public error text.

## Verification

`npm test` runs frontend tests, including an HTTP smoke test for source updates,
failed-build recovery and development-server shutdown. It requires permission
to bind a temporary local port. Cross-service lifecycle and taxonomy
reliability work is tracked in the
[documentation guide](../../docs/README.md) and
[work-package archive](../../docs/archive/work-packages.md).

PTR-5 backend compatibility: input responses omit `taxonomy_state`, retain
processing `status` and `published_taxonomy_run_id`, and return empty arrays for
uncovered inputs. Summary coverage fields count evidence with/without canonical
topics in exactly that published snapshot. The typed contracts mirror these
fields. Quality failure messaging uses completed processing, consistent evidence
links and at least one valid topic; low coverage and zero themes are valid.
Overview and Generate default to topics; explicit theme URLs still work.
An empty theme collection is normal and directs editors to Topics. Overview
shows total evidence, with-topic/without-topic counts and full/partial coverage.

`/inputs` pages through inputs in batches of 50 and renders published-run topic
and theme arrays, including normal empty associations, independently of evidence
processing status. Its filter form provides answer/question text search,
processing status, published topic presence, topic/theme name substrings and
inclusive UTC received dates. Additional attributes expose exact source/form,
question/version and submission keys, with visible dependency validation. Apply
and Clear reset paging; Refresh and Previous/Next preserve filters. Filter and
offset query parameters restore the view on deep links/reload. Filters run on
the server across the dataset; counts shown are for the current page, not totals.
Response cards show the matching source/form/question/version, received time
and submission key. `/taxonomy-review?run=<id>` is a read-only admin screen:
automatically load recent runs without a token, inspect canonical topics,
expand provisional antecedents and merge relationships, and explicitly load
canonical evidence. It also shows unresolved cluster support/reason codes,
unclustered evidence counts, publication checks and the run's processing status.
The API limits the review to 100 topics/clusters and 50 evidence rows per page;
the UI marks truncation and supports evidence paging. Deep links may select an
older run outside the latest-50 list.

Taxonomy review reads require no operator credentials and send no Authorization
header. The API and admin remain internal; the public edge denies review routes.
Taxonomy mutations, operations and legacy archive APIs retain their existing
credentials. Refresh/retry, run selection and navigation cancel owned requests.
Late responses cannot
replace the newer review/input/generation state. Source/model text uses safe
text rendering; raw prompts/model payloads are absent from review responses.

`tests/partial-taxonomy-components.test.mjs` executes production Web Components
in a small native-DOM harness, including partial coverage, empty themes/inputs,
automatic loading, server errors, provenance, stale responses and the zero-theme generation
steps through job creation. PostgreSQL/API and public HTTP evidence is recorded
in the completed [PTR plan](../../docs/archive/partial-taxonomy-and-reconciled-topic-work-packages.md).
PTR-8 also verifies the full Sheets/API, automatic-publication, generation and
public-delivery lifecycle; frontend typecheck, all 10 test files and build
passed on 2026-10-10. These checks do not claim
browser layout or production-model semantic evaluation.
