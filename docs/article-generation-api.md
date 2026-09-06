# Article and generation API

WP3 and WP4 provide the durable backend used by the article-generation and
editorial interfaces. Generated articles always start in
`ready_for_review`; approval is a separate, audited request.

## Articles

```http
GET    /articles?status=draft&theme_id=7&topic=cost%20barriers&sort=updated&direction=desc&page=1&page_size=25
POST   /articles
GET    /articles/{id}
PATCH  /articles/{id}
POST   /articles/{id}/preview
POST   /articles/{id}/submit
POST   /articles/{id}/approve
POST   /articles/{id}/return-to-draft
POST   /articles/{id}/archive
GET    /articles/{id}/evidence
GET    /articles/{id}/history
```

Only drafts can be edited. Each content edit creates an immutable revision;
approved content is therefore never overwritten. Submission and approval
require rendered content, at least one taxonomy tag, and canonical evidence.
Transitions accept an optional `actor` and review `note` and append an audit
event in the same transaction.

Editor preview and patch requests may include `expected_revision_id`. A stale
revision returns `409` rather than overwriting newer work. Preview renders
structured content through the revision's frozen template and returns sanitized
HTML; the dashboard displays it only in a sandboxed iframe. Article evidence
responses include segment/original type, untouched source text, topic, source,
submission, and question context for provenance display.

Evidence IDs use `original:{id}` for unsplit inputs and `segment:{id}` for
split inputs. Source rows use restrictive foreign keys so provenance cannot be
silently deleted.

## Safe, versioned templates

```http
GET    /article-templates
POST   /article-templates
GET    /article-templates/{id}
POST   /article-templates/{id}/versions
POST   /article-templates/{id}/preview
POST   /article-templates/{id}/archive
```

Templates support only `{{title}}`, `{{standfirst}}`, `{{article_body}}`, and
`{{published_at}}`. `title` and `article_body` must each occur exactly once.
Scripts, event handlers, forms, embeds, remote assets, unsafe URL schemes, and
malformed markup are rejected. Scalar content is escaped and the result is
sanitized server-side with `nh3`. Existing versions cannot be changed or
deleted; updates create a new version.

## Asynchronous generation

```http
GET  /article-generation-jobs?status=failed&page=1&page_size=25
POST /article-generation-jobs
GET  /article-generation-jobs/{id}
POST /article-generation-jobs/{id}/retry
POST /article-generation-jobs/{id}/dismiss
```

Creation returns `202 Accepted` and a stable `status_url`. It validates the
theme or topic target, freezes up to 100 canonical evidence units and the
selected template version, and queues the request. A dedicated worker claims
jobs with `FOR UPDATE SKIP LOCKED`, renews its lease, retries temporary errors
with bounded exponential backoff, and marks terminal failures for dashboard
visibility.

The LLM returns strict JSON sections and citation IDs, never outer HTML. Every
citation and taxonomy tag is checked against the frozen job scope. Article,
revision, tags, evidence provenance, and job completion are committed in one
transaction.
