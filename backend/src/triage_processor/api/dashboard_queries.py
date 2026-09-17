"""SQL building blocks for evidence, taxonomy, and article coverage."""

CANONICAL_EVIDENCE_CTE = """
published_taxonomy_run AS (
    SELECT id FROM taxonomy_runs WHERE status = 'published'
),
canonical_evidence AS (
    -- A published run is a frozen evidence snapshot.  Do not mix it with
    -- inputs that arrived after its cutoff or with legacy string assignments.
    SELECT
        CASE WHEN evidence.segment_input_id IS NULL THEN 'original:' || evidence.original_input_id::text
             ELSE 'segment:' || evidence.segment_input_id::text END AS evidence_id,
        CASE WHEN evidence.segment_input_id IS NULL THEN 'original'::text ELSE 'segment'::text END AS evidence_type,
        COALESCE(evidence.segment_input_id, evidence.original_input_id) AS evidence_numeric_id,
        evidence.original_input_id,
        segments.segment_order,
        COALESCE(segments.segment_text, inputs.original_text) AS excerpt,
        inputs.original_text,
        revisions.topic_id::text AS topic_key,
        revisions.name AS topic_name,
        inputs.source, inputs.submission_key, inputs.source_record_key,
        inputs.question_id, inputs.created_at
    FROM published_taxonomy_run published
    JOIN taxonomy_run_evidence evidence ON evidence.taxonomy_run_id = published.id
    JOIN topic_memberships memberships ON memberships.taxonomy_run_id = published.id
                                      AND memberships.evidence_id = evidence.id
    JOIN topic_revisions revisions ON revisions.id = memberships.topic_revision_id
                                  AND revisions.taxonomy_run_id = published.id
    JOIN original_inputs inputs ON inputs.id = evidence.original_input_id
    LEFT JOIN segment_inputs segments ON segments.id = evidence.segment_input_id
)
"""

CANONICAL_THEME_CTES = """
canonical_theme_map AS (
    SELECT revisions.theme_id, revisions.theme_id AS canonical_theme_id
    FROM published_taxonomy_run published
    JOIN theme_revisions revisions ON revisions.taxonomy_run_id = published.id
),
canonical_theme_topics AS (
    SELECT DISTINCT
        themes.theme_id, revisions.topic_id::text AS topic_key
    FROM published_taxonomy_run published
    JOIN theme_revisions themes ON themes.taxonomy_run_id = published.id
    JOIN theme_revision_topics links ON links.taxonomy_run_id = published.id
                                    AND links.theme_revision_id = themes.id
    JOIN topic_revisions revisions ON revisions.id = links.topic_revision_id
                                  AND revisions.taxonomy_run_id = published.id
),
canonical_themes AS (
    SELECT revisions.theme_id, revisions.name, revisions.description
    FROM published_taxonomy_run published
    JOIN theme_revisions revisions ON revisions.taxonomy_run_id = published.id
)
"""

TOPIC_AGGREGATES_CTE = """
topic_article_counts AS (
    SELECT
        links.topic_id::text AS topic_key,
        count(DISTINCT articles.id)::bigint AS article_count,
        count(DISTINCT articles.id) FILTER (
            WHERE articles.status = 'approved'
        )::bigint AS approved_article_count
    FROM article_topics AS links
    JOIN articles ON articles.id = links.article_id
    WHERE articles.status <> 'archived'
      AND links.topic_id IS NOT NULL
    GROUP BY links.topic_id::text
),
topic_aggregates AS (
    SELECT
        evidence.topic_key AS key,
        min(evidence.topic_name COLLATE "C") AS name,
        NULL::text AS description,
        count(*)::bigint AS evidence_count,
        COALESCE(max(article_counts.article_count), 0)::bigint AS article_count,
        COALESCE(max(article_counts.approved_article_count), 0)::bigint
            AS approved_article_count
    FROM canonical_evidence AS evidence
    LEFT JOIN topic_article_counts AS article_counts
        ON article_counts.topic_key = evidence.topic_key
    GROUP BY evidence.topic_key
)
"""

THEME_AGGREGATES_CTE = """
theme_article_counts AS (
    SELECT
        theme_map.canonical_theme_id AS theme_id,
        count(DISTINCT articles.id)::bigint AS article_count,
        count(DISTINCT articles.id) FILTER (
            WHERE articles.status = 'approved'
        )::bigint AS approved_article_count
    FROM article_themes AS links
    JOIN canonical_theme_map AS theme_map
        ON theme_map.theme_id = links.stable_theme_id
    JOIN articles ON articles.id = links.article_id
    WHERE articles.status <> 'archived'
    GROUP BY theme_map.canonical_theme_id
),
theme_aggregates AS (
    SELECT
        themes.theme_id AS key,
        themes.name,
        themes.description,
        count(DISTINCT evidence.evidence_id)::bigint AS evidence_count,
        COALESCE(max(article_counts.article_count), 0)::bigint AS article_count,
        COALESCE(max(article_counts.approved_article_count), 0)::bigint
            AS approved_article_count
    FROM canonical_themes AS themes
    LEFT JOIN canonical_theme_topics AS linked_topics
        ON linked_topics.theme_id = themes.theme_id
    LEFT JOIN canonical_evidence AS evidence
        ON evidence.topic_key = linked_topics.topic_key
    LEFT JOIN theme_article_counts AS article_counts
        ON article_counts.theme_id = themes.theme_id
    GROUP BY themes.theme_id, themes.name, themes.description
)
"""

DASHBOARD_SUMMARY_QUERY = f"""
-- dashboard:summary
WITH RECURSIVE {CANONICAL_EVIDENCE_CTE}, {CANONICAL_THEME_CTES}
SELECT
    (SELECT count(*) FROM canonical_evidence)::bigint AS evidence_count,
    (
        SELECT count(*) FROM canonical_themes
    )::bigint AS theme_count,
    (
        SELECT count(DISTINCT topic_key) FROM canonical_evidence
    )::bigint AS topic_count,
    (
        SELECT count(*) FROM articles WHERE status <> 'archived'
    )::bigint AS article_count,
    (
        SELECT count(*) FROM articles WHERE status = 'ready_for_review'
    )::bigint AS awaiting_approval_count,
    (
        SELECT count(*) FROM article_generation_jobs WHERE status = 'failed'
    )::bigint AS failed_generation_count
"""


def taxonomy_aggregate_ctes(taxonomy_type: str) -> tuple[str, str]:
    if taxonomy_type == "topic":
        return (
            f"WITH {CANONICAL_EVIDENCE_CTE}, {TOPIC_AGGREGATES_CTE}",
            "topic_aggregates",
        )
    if taxonomy_type == "theme":
        return (
        "WITH RECURSIVE "
            f"{CANONICAL_EVIDENCE_CTE}, {CANONICAL_THEME_CTES}, "
            f"{THEME_AGGREGATES_CTE}",
            "theme_aggregates",
        )
    raise ValueError(f"unsupported taxonomy type: {taxonomy_type}")


TAXONOMY_ORDER_BY = {
    ("name", "asc"): 'lower(name) ASC, key ASC',
    ("name", "desc"): 'lower(name) DESC, key ASC',
    ("evidence", "asc"): 'evidence_count ASC, lower(name) ASC, key ASC',
    ("evidence", "desc"): 'evidence_count DESC, lower(name) ASC, key ASC',
    ("articles", "asc"): 'article_count ASC, lower(name) ASC, key ASC',
    ("articles", "desc"): 'article_count DESC, lower(name) ASC, key ASC',
    ("approved_articles", "asc"): (
        'approved_article_count ASC, lower(name) ASC, key ASC'
    ),
    ("approved_articles", "desc"): (
        'approved_article_count DESC, lower(name) ASC, key ASC'
    ),
}


def taxonomy_count_query(taxonomy_type: str) -> str:
    ctes, aggregate = taxonomy_aggregate_ctes(taxonomy_type)
    return f"""
-- dashboard:taxonomy-count:{taxonomy_type}
{ctes}
SELECT count(*)::bigint
FROM {aggregate}
WHERE
    $1::text IS NULL
    OR name ILIKE '%' || $1 || '%'
    OR COALESCE(description, '') ILIKE '%' || $1 || '%'
"""


def taxonomy_list_query(
    taxonomy_type: str,
    *,
    sort: str,
    direction: str,
) -> str:
    ctes, aggregate = taxonomy_aggregate_ctes(taxonomy_type)
    order_by = TAXONOMY_ORDER_BY[(sort, direction)]
    return f"""
-- dashboard:taxonomy-list:{taxonomy_type}
{ctes}
SELECT
    key,
    name,
    description,
    evidence_count,
    article_count,
    approved_article_count
FROM {aggregate}
WHERE
    $1::text IS NULL
    OR name ILIKE '%' || $1 || '%'
    OR COALESCE(description, '') ILIKE '%' || $1 || '%'
ORDER BY {order_by}
OFFSET $2
LIMIT $3
"""


def taxonomy_detail_query(taxonomy_type: str) -> str:
    ctes, aggregate = taxonomy_aggregate_ctes(taxonomy_type)
    key_predicate = (
        "key = (SELECT theme_id FROM resolve_published_theme_id($1::bigint) WHERE resolution = 'resolved')"
        if taxonomy_type == "theme"
        else "(key = lower(btrim($1::text)) OR (EXISTS (SELECT 1 FROM published_taxonomy_run) AND key IN (SELECT aliases.topic_id::text FROM topic_aliases aliases WHERE aliases.retired_at IS NULL AND aliases.normalized_alias = lower(btrim($1::text)))))"
    )
    return f"""
-- dashboard:taxonomy-detail:{taxonomy_type}
{ctes}
SELECT
    key,
    name,
    description,
    evidence_count,
    article_count,
    approved_article_count
FROM {aggregate}
WHERE {key_predicate}
"""


def evidence_scope_ctes(taxonomy_type: str) -> tuple[str, str]:
    if taxonomy_type == "topic":
        return (
            f"WITH {CANONICAL_EVIDENCE_CTE}",
            "(evidence.topic_key = lower(btrim($1::text)) OR (EXISTS (SELECT 1 FROM published_taxonomy_run) AND evidence.topic_key IN (SELECT aliases.topic_id::text FROM topic_aliases aliases WHERE aliases.retired_at IS NULL AND aliases.normalized_alias = lower(btrim($1::text)))))",
        )
    if taxonomy_type == "theme":
        return (
            "WITH RECURSIVE "
            f"{CANONICAL_EVIDENCE_CTE}, {CANONICAL_THEME_CTES}",
            "EXISTS ("
            "SELECT 1 FROM canonical_theme_topics AS linked_topics "
            "WHERE linked_topics.theme_id = (SELECT theme_id FROM resolve_published_theme_id($1::bigint) WHERE resolution = 'resolved') "
            "AND linked_topics.topic_key = evidence.topic_key"
            ")",
        )
    raise ValueError(f"unsupported taxonomy type: {taxonomy_type}")


def evidence_count_query(taxonomy_type: str) -> str:
    ctes, predicate = evidence_scope_ctes(taxonomy_type)
    return f"""
-- dashboard:evidence-count:{taxonomy_type}
{ctes}
SELECT count(*)::bigint
FROM canonical_evidence AS evidence
WHERE {predicate}
"""


def evidence_list_query(taxonomy_type: str) -> str:
    ctes, predicate = evidence_scope_ctes(taxonomy_type)
    return f"""
-- dashboard:evidence-list:{taxonomy_type}
{ctes}
SELECT
    evidence.evidence_id AS id,
    evidence.evidence_type AS type,
    evidence.excerpt,
    evidence.original_text,
    evidence.original_input_id,
    evidence.segment_order,
    evidence.topic_key,
    evidence.topic_name,
    evidence.source,
    evidence.submission_key,
    evidence.source_record_key,
    evidence.created_at,
    questions.form_key,
    questions.question_key,
    questions.question_version,
    questions.question_text,
    form_sources.form_id
FROM canonical_evidence AS evidence
LEFT JOIN questions
    ON questions.id = evidence.question_id
LEFT JOIN form_sources
    ON form_sources.id = questions.form_source_id
WHERE {predicate}
ORDER BY
    evidence.created_at DESC,
    evidence.original_input_id DESC,
    evidence.segment_order ASC NULLS FIRST,
    evidence.evidence_type,
    evidence.evidence_numeric_id
OFFSET $2
LIMIT $3
"""


RECOMMENDATION_ORDER_BY = {
    "most-evidence": (
        "evidence_count DESC, approved_article_count ASC, "
        "article_count ASC, lower(name) ASC, key ASC"
    ),
    "least-covered": (
        "approved_article_count ASC, article_count ASC, "
        "evidence_count DESC, lower(name) ASC, key ASC"
    ),
}


def recommendation_query(taxonomy_type: str, strategy: str) -> str:
    ctes, aggregate = taxonomy_aggregate_ctes(taxonomy_type)
    order_by = RECOMMENDATION_ORDER_BY[strategy]
    return f"""
-- dashboard:recommendations:{taxonomy_type}:{strategy}
{ctes}
SELECT
    key,
    name,
    description,
    evidence_count,
    article_count,
    approved_article_count
FROM {aggregate}
WHERE evidence_count > 0
ORDER BY {order_by}
LIMIT $1
"""
