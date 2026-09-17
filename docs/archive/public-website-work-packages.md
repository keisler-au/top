# Public website work packages

**Status: archived — superseded and incorporated.** This is the source
proposal for the public website. Its reviewed, batch-aligned PW packages are
now in the [current work packages](../work-packages.md); do not implement this
historical version directly.

This plan adds a public, read-only
publication site alongside the existing internal evidence dashboard. It is
deliberately independent of the unfinished candidate-taxonomy path: public
pages publish approved article revisions and their already attached canonical
themes, rather than reading a mix of live taxonomy state and candidate runs.

No package has a human approval, design-sign-off, content-review, or manual
test gate. Existing article approval remains the product's publishing rule:
only an article that has reached the current `approved` lifecycle state is
eligible to appear publicly. All implementation checks are automated.

## What the repository does today

The project has a sound internal workflow:

```text
feedback -> segmentation -> embeddings -> topics -> themes
         -> evidence-grounded article generation -> editorial approval
```

The current `frontend/` application is an internal dashboard for that work. It
can inspect raw evidence, manage form sources and templates, generate drafts,
and transition article status. The sole frontend service currently proxies its
entire API surface, including `/articles/{id}/evidence`, operations, form
source, and generation endpoints. Those behaviours must not be exposed from a
public site.

The public website therefore has one purpose: help a general reader discover
and read approved, evidence-grounded articles. It does **not** accept feedback,
show respondent text, citation identifiers, source names, submission keys,
operations data, prompts, model metadata, draft content, or editorial history.

## Product and experience design

The site is an editorial library called **Evidence-led insights** by default.
`PUBLIC_SITE_NAME` can replace that label without a code change, so the
application does not invent an organisation name or make unsupported brand
claims.

### Public information architecture

| Route | Purpose | Data allowed |
| --- | --- | --- |
| `/` | Explain the evidence-led approach; feature the newest approved article and recent articles/themes. | Public article cards and public theme names only. |
| `/insights` | Paginated, searchable article library with a theme filter. | Approved publication cards only. |
| `/insights/{slug}` | Read one approved article revision; show public themes, publication/update dates, related approved articles, and a short methodology disclosure. | Sanitized rendered article HTML and public article metadata only. |
| `/themes` | Browse themes represented by at least one public article. | Public theme names and public article counts only. |
| `/themes/{id}-{slug}` | Browse approved articles attached to one canonical theme. A stale name redirects to the canonical route; an unknown or merged theme is `404`. | Public article cards and theme name only. |
| `/about` | Explain the collection-to-publication workflow, privacy boundary, and editorial approval rule. | Static copy only. |
| `/robots.txt`, `/sitemap.xml` | Make indexable pages discoverable. | Canonical public URLs only. |

There is intentionally no public topic directory. Topic IDs and names are
still in a legacy-to-run-scoped migration, while article/theme links are
durable enough for public navigation. Topic labels may appear as non-linking
context on an article only after they are explicitly included in the public
article contract; that is not part of this first release.

### Visual direction

- Use a calm editorial layout rather than the admin dashboard's persistent
  sidebar: a compact top header, generous reading width (about 44rem), cards
  for library browsing, and a clear footer.
- Keep the established forest/mint palette (`#153f3a`, `#216f63`, and light
  neutral surfaces) so the two applications feel related. Use the existing
  warm focus colour (`#f2a93b`) and system fonts; do not add remote fonts,
  trackers, stock imagery, invented testimonials, or fabricated statistics.
- Home contains a concise hero, one featured insight, a recent-insights grid,
  a public-theme list, and three plain-language steps: collect feedback,
  identify patterns, and publish an approved insight.
- The article page prioritizes title, standfirst, dates, themes, readable body
  typography, related insights, and the disclosure: “Published from an
  evidence-grounded workflow and approved before publication.” It never
  renders raw supporting inputs or per-article evidence counts.
- Search is a normal `GET` form and all navigation works without JavaScript.
  The site must have visible keyboard focus, a skip link, semantic landmarks,
  one `h1`, correctly nested headings, responsive layouts from 320px upward,
  and WCAG AA contrast.

## Target architecture and repository layout

```text
internet
  -> public-web (nginx, only public routes and static public assets)
       -> api /_site/* (server-rendered public HTML)
            -> PostgreSQL (approved publication projection only)

operator on localhost/private ingress
  -> admin-web (current dashboard, explicit `admin` Compose profile)
       -> api /api/* (internal dashboard routes)
            -> PostgreSQL, Ollama, workers
```

`api` remains internal to the Compose network. `public-web` must proxy only a
small, explicit URL allow-list to an internal `/_site` router; it must not use
a catch-all proxy. `admin-web` is not published by default and binds to
`127.0.0.1` when the `admin` profile is explicitly enabled. A production
private ingress may protect that loopback/private service further, but public
isolation must not depend on an external account or an untested manual step.

The intended repository shape after the migration is:

```text
backend/src/triage_processor/
  api/routes/                 # existing internal/admin HTTP routes
  public_site/                # public queries, rendering, schemas, service
  templates.py                # existing safe article-template renderer
frontend/
  admin/                      # moved, behaviour-preserving current dashboard
  public/                     # public CSS, SVG favicon, and public-web Docker/nginx config
infrastructure/postgres/migrations/
  023_add_article_publications.sql
docs/
  public-website-work-packages.md
```

The public site is server-rendered by FastAPI so article URLs are useful to
readers, crawlers, and shared links before JavaScript runs. `frontend/public`
contains static presentation assets only; no browser API client is needed.
The existing framework-free TypeScript dashboard remains a separate admin
application and continues to own its current typed API client, query cache,
and Web Components.

## Publication boundary

Add an `article_publications` projection rather than making the current broad
`/articles` API public. It has the following minimum shape:

```sql
article_id          BIGINT PRIMARY KEY REFERENCES articles(id)
article_revision_id BIGINT NOT NULL
slug                TEXT NOT NULL UNIQUE
first_published_at  TIMESTAMPTZ NOT NULL
updated_at          TIMESTAMPTZ NOT NULL
FOREIGN KEY (article_id, article_revision_id)
  REFERENCES article_revisions(article_id, id)
```

`slug` is deterministic and permanent: a normalized title plus the article ID
(falling back to `insight-{id}`) makes collisions impossible and requires no
new editorial form. On approval, the same transaction records the current
immutable revision, creates or refreshes the projection, and keeps the
original slug. On a later approved revision the route stays stable while the
projection points at the new immutable revision. Returning an article to draft
or archiving it needs no destructive delete: public queries require both an
existing projection and `articles.status = 'approved'`, so the page disappears
immediately and reappears only on a subsequent approval.

The migration backfills every already-approved article using its current
revision and a deterministic slug. The public query always reads the projected
revision, never a mutable draft revision, and derives a bounded plain-text
excerpt and reading time from the already-sanitized rendered HTML. It exposes
theme names only through canonical, non-merged `article_themes` links.

## Package sequence

```text
PW-WP1 repository split and transport isolation
  -> PW-WP2 durable approved-article publication projection
  -> PW-WP3 server-rendered public query and route layer
  -> PW-WP4 public interface and responsive design system
  -> PW-WP5 discovery, caching, and public security policy
  -> PW-WP6 end-to-end verification and operational documentation
```

Each package is independently mergeable once its automated acceptance criteria
pass. Later packages may change the public presentation without changing the
publication boundary.

## PW-WP1 — Repository split and transport isolation

### Objective

Separate the internal dashboard from the internet-facing delivery path without
changing dashboard behaviour.

### Work

- Move the current `frontend` application, including its `src`, tests, build
  scripts, Dockerfile, nginx configuration, package manifest, and README into
  `frontend/admin`. Update relative paths and Compose build contexts only; do
  not redesign admin routes or change its contracts in this package.
- Create `frontend/public` with a dedicated Dockerfile, nginx configuration,
  a public asset build/copy script, `assets/site.css`, and an SVG favicon.
  Keep the public asset build dependency-free, as the current frontend is.
- Replace the current externally exposed `frontend` Compose service with
  `public-web`, published on `${PUBLIC_PORT:-8080}:8080`. Add `admin-web` to
  the explicit `admin` profile, binding
  `127.0.0.1:${ADMIN_PORT:-8081}:8080`; it is absent from a normal
  `docker compose up`.
- Leave PostgreSQL, Ollama, API, worker, and importer ports internal. Rename
  `DASHBOARD_PORT` documentation to `PUBLIC_PORT` and document the explicit
  admin-profile command.
- Configure public nginx to serve `/assets/*`, `/favicon.svg`, and `/healthz`
  locally; reserve page routes for the later `/_site` proxy. Its fallback must
  be `404`, not an SPA fallback or a proxy to arbitrary API paths.
- Add a Compose smoke test proving public nginx cannot route `/api/*`,
  `/articles*`, `/inputs*`, `/operations*`, `/form-sources*`, or `/_site/*`
  directly. The last path is internal-only and may be reached only through
  nginx's explicit rewritten public routes in PW-WP3.

### Automated acceptance criteria

- `npm ci`, `npm run typecheck`, `npm test`, and `npm run build` succeed from
  `frontend/admin`, with all existing admin tests unchanged in intent.
- `docker compose up --build` exposes only `public-web` on the host by
  default; `docker compose --profile admin up --build` makes the dashboard
  available only on loopback.
- An automated nginx/container test gets `404` for each disallowed public
  route and `200` for public health and static assets.
- Existing API and worker tests continue to pass without a browser or network
  dependency.

## PW-WP2 — Durable approved-article publication projection

### Objective

Turn the existing `approved` lifecycle state into a safe, stable public
publication record without altering article revision or evidence provenance.

### Work

- Add migration `023_add_article_publications.sql`, required constraints,
  slug validation, publication lookup indexes, and a deterministic backfill
  for existing approved articles. Do not alter or copy raw evidence tables.
- Add a small publication service under `triage_processor/public_site` that
  generates an ASCII-safe deterministic slug, validates it, derives a bounded
  excerpt and reading-time estimate from sanitized HTML, and performs no
  database write during a public read.
- Extend the existing transactional approval transition to upsert the
  projection after all current approval prerequisites have passed. Preserve the
  first publication timestamp; refresh `article_revision_id` and `updated_at`
  on reapproval. Do not make a separate public “publish” action or new human
  workflow.
- Keep public selection defensive: the projected revision must belong to the
  article, the article must still be `approved`, the revision must have
  sanitized rendered HTML, and every displayed theme must be canonical.
- Define internal `PublicArticleCard`, `PublicArticleDetail`, and
  `PublicTheme` models that contain only slug, title, excerpt, public dates,
  reading time, public theme names, sanitized HTML, and related public cards.
  Prohibit `generation_metadata`, revision IDs, article IDs, evidence IDs,
  raw text, source identifiers, taxonomy descriptions, and audit fields.

### Automated acceptance criteria

- PostgreSQL integration tests verify migration from empty and current schema,
  backfill correctness, slug uniqueness, and the composite revision/article
  foreign-key relationship.
- Tests prove draft, `ready_for_review`, returned-to-draft, and archived
  articles are never returned by the public query; an approved article is;
  reapproval serves the new immutable revision at the original slug.
- Tests prove no public model or rendered response contains a raw evidence
  excerpt, original input ID, source, submission key, citation ID, generation
  metadata, audit actor, or internal numeric ID.
- Existing transition tests still prove approval is atomic: a failed audit or
  projection write rolls back both the article state and public projection.

## PW-WP3 — Server-rendered public query and route layer

### Objective

Provide a small, cacheable HTML surface whose data access is limited to the
publication projection.

### Work

- Implement `triage_processor.public_site.queries`, `service`, `renderer`,
  and a thin `api/routes/public_site.py`. Mount its routes below internal-only
  `/_site`; do not add public versions of the admin JSON APIs.
- Implement page queries for home, insight library, article detail, theme
  directory/detail, about, sitemap, robots, and a generic 404. Bound library
  pagination (default 12, maximum 48, offset at most 10,000), trim search,
  and parameterize every query.
- Build related-article results from shared canonical public themes, excluding
  the current article, ordered by number of shared themes then public update
  time, and capped at three.
- Render all variable shell content with escaping. Insert article HTML only
  after a defense-in-depth `sanitize_html` pass; never concatenate structured
  content, database errors, or query parameters into markup.
- Make public nginx explicitly rewrite and proxy only the declared routes to
  their `/_site` counterparts. Unknown paths are the public 404 page, while
  requests for internal `/_site/*` and admin API paths remain `404` at the
  public edge.
- Give every page a document title, meta description, canonical URL, skip
  link, `header`/`main`/`footer` landmarks, and a meaningful no-publications
  empty state. The first empty launch must look intentional rather than broken.

### Automated acceptance criteria

- Route tests cover every declared public route, pagination boundaries, search
  escaping, stale theme slug redirects, merged/unknown theme `404`s, and an
  empty library.
- A full Compose test creates articles in each lifecycle state and proves only
  the approved article appears on `/`, `/insights`, its canonical detail URL,
  the applicable theme page, and `sitemap.xml`.
- HTML assertions verify one `h1`, a skip link, navigation landmarks, escaped
  search text, canonical metadata, and no JavaScript requirement for a page
  to contain its article body.
- A public-edge test proves direct `/api`, `/articles`, `/inputs`,
  `/operations`, and `/_site` requests remain unavailable even when matching
  data exists internally.

## PW-WP4 — Public interface and responsive design system

### Objective

Implement the editorial-library experience described above without coupling it
to admin CSS, dashboard navigation, or a client-side framework.

### Work

- Create public-only CSS tokens and components in `frontend/public/assets`:
  typography, colour, spacing, focus, header, footer, hero, cards, article
  prose, theme pills, form controls, pagination, notice, and empty-state
  styles. Keep the related colour values intentionally aligned with, but not
  imported from, admin styles so either application can evolve safely.
- Implement the home hierarchy: hero, featured insight, recent insight cards,
  theme links, explanatory workflow, and transparency link. Hide a section
  cleanly when its query has no content.
- Implement the insight index search/filter form and URL-preserving
  pagination. Do not use asynchronous search, analytics, cookies, third-party
  embeds, or a feedback submission control.
- Implement long-form article typography, date/read-time metadata, theme
  navigation, related cards, and the publication disclosure. Preserve the
  article renderer's semantic HTML; do not reformat it into unsafe DOM
  fragments.
- Implement high-contrast responsive styles at 320px, 768px, and 1280px.
  Respect `prefers-reduced-motion`; there should be no motion that conveys
  essential meaning.

### Automated acceptance criteria

- CSS/unit contract tests verify every template class has a public stylesheet
  rule, focus styles are present, and no public asset imports a remote URL or
  the admin stylesheet.
- HTML snapshot tests cover populated and empty home/library/theme/article
  pages at all three content-density fixtures (short, typical, long title and
  excerpt).
- An automated accessibility checker in the test container reports no serious
  landmark, heading-order, form-label, link-name, duplicate-ID, or colour
  contrast violations for each route. The checker and fixtures run locally and
  in CI; no manual visual-review step is required.
- Public asset output contains no application JSON, raw evidence fixture text,
  API client code, or external network dependency.

## PW-WP5 — Discovery, caching, and public security policy

### Objective

Make public pages safe to share and index while keeping the public delivery
surface minimal and predictable.

### Work

- Add a validated `PUBLIC_SITE_ORIGIN` setting (localhost is allowed for
  development), `PUBLIC_SITE_NAME`, and an optional `PUBLIC_SITE_DESCRIPTION`.
  Use configured origin rather than request headers to construct canonical,
  sitemap, Open Graph, and JSON-LD URLs.
- Render Article JSON-LD only on public article pages, from the constrained
  public model. Add Open Graph/Twitter title, description, URL, and date tags;
  do not declare an author, image, rating, or claim not stored by the system.
- Produce a complete sitemap of home, library, about, public theme pages, and
  active public articles. `robots.txt` permits the public pages and disallows
  `/_site/`, `/api/`, and admin-looking paths.
- Set short shared-cache headers for HTML (for example, `max-age=60` with a
  bounded stale window); use immutable caching only for content-hashed public
  assets. Invalidate safely through the short HTML TTL, never by exposing a
  mutation endpoint.
- Use a public-specific CSP: no scripts, no third-party connections, no
  frames, only self-hosted styles/assets and `data:` images where required.
  Retain `nosniff`, restrictive referrer policy, permissions policy, and
  `frame-ancestors 'none'`. Return generic errors rather than upstream detail.

### Automated acceptance criteria

- Settings tests reject malformed origins and tests confirm canonical URLs do
  not reflect an attacker-supplied `Host` header.
- Sitemap and robots tests prove inactive articles and internal routes are
  absent; every sitemap URL resolves through the public edge.
- Header tests assert the public CSP, cache policy, `nosniff`, referrer policy,
  and no stack trace/error detail for 404/500 fixtures.
- Security regression tests submit script-like titles, search strings, and
  stored HTML attempts and confirm neither executable markup nor unsafe URLs
  appear in public responses.

## PW-WP6 — End-to-end verification and operational documentation

### Objective

Make the website maintainable and release-ready using repeatable checks rather
than review checklists.

### Work

- Extend `compose.test.yaml` with the public edge and a disposable PostgreSQL
  fixture. Test migration, approval, publication projection, public HTTP
  rendering, archive/return-to-draft withdrawal, reapproval, theme merge, and
  admin isolation in one lifecycle suite.
- Add public-route API/render tests to the backend test selection and public
  asset/accessibility tests to the frontend selection. Keep model calls fully
  faked; the suite must not download models or call external services.
- Update root README, `docs/architecture.md`, `docs/api.md`,
  `docs/operations.md`, and frontend READMEs to distinguish public delivery
  from the admin dashboard. Document ports, Compose profiles, public route
  allow-list, configuration, cache behaviour, backups, and rollback behaviour
  (return an approved article to draft or archive it to withdraw it).
- Add a CI job or existing CI target that runs backend unit tests, PostgreSQL
  integration tests, both frontend builds/tests, public-edge smoke tests, and
  `nginx -t` for both web images whenever public-site, article lifecycle,
  migration, Compose, or nginx files change.

### Automated acceptance criteria

- A clean clone can run the documented build/test commands and start a public
  empty state with `docker compose up --build`, with no interactive step.
- The lifecycle suite proves public content changes only when an article's
  existing lifecycle changes, never when evidence, form-source, taxonomy-run,
  operation, or generation-job records change independently.
- CI fails on a public-route data leak, inaccessible sitemap URL, failed
  migration/backfill, public nginx catch-all proxy, accessibility violation,
  or regression in the existing admin frontend tests.
- Documentation contains no manual acceptance checklist or mandatory human
  review/sign-off requirement for these packages.

## Explicit non-goals

- A public feedback form, visitor accounts, comments, newsletter integration,
  analytics, payments, external CMS, and social-media embeds.
- Publishing raw input, evidence excerpts, source names, question text,
  citation IDs, model output, model names, generation prompts, operations, or
  taxonomy-run review data.
- Replacing the internal dashboard, changing the article approval lifecycle,
  or completing the candidate batch-taxonomy reliability programme.
- A new brand identity, custom photography, or claims about a specific
  organisation not represented in repository configuration.

## Completion definition

The implementation is complete when the six packages pass their automated
criteria, a normal Compose startup serves only the public website on the host,
the admin dashboard remains available only via its explicit private profile,
and every public page is backed exclusively by an approved article publication
projection. Presentation and content wording can then be changed in later
work without widening the public data boundary.
