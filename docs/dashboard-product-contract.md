# Dashboard product and data contract

Status: accepted baseline for dashboard work packages WP2, WP6, and WP7.

This document defines the product rules behind dashboard metrics and
recommendations. Backend queries and frontend labels must implement these
definitions consistently. Changing a definition requires updating this
contract, the relevant query tests, and the UI copy in the same change.

## Scope

The first dashboard release is an all-time, organization-wide view. It does
not apply a date, source, form, or question filter unless a later contract
revision explicitly introduces one.

The dashboard has two taxonomy views:

- **Topics** are fine-grained, question-aware classifications attached to a
  completed original input or segment.
- **Themes** are canonical live themes connected to topics through
  `theme_topics`.

Metrics are computed from committed PostgreSQL state. Embeddings, pending
worker jobs, theme suggestions that have not been materialized, and failed
article-generation jobs do not contribute to dashboard counts.

## Normalization and identity

### Topics

A topic's identity is its normalized database value:

```text
lower(btrim(topic))
```

Topic comparisons and grouping are case-insensitive after trimming. The API
must expose:

- `key`: the normalized value, used as the stable dashboard identifier;
- `name`: a deterministic representative spelling for display.

Until topics are normalized into their own table, the display name is the
lexicographically smallest trimmed spelling in the group, with a stable
database collation and the normalized key as the final tie-breaker. Topic
URLs must URL-encode `key`; clients must not invent slugs.

Blank and null topic values are never dashboard topics.

### Themes

A theme is visible only when it resolves to a live canonical theme whose
`merged_into_id` is null. A merged theme is an alias and must not appear as a
separate dashboard row.

All topic links attached to an alias or its canonical root contribute to the
canonical theme. The canonical theme's numeric ID is the stable API key.
Readers must deduplicate an evidence item that reaches the same canonical
theme through multiple topics or alias paths.

An invalid merge path, including a cycle or a path with no live root, must be
excluded from user-facing results and reported as an operational data error;
it must not create a duplicate or arbitrary theme.

## Canonical evidence units

The dashboard counts classified points, not database rows. A canonical
evidence unit is selected as follows:

```text
Completed input with one or more segments
    -> each segment with a non-blank topic is one evidence unit

Completed input with no segments
    -> the original input is one evidence unit when it has a non-blank topic
```

Consequences:

- A split original is never counted alongside its segments.
- An unsplit original is not lost merely because it has no segment row.
- An input whose status is not `completed` does not contribute evidence.
- A segment is eligible only when its parent input is `completed`.
- Repeated responses remain separate evidence units; they are distinct source
  observations, not duplicates.
- Multiple segments from one original may count separately when they express
  separately classified points.

Each unit has a stable compound identity:

```text
original:<original_inputs.id>
segment:<segment_inputs.id>
```

The API must return the compound identity rather than exposing an ambiguous
bare numeric evidence ID.

## Evidence attribution

### Topic evidence

An evidence unit contributes once to the normalized topic attached directly
to that unit.

### Theme evidence

An evidence unit contributes once to every canonical theme connected to its
topic. If multiple matching links resolve to the same canonical theme, it is
still counted only once for that theme.

The same evidence unit may legitimately count once for several different
themes because topic-to-theme membership is many-to-many. Theme counts are
therefore not expected to sum to the global evidence total.

### Global evidence total

The overview's evidence total is the number of distinct canonical evidence
units across all topics. It is not the sum of topic or theme row counts.

## Evidence presentation and provenance

Evidence list responses and UI cards must distinguish generated structure
from source material:

- For a segment unit, the primary excerpt is `segment_text`.
- For an original unit, the primary excerpt is `original_text`.
- Every segment unit also links to and can reveal its parent's untouched
  `original_text`.
- Available source, form, question, submission, and creation context travels
  with the evidence item.
- The UI labels segment text as a system-created segment and original text as
  the source response.

The dashboard may truncate text visually, but the API must return the complete
stored text and the UI must provide a deliberate way to reveal it. Truncation
must not alter stored evidence.

Default evidence order is newest parent input first, followed by segment order
ascending, evidence kind, and evidence numeric ID. This provides deterministic
pagination while keeping segments from one response together.

## Article lifecycle assumed by dashboard metrics

The article persistence work package must provide these user-facing lifecycle
states:

- `draft`: editable and not yet submitted for approval;
- `ready_for_review`: generated or edited and awaiting an approval decision;
- `approved`: explicitly approved for use;
- `archived`: retained for history but removed from active coverage.

Generation-job states are separate from article lifecycle. A queued,
processing, or failed generation job is not an article and never contributes
to article coverage.

Approval is an explicit backend transition; generation never approves an
article. Approved content must not be silently overwritten. Editing approved
content must create a new revision or return a copy to a non-approved state,
as defined by the article persistence work package.

The initial deployment is treated as a trusted single-operator environment.
Any caller that can access the future approval endpoint is therefore treated
as authorized. This is a deployment assumption, not an authorization system;
when authentication is introduced, the backend must enforce an approver role
without changing the metric definitions below.

## Article tagging and counts

Every active article must have at least one theme or topic tag. An article can
have several tags and contributes independently to every tagged taxonomy item.
Within one taxonomy item it is counted once, regardless of duplicate joins.

For each theme or topic, expose:

- `article_count`: distinct tagged articles in `draft`, `ready_for_review`, or
  `approved` state;
- `approved_article_count`: distinct tagged articles in `approved` state.

Archived articles and generation jobs are excluded from both counts.

The overview's article total is a distinct global count of non-archived
articles. It must not be calculated by summing taxonomy article counts. The
overview's awaiting-approval total counts distinct `ready_for_review`
articles.

Approved article count is the measure of actual coverage. Drafts are visible
as work in progress but do not make a theme or topic covered.

## Coverage state

Coverage uses deliberately simple, explainable states:

| State | Rule | Meaning |
| --- | --- | --- |
| `no_evidence` | `evidence_count = 0` | Not eligible for generation |
| `uncovered` | `evidence_count > 0` and `approved_article_count = 0` | Evidence exists but no approved article covers it |
| `covered` | `evidence_count > 0` and `approved_article_count > 0` | At least one approved article covers it |

The initial release does not invent a ratio-based "low coverage" threshold.
If editorial policy later defines how many evidence items one article can
adequately cover, a new version of this contract may add such a state.

The API returns both the raw counts and `coverage_state`. The UI must display
the state with text or an icon in addition to color.

## Generation eligibility

A taxonomy item is eligible as an article-generation target only when:

- it is a visible topic or canonical live theme;
- `evidence_count > 0`;
- at least one attributable evidence unit still exists when generation starts.

Existing article coverage does not make an item ineligible. An editor may
generate another article for a covered item intentionally.

The backend must revalidate eligibility and evidence in the generation
transaction. A stale browser recommendation is not sufficient authority to
generate from missing or newly invalid evidence.

## Recommendation strategies

Recommendations are ranked within a requested taxonomy type. Themes and
topics are not mixed into one ranking because their scopes are different.

Only generation-eligible items participate.

### Most evidence

Sort by:

1. `evidence_count` descending;
2. `approved_article_count` ascending;
3. `article_count` ascending;
4. normalized display name ascending;
5. stable taxonomy key ascending.

Explanation template:

```text
Recommended because it has {evidence_count} evidence items and
{approved_article_count} approved articles.
```

### Least covered

Sort by:

1. `approved_article_count` ascending;
2. `article_count` ascending;
3. `evidence_count` descending;
4. normalized display name ascending;
5. stable taxonomy key ascending.

This deliberately prioritizes zero approved coverage. Among equally covered
items it favors fewer works in progress, then the item with more evidence.

Explanation template:

```text
Recommended because it has {approved_article_count} approved articles for
{evidence_count} evidence items.
```

### Specific target

An editor may select any generation-eligible item regardless of its rank. The
detail response must expose the same counts and evidence used by the
recommendation views.

## Dashboard summary metrics

The overview exposes these all-time metrics:

- `evidence_count`: distinct canonical evidence units;
- `theme_count`: visible canonical live themes, including themes with zero
  current evidence;
- `topic_count`: distinct normalized topics represented by canonical evidence;
- `article_count`: distinct non-archived articles;
- `awaiting_approval_count`: distinct `ready_for_review` articles;
- `failed_generation_count`: currently failed generation jobs that have not
  been successfully retried or dismissed.

Theme count includes empty live themes so administrators can see that the
taxonomy exists. Topic count does not include historical topic strings with
no canonical evidence because there is no independent topic registry today.

## Search, sorting, and pagination

- Search is case-insensitive and matches taxonomy name and description where
  a description exists.
- Leading and trailing search whitespace is ignored.
- An empty search behaves as no search.
- Default taxonomy order is evidence count descending, then normalized name
  and stable key ascending.
- Supported explicit sorts are `name`, `evidence`, `articles`, and
  `approved_articles`, each with ascending or descending direction.
- Every sort ends with normalized name and stable key tie-breakers.
- Pagination is server-side and returns total matching rows.
- Page size defaults to 25 and is limited to 100.

Dashboard filters, taxonomy type, sort, direction, and page belong in the URL
so a view can be refreshed, bookmarked, and shared.

## Empty, partial, and changing data

- A successful query with no matching data returns empty collections and zero
  metrics, not `404`.
- Evidence and taxonomy aggregates are eventually consistent with background
  workers and reflect only committed completed inputs.
- Dashboard endpoints must never wait for pipeline workers or article
  generation to finish.
- The UI may refresh data after a successful approval or generation event, but
  it must not synthesize new counts locally.
- A deleted source row, merged theme, approval, or archival between requests
  may change totals; the next API response is authoritative.

## Accessibility and responsive presentation requirements

- The desktop taxonomy table becomes a stacked list of labelled cards on
  narrow screens; it must not require horizontal scrolling for primary data.
- Touch targets are at least 44 by 44 CSS pixels.
- Evidence, coverage, and job status are never communicated by color alone.
- Loading, empty, error, and stale-data states have visible text.
- Search, taxonomy selection, sorting, pagination, evidence inspection, and
  generation entry points are operable with a keyboard.
- The document heading hierarchy and landmark structure remain meaningful
  when dashboard cards change layout.

## Deferred decisions

The following are explicitly outside this baseline and must not be inferred
by WP2, WP6, or WP7:

- date-range, source, form, and question filtering;
- weighted evidence or confidence scores;
- evidence deduplication by semantic similarity or respondent identity;
- a numeric article-to-evidence coverage ratio;
- automatic approval;
- multi-user roles, ownership, and editorial assignment;
- publication to an external CMS.

