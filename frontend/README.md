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

The overview and Themes & Topics routes use the WP2 dashboard endpoints. They
provide summary metrics, URL-backed coverage exploration, recommendations,
editorial attention states, and paginated evidence provenance. The Forms route
registers and manages Google Sheets poller sources. Article, template, and
generation workspaces remain route placeholders for their respective work
packages.
