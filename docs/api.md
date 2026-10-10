# API reference

The FastAPI application is mounted directly in development and under `/api` in
the production frontend proxy. Pydantic schemas and route modules are the
authoritative definition of request and response shapes.

## Inputs and form sources

- `POST /inputs` creates an immutable input and requires a complete
  `question_context`. `GET /inputs` retrieves inputs by
  source/form/question/submission scope with bounded offset pagination.
  Optional filters combine with AND before pagination: `status` (new, ineligible,
  ready_for_embedding, ready_for_analysis, completed), `search` (answer or question
  text, up to 500 characters), `topic` and `theme` (published association names,
  up to 200 characters), `has_topic` (boolean), and `created_from`/`created_to`
  (inclusive UTC dates, YYYY-MM-DD). Text search is a case-insensitive literal
  substring, including percent and underscore characters. Blank text, invalid
  statuses/dates and reversed date ranges return 422. Existing identity scope
  rules remain: source and form_key must be supplied together; question_key and
  submission_key require both, and question_version requires question_key.
  `has_topic=false` includes inputs outside the published snapshot; before first
  publication all inputs have no topic. Responses remain a list, ordered by ID,
  with limit 1–100 and offset 0–100000.
- `GET|POST /form-sources`, `GET|PATCH /form-sources/{id}`, and
  `POST /form-sources/{id}/enable|disable` manage optional Google Sheets form
  sources.

Question identity is `(source, form_key, question_key, question_version)`.
Question wording is immutable; change it by incrementing the version.
Every response has a non-null `question_id` and resolved `question_context`.
Input responses expose only `topics: [{id, name}]` and
`themes: [{id, name, description}]` from the one published taxonomy run, plus
`published_taxonomy_run_id` and the retained evidence-processing `status`.
`taxonomy_state` is removed from the response and OpenAPI schema. Associations
are derived from the captured published run, combine all segments under their
original answer, remove duplicates, and sort by name then ID. Uncovered inputs
and inputs outside that run have empty lists. Before first publication, lists
are empty and the published-run ID is null. Publication writes no taxonomy
classification onto source inputs. Legacy input topic strings are not part of
this API.

A successor replaces both arrays together, including additions, removals, changed
labels and continued empty results. A ready candidate or failed publication
does not change them. Each response reads one committed publication, including
while another publisher is waiting. Explicit rollback restores both arrays from
the selected earlier run. These changes do not rewrite frozen run evidence or
approved article topic/theme displays.

## Dashboard taxonomy and recommendations

- `GET /dashboard/summary` reports `published_taxonomy_run_id`,
  `evidence_count`, `evidence_with_topic_count`, `evidence_without_topic_count`
  and `topic_coverage` (`full` or `partial`). The coverage counts add up to the
  exact published snapshot, including evidence without an accepted topic.
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
revision snapshot. Public snapshots retain their approved topic and batch-theme display values
through taxonomy rename, split, merge, retirement, publication, and rollback.

## Operations and candidate taxonomy

- Taxonomy run reads (`GET /taxonomy-runs`, `GET /taxonomy-runs/{id}`,
  and topic evidence reads) are internal admin endpoints without token checks
  or operator rate limits. The public edge denies these routes.
- All `/operations/*` routes and taxonomy run mutations require
  `Authorization: Bearer <token>`. `TAXONOMY_REVIEW_TOKEN` may read operations;
  `TAXONOMY_MUTATION_TOKEN` is required for every taxonomy mutation and may
  also read operations. Missing credentials fail closed. Protected scopes
  remain durably rate-limited per credential fingerprint.
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
- `GET /taxonomy-runs` lists the latest 50 runs as `{id, status}`, newest first.
- `GET /taxonomy-runs/{id}` reads one consistent database snapshot of a run's
  summary, coverage, gate results, up to 100 canonical topics and up to 100
  cluster outcomes. `truncated` reports omitted topics/clusters. Topics include
  `antecedent_provisional_topic_ids` and readable `antecedents`: provisional ID,
  name, description, question ID, support count, `singleton|equivalent`
  relationship and reconciliation decision ID. Historical runs may have empty
  antecedents. Cluster `reasons` contain geometry/naming failure codes, with
  support counts and optional provisional names; unresolved labels do not
  imply invalid evidence. Raw prompts, responses and decision payloads are absent.
- `GET /taxonomy-runs/{id}/topics/{revision_id}/evidence?offset=` reads only
  that canonical revision's evidence, ordered by evidence ID, in pages of 50.
  It returns `{items, offset, page_size}`; items contain evidence ID, original
  input ID, optional segment ID and text. Offset is bounded to 0–100000;
  a revision outside the run returns 404. This explicit evidence read is an internal admin route and requires no token.
- `POST /taxonomy-runs/{id}/schedule` queues an already frozen candidate run.
- `POST /taxonomy-runs/{id}/publish|reject` performs an optimistic decision.
- The scheduler's `quality` stage records the only release-gate assessment.
  It derives aggregate metrics from the frozen run, records the threshold
  version and a hash of all gate inputs, and exposes no endpoint for
  caller-supplied quality signals.
  Current source uses `taxonomy-release-gate-v3`: canonical topic evidence and
  stored consistency are required; partial coverage, rejected naming attempts
  and zero themes are valid. Internal candidate review includes
  `evidence_count`, `evidence_with_topic_count`, `evidence_without_topic_count`,
  `gate_passed`, `threshold_version` and bounded `publication_failures`.
  These aggregates contain no raw model requests, responses or evidence text.
  Existing gate-v2 rows retain their historical version and result.

Run review can inspect candidate and historical runs; ordinary taxonomy readers
continue to use only the published run. Human publication additionally
requires the default-off deployment switch and the computed release gate;
automatic publication is database-gated by its durable policy decision. See
the [work-package archive](archive/work-packages.md).

Automatic snapshot admission uses cumulative eligible canonical evidence.
New `partial-topic-policy/v1` candidates require question-answer embeddings
from one model and vector dimension and use
`partial-topic-naming/v1` prompt provenance during scheduling. The explicit manual compatibility path
continues to support the older `mixed` representation. A new ready embedding can trigger a
replacement even when its input predates the prior publication cutoff. Frozen
candidate membership and prior publications remain immutable until a passing
replacement is published. Manual snapshots retain exact representation
validation.

Partial publication uses migration 048. Manual and automatic transitions require
a passing `taxonomy-release-gate-v3` attestation with the current thresholds
and unchanged computed facts. A ready partial run can replace the publication
with zero themes. Swap, optional theme materialization, aliases and immutable
publication decision commit together. Same-run publication replay returns the
existing decision. A waiting different-candidate publication is rejected if the
current run changed; it can retry after reviewing the new publication. Explicit rollback restores a superseded publication and
records one immutable rollback decision, including for historical gate versions.

`GET /operations/summary` adds `published_taxonomy_run_id`,
`evidence_with_topic_count`, `evidence_without_topic_count`, and nullable
`topic_coverage` to `taxonomy_runs`. Coverage is null before first publication.
The existing bounded automation states distinguish a running replacement, a
quality-blocked candidate and a usable publication; partial coverage alone
does not block publication. Protected failures expose bounded codes only.

Topic-targeted generation accepts a canonical topic with evidence even when
there are no themes. Job creation reads target, evidence and published-run ID
within one PostgreSQL snapshot. Explicit evidence outside that topic returns
422. The worker validates citations against the frozen job evidence and creates
a reviewable article with topic tags from that job's run, even after replacement;
it adds no theme tags to a topic-targeted article. New article evidence rows
record the same frozen run ID as the generation job and article topic tags.
