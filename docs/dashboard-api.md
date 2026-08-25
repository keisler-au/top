# Dashboard read API

The dashboard endpoints implement the metric and ranking rules in
[`dashboard-product-contract.md`](dashboard-product-contract.md). They read
only committed, completed evidence and never wait for background workers.

## Article-count behavior

Article counters are read from the durable article and generation tables.
Archived articles are excluded from active and taxonomy counts, only approved
articles contribute to approved coverage, and unresolved failed generation
jobs contribute to `failed_generation_count`.

## Summary

```http
GET /dashboard/summary
```

Returns the global canonical evidence, live-theme, and represented-topic
counts together with the article workflow counters.

## Taxonomy list

```http
GET /taxonomy?type=theme
GET /taxonomy?type=topic&search=cost&sort=evidence&direction=desc&page=1&page_size=25
```

Query parameters:

- `type`: required; `theme` or `topic`;
- `search`: optional case-insensitive name/description search;
- `sort`: `name`, `evidence`, `articles`, or `approved_articles`;
- `direction`: `asc` or `desc`;
- `page`: one-based page number;
- `page_size`: 1 through 100, default 25.

The calculated offset is bounded at 100,000. Results contain raw counts,
coverage state, and generation eligibility.

## Taxonomy detail

```http
GET /taxonomy/theme/12
GET /taxonomy/topic/cost%20barriers
```

Theme keys are positive canonical theme IDs. Topic keys are the normalized
topic values returned by the list endpoint and must be URL-encoded.

## Taxonomy evidence

```http
GET /taxonomy/theme/12/evidence?page=1&page_size=25
GET /taxonomy/topic/cost%20barriers/evidence?page=1&page_size=25
```

Evidence responses use compound IDs such as `original:7` and `segment:19`.
For segments, both the system-created excerpt and the untouched parent
original are returned. Question and form context is included when available.

## Article recommendations

```http
GET /recommendations/articles?type=theme&strategy=most-evidence&limit=5
GET /recommendations/articles?type=topic&strategy=least-covered&limit=5
```

`limit` is between 1 and 20. Recommendations contain only taxonomy items with
canonical evidence and include a human-readable explanation generated from
the returned counts.
