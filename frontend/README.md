# Evidence dashboard frontend

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

The Overview route uses the WP2 dashboard endpoints for summary metrics,
URL-backed coverage exploration, recommendations, editorial attention states,
and paginated evidence provenance. Forms registers and manages Google Sheets
poller sources. Generate provides the durable article-generation workflow, and
Articles provides the filterable library plus revision-safe editorial review,
provenance, preview, and approval workspace. Template administration is nested
inside the generation workflow’s Template step. Legacy `/templates` URLs redirect
with history replacement to `/generate`, discarding template-page query/hash
state so users start with a validated generation request.

## Manual browser verification

Browser functionality is tested manually for now using the
[NAV-WP4 checklist](../docs/manual-navigation-checklist.md). Playwright and axe
automation are deferred in [future recommendations](../docs/future-recommendations.md).
The existing `npm test` command continues to run the Node unit tests.
