# Database inspection queries

These queries expose the normalized question context and live theme state.
Replace the example filter values as needed.

## Answers by question

Omit the version predicate to inspect every immutable version of a question.

```sql
SELECT
    questions.source,
    questions.form_key,
    questions.question_key,
    questions.question_version,
    questions.question_text,
    inputs.id AS answer_id,
    inputs.submission_key,
    inputs.original_text,
    inputs.topic,
    inputs.status
FROM questions
JOIN original_inputs AS inputs
    ON inputs.question_id = questions.id
WHERE
    questions.source = 'customer-survey'
    AND questions.form_key = 'quarterly-survey'
    AND questions.question_key = 'purchase-barrier'
    AND questions.question_version = 1
ORDER BY inputs.id;
```

## Answers by submission

Submission keys are scoped by source and form rather than globally unique.

```sql
SELECT
    questions.source,
    questions.form_key,
    inputs.submission_key,
    questions.question_key,
    questions.question_version,
    questions.question_text,
    inputs.id AS answer_id,
    inputs.original_text,
    inputs.topic,
    inputs.status
FROM questions
JOIN original_inputs AS inputs
    ON inputs.question_id = questions.id
WHERE
    questions.source = 'customer-survey'
    AND questions.form_key = 'quarterly-survey'
    AND inputs.submission_key = 'response-4832'
ORDER BY inputs.id;
```

## Pending and materialized theme suggestions

Suggestion rows are the audit trail. `theme_topics` and `themes` hold the
current live state.

```sql
SELECT
    suggestions.id,
    suggestions.action,
    suggestions.proposed_name,
    suggestions.materialized_theme_id,
    suggestions.materialized_at,
    CASE
        WHEN suggestions.materialized_at IS NULL THEN 'pending'
        ELSE 'materialized'
    END AS materialization_status
FROM theme_suggestions AS suggestions
ORDER BY
    suggestions.materialized_at NULLS FIRST,
    suggestions.id;
```

## Form → question → submission → answer → topic → themes

This query includes topics assigned to an original answer or any of its
segments. It follows `merged_into_id` to each live theme root and deduplicates
canonical themes when both a live row and a merged alias are linked.

```sql
WITH RECURSIVE theme_paths AS (
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
canonical_themes AS (
    SELECT starting_id, id AS canonical_id
    FROM theme_paths
    WHERE merged_into_id IS NULL
),
answer_topics AS (
    SELECT id AS answer_id, topic
    FROM original_inputs
    WHERE topic IS NOT NULL

    UNION

    SELECT original_input_id, topic
    FROM segment_inputs
    WHERE topic IS NOT NULL
)
SELECT DISTINCT
    questions.source,
    questions.form_key,
    questions.question_key,
    questions.question_version,
    inputs.submission_key,
    inputs.id AS answer_id,
    inputs.original_text,
    answer_topics.topic,
    canonical.id AS theme_id,
    canonical.name AS theme_name
FROM original_inputs AS inputs
LEFT JOIN questions
    ON questions.id = inputs.question_id
LEFT JOIN answer_topics
    ON answer_topics.answer_id = inputs.id
LEFT JOIN theme_topics
    ON lower(theme_topics.topic) = lower(answer_topics.topic)
LEFT JOIN canonical_themes
    ON canonical_themes.starting_id = theme_topics.theme_id
LEFT JOIN themes AS canonical
    ON canonical.id = canonical_themes.canonical_id
WHERE
    questions.source = 'customer-survey'
    AND questions.form_key = 'quarterly-survey'
ORDER BY inputs.id, answer_topics.topic, canonical.name;
```
