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
`dist/`. `npm run dev` serves that directory at `http://localhost:4173` and
proxies `/api/*` to `API_BASE_URL`, which defaults to
`http://localhost:8000`.

Override either port when needed:

```bash
FRONTEND_PORT=3000 API_BASE_URL=http://localhost:8080 npm run dev
```

The Compose `admin-web` service is deliberately opt-in and bound to loopback:
`docker compose --profile admin up --build`, using
`127.0.0.1:${ADMIN_PORT:-8081}`. It is not the public website edge.

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

Taxonomy views and generation targets use the one published batch run. Before
the first publication the API returns `taxonomy_unavailable`; it never falls
back to retired incremental topic/theme data. Historical classifications are
available only through the protected archive audit API, not this dashboard.

## Verification

`npm test` runs the frontend unit tests. Cross-service lifecycle and taxonomy
reliability work is tracked in the
[documentation guide](../docs/README.md) and its active
[work-package plan](../docs/work-packages.md).
