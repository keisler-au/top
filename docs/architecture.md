# Architecture

For normative implementation rules and ownership, see the
[architecture contracts](architecture-contracts.md). The
[baseline review](reviews/architecture-baseline.md) records known discrepancies
between this reference, current code and historical plans.

## Components

```text
public-web (allowlisted public HTML, discovery documents, and self-hosted assets)
admin-web (framework-free Web Components, explicit admin profile)
    -> /api proxy -> FastAPI routes
        -> PostgreSQL + pgvector
        -> Ollama chat and embedding APIs
        -> evidence-preparation workers and batch taxonomy scheduler
        -> article-generation worker
```

`backend/` is a Python `src` project. `frontend/admin/` is a framework-free
TypeScript/Web Components administrative application; `frontend/public/` is a
dependency-free static public edge. `infrastructure/postgres/` contains the
fresh-install schema and ordered migrations; `compose.yaml` connects runtime
services. The API owns HTTP validation, `clients/` owns model communication,
and workers own background processing.

`article_publications` is the minimal public-projection boundary. It records an
article's approved immutable revision, permanent slug, and publication times;
`article_publication_themes` preserves the stable batch-theme display snapshot
for that revision. Neither relation contains evidence, source inputs,
generation metadata, editorial audit data, prompts, or taxonomy descriptions.
The projection is populated by its transactional migration backfill and by the
same transaction that approves an article. Reapproval advances the projection
to the new immutable revision while preserving the original slug and
first-publication time; prior revision-scoped theme snapshots remain immutable.
Public read routes are served by this projection-only renderer and public edge.
Taxonomy lineage can change as runs are published or rolled back, but it never
mutates an approved article's revision-scoped public theme display snapshot.

The internal `/_site` renderer is server-rendered HTML only. It queries only
the active approved projection and its revision-scoped batch-theme snapshots;
it neither invokes nor mirrors administrative JSON APIs. The public nginx edge
does not route to it until the separately verified rewrite package.

`public-web` rewrites only `/`, `/insights`, `/insights/{slug}`, `/themes`,
`/themes/{id}-{slug}`, `/about`, `robots.txt`, and `sitemap.xml` to that
internal renderer. Its named internal 404 handler returns the renderer's
generic public 404 for all other paths; direct `/_site`, API, and dashboard
paths remain unavailable at the edge.

`PUBLIC_SITE_ORIGIN` is a validated absolute HTTP(S) origin with no path,
query, fragment, or credentials. Along with `PUBLIC_SITE_NAME` and optional
`PUBLIC_SITE_DESCRIPTION`, it is the sole source for canonical, Open Graph,
JSON-LD, and sitemap URLs; request Host is never consulted. Public discovery
includes only allowlisted pages, active projection articles, and active public
themes. The nginx edge applies a scriptless, self-host-only CSP, denies frames
and browser capabilities, uses short shared caching for HTML/discovery and
unhashed assets, and reserves immutable caching for content-hashed assets.

## Backend responsibilities

- `api` owns FastAPI application startup, HTTP schemas, and routes.
- `clients` owns communication with Ollama's chat and embedding APIs.
- `workers` owns eligibility/segmentation, embeddings, and article generation.
- `job_queue.py` owns durable job claiming, leases, retries, and completion.
- `config.py` owns shared environment-derived configuration.

## Evidence preparation and batch taxonomy

```text
HTTP input
→ eligibility and segmentation
→ embeddings
→ immutable batch snapshot
→ leased clustering, topic naming, theme inference, reconciliation, and quality
→ quality-gated automatic publication of one taxonomy run
```

The original input remains the source of truth. PostgreSQL stores pipeline
state and generated classifications. Ollama has no direct database access.
The evidence queue has exactly two executable types: `eligibility_segmentation`
and `embeddings`. The batch scheduler owns all taxonomy stages in its separate
run-stage lease model.

## Question context

Question identity is normalized in `questions` as:

```text
(source, form_key, question_key, question_version)
```

Each row stores an immutable `question_text` snapshot. A new wording requires a
new positive `question_version`; neither an existing question nor an answer's
`question_id` can be mutated. `original_inputs.submission_key` groups the
answers from one submission, but is only meaningful together with the
question's source and form. Inputs without question context remain valid,
fully generic inputs.

Eligibility and topic assignment can use question text to interpret terse
answers such as “Price” or “No”. Segments still contain answer content only.
Embeddings contain `Question: …` and `Answer: …` for contextual inputs, while
generic inputs retain answer-only embeddings.

## Published taxonomy and legacy archive

```text
frozen canonical evidence -> embeddings -> clustering -> literal topics
    -> reconciled themes -> reviewed candidate run -> one published run
```

Every production reader resolves the one published run; article associations
retain stable taxonomy snapshots. The retired incremental topic/theme workers,
queue types, and reader fallbacks have no runtime path. Its historical
classifications, themes, suggestions, and assignment metadata are retained
only in the immutable `taxonomy_legacy_archive` audit schema. The mutable
legacy source tables and topic columns were destructively removed by migration
`037_drop_legacy_taxonomy_schema.sql`; the archive is their only retained
taxonomy history. See the [work-package archive](archive/work-packages.md).
