# API reference

The FastAPI application is mounted directly in development and under `/api` in
the production frontend proxy. Pydantic schemas and route modules are the
authoritative definition of request and response shapes.

## Inputs and form sources

- `POST /inputs` creates an immutable input. `GET /inputs` retrieves inputs by
  source/form/question/submission scope with bounded offset pagination.
- `GET|POST /form-sources`, `GET|PATCH /form-sources/{id}`, and
  `POST /form-sources/{id}/enable|disable` manage optional Google Sheets form
  sources.

Question identity is `(source, form_key, question_key, question_version)`.
Question wording is immutable; change it by incrementing the version.
Input responses expose only `topics: [{id, name}]` and
`themes: [{id, name, description}]` from the one published taxonomy run, plus
`taxonomy_state` and `published_taxonomy_run_id`. Inputs outside that frozen
run are `pending_classification`; before first publication they are explicitly
`taxonomy_unavailable`. Legacy input topic strings are not part of this API.

## Dashboard taxonomy and recommendations

- `GET /dashboard/summary`
- `GET /taxonomy?type=topic|theme&search=&sort=&direction=&page=&page_size=`
- `GET /taxonomy/{topic|theme}/{key}`
- `GET /taxonomy/{topic|theme}/{key}/evidence`
- `GET /recommendations/articles?type=topic|theme&strategy=most-evidence|least-covered&limit=`

Evidence identifiers are `original:{id}` or `segment:{id}`. Before a candidate
run is published, dashboard taxonomy endpoints return HTTP 503 with bounded
`taxonomy_first_run`, `taxonomy_candidate_failed`,
`taxonomy_quality_blocked`, `taxonomy_candidate_processing`,
`taxonomy_automation_blocked`, or `taxonomy_scheduler_unavailable` codes.
The latest run determines candidate status;
an older failed candidate does not mask a newer active one. A failed release
attestation reports the quality block even if its final readiness stage also
failed. After publication, the dashboard query layer
selects exactly one published run and returns topic IDs as topic keys; active
aliases resolve stable batch-taxonomy names only. Retired incremental topic and
theme rows are never consulted.

## Articles, templates, and generation

- `GET|POST /articles`, `GET|PATCH /articles/{id}`
- `POST /articles/{id}/preview|submit|approve|return-to-draft|archive`
- `GET /articles/{id}/evidence|history`
- `GET|POST /article-templates`, `GET /article-templates/{id}`
- `POST /article-templates/{id}/versions|preview|archive`
- `GET|POST /article-generation-jobs`,
  `GET /article-generation-jobs/{id}`, and `POST` retry/dismiss actions.

Articles use immutable revisions. Generated articles begin
`ready_for_review`; approval is a separate audit event. Generation freezes its
template and canonical evidence, validates returned citations/tags against that
scope, and persists provenance transactionally. Template HTML is versioned and
sanitized; only the documented placeholder set is permitted.

Approval refreshes the internal `article_publications` projection used by the
public edge. Returning an approved article to draft or archiving it withdraws
it; reapproval keeps its permanent slug while selecting a new immutable
revision snapshot. Public snapshots retain their batch-theme display values
through taxonomy rename, split, merge, retirement, publication, and rollback.

## Operations and candidate taxonomy

- All `/operations/*` and `/taxonomy-runs/*` routes require `Authorization:
  Bearer <token>`. `TAXONOMY_REVIEW_TOKEN` may read operations and candidate
  review data; `TAXONOMY_MUTATION_TOKEN` is required for every taxonomy
  mutation and may also read. Missing credentials fail closed. Protected read
  and mutation scopes are durably rate-limited per credential fingerprint.
- `GET /operations/summary` exposes bounded queue, form, generation, and
  taxonomy counters, including automation state, policy version, and bounded
  failure code. Its taxonomy state uses the latest candidate: active work takes
  precedence over an older failed gate or failed run. It never returns prompts,
  raw model responses, or evidence. Current-policy automatic decisions determine
  candidate state; unrelated manual history does not. Its bounded state also
  identifies disabled policy, failed evidence, automation errors, and an
  expired scheduler heartbeat.
- `GET /taxonomy-legacy-archive` and
  `GET /taxonomy-legacy-archive/{safe-table}?after_id=&limit=` are protected
  read-only audit exports. They require a review or mutation token, page at
  most 100 rows, expose legacy IDs/classifications and checksum metadata only,
  and never expose raw input text, prompts, model output, or runtime taxonomy
  state.
- `POST /taxonomy-runs` atomically captures canonical completed evidence and
  its matching vectors into a run-scoped snapshot. It requires a versioned
  configuration, explicit model/prompt provenance, embedding dimension, and an
  idempotency key; invalid snapshots return bounded error counts only.
- `GET /taxonomy-runs/{id}` reads a candidate-run summary and representatives.
- `POST /taxonomy-runs/{id}/schedule` queues an already frozen candidate run.
- `POST /taxonomy-runs/{id}/publish|reject` performs an optimistic decision.
- The scheduler's `quality` stage records the only release-gate assessment.
  It derives aggregate metrics from the frozen run, records the threshold
  version and a hash of all gate inputs, and exposes no endpoint for
  caller-supplied quality signals.

Candidate routes operate on candidate runs only. Human publication additionally
requires the default-off deployment switch and the computed release gate;
automatic publication is database-gated by its durable policy decision. See
the [work-package archive](archive/work-packages.md).

Automatic snapshot admission uses cumulative eligible canonical evidence.
`mixed` representation accepts answer-only and question-answer embeddings
from one model and vector dimension. A new ready embedding can trigger a
replacement even when its input predates the prior publication cutoff. Frozen
candidate membership and prior publications remain immutable until a passing
replacement is published. Manual snapshots retain exact representation
validation.
