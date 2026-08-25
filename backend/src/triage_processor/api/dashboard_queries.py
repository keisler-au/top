"""SQL building blocks for evidence, taxonomy, and article coverage."""

CANONICAL_EVIDENCE_CTE = """
canonical_evidence AS (
    SELECT
        'segment:' || segments.id::text AS evidence_id,
        'segment'::text AS evidence_type,
        segments.id AS evidence_numeric_id,
        inputs.id AS original_input_id,
        segments.segment_order,
        segments.segment_text AS excerpt,
        inputs.original_text,
        lower(btrim(segments.topic)) AS topic_key,
        btrim(segments.topic) AS topic_name,
        inputs.source,
        inputs.submission_key,
        inputs.source_record_key,
        inputs.question_id,
        inputs.created_at
    FROM original_inputs AS inputs
    JOIN segment_inputs AS segments
        ON segments.original_input_id = inputs.id
    WHERE
        inputs.status = 'completed'
        AND segments.topic IS NOT NULL
        AND btrim(segments.topic) <> ''

    UNION ALL

    SELECT
        'original:' || inputs.id::text AS evidence_id,
        'original'::text AS evidence_type,
        inputs.id AS evidence_numeric_id,
        inputs.id AS original_input_id,
        NULL::integer AS segment_order,
        inputs.original_text AS excerpt,
        inputs.original_text,
        lower(btrim(inputs.topic)) AS topic_key,
        btrim(inputs.topic) AS topic_name,
        inputs.source,
        inputs.submission_key,
        inputs.source_record_key,
        inputs.question_id,
        inputs.created_at
    FROM original_inputs AS inputs
    WHERE
        inputs.status = 'completed'
        AND inputs.topic IS NOT NULL
        AND btrim(inputs.topic) <> ''
        AND NOT EXISTS (
            SELECT 1
            FROM segment_inputs AS segments
            WHERE segments.original_input_id = inputs.id
        )
)
"""

CANONICAL_THEME_CTES = """
theme_paths AS (
    SELECT
        themes.id AS starting_id,
        themes.id,
        themes.merged_into_id,
        ARRAY[themes.id]::bigint[] AS path
    FROM themes

    UNION ALL

    SELECT
        theme_paths.starting_id,
        parent.id,
        parent.merged_into_id,
        theme_paths.path || parent.id
    FROM theme_paths
    JOIN themes AS parent
        ON parent.id = theme_paths.merged_into_id
    WHERE NOT parent.id = ANY(theme_paths.path)
),
canonical_theme_map AS (
    SELECT DISTINCT
        starting_id AS theme_id,
        id AS canonical_theme_id
    FROM theme_paths
    WHERE merged_into_id IS NULL
),
canonical_theme_topics AS (
    SELECT DISTINCT
        theme_map.canonical_theme_id AS theme_id,
        lower(btrim(theme_topics.topic)) AS topic_key
    FROM theme_topics
    JOIN canonical_theme_map AS theme_map
        ON theme_map.theme_id = theme_topics.theme_id
    WHERE btrim(theme_topics.topic) <> ''
)
"""

TOPIC_AGGREGATES_CTE = """
topic_article_counts AS (
    SELECT
        links.topic_key,
        count(DISTINCT articles.id)::bigint AS article_count,
        count(DISTINCT articles.id) FILTER (
            WHERE articles.status = 'approved'
        )::bigint AS approved_article_count
    FROM article_topics AS links
    JOIN articles ON articles.id = links.article_id
    WHERE articles.status <> 'archived'
    GROUP BY links.topic_key
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
        ON theme_map.theme_id = links.theme_id
    JOIN articles ON articles.id = links.article_id
    WHERE articles.status <> 'archived'
    GROUP BY theme_map.canonical_theme_id
),
theme_aggregates AS (
    SELECT
        themes.id AS key,
        themes.name,
        themes.description,
        count(DISTINCT evidence.evidence_id)::bigint AS evidence_count,
        COALESCE(max(article_counts.article_count), 0)::bigint AS article_count,
        COALESCE(max(article_counts.approved_article_count), 0)::bigint
            AS approved_article_count
    FROM themes
    LEFT JOIN canonical_theme_topics AS linked_topics
        ON linked_topics.theme_id = themes.id
    LEFT JOIN canonical_evidence AS evidence
        ON evidence.topic_key = linked_topics.topic_key
    LEFT JOIN theme_article_counts AS article_counts
        ON article_counts.theme_id = themes.id
    WHERE themes.merged_into_id IS NULL
    GROUP BY themes.id, themes.name, themes.description
)
"""

DASHBOARD_SUMMARY_QUERY = f"""
-- dashboard:summary
WITH {CANONICAL_EVIDENCE_CTE}
SELECT
    (SELECT count(*) FROM canonical_evidence)::bigint AS evidence_count,
    (
        SELECT count(*)
        FROM themes
        WHERE merged_into_id IS NULL
    )::bigint AS theme_count,
    (
        SELECT count(DISTINCT topic_key)
        FROM canonical_evidence
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
        "key = $1::bigint"
        if taxonomy_type == "theme"
        else "key = lower(btrim($1::text))"
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
            "evidence.topic_key = lower(btrim($1::text))",
        )
    if taxonomy_type == "theme":
        return (
            "WITH RECURSIVE "
            f"{CANONICAL_EVIDENCE_CTE}, {CANONICAL_THEME_CTES}",
            "EXISTS ("
            "SELECT 1 FROM canonical_theme_topics AS linked_topics "
            "WHERE linked_topics.theme_id = $1::bigint "
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
