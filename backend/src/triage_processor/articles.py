import json
from dataclasses import dataclass
from typing import Any, Sequence

import asyncpg


@dataclass(frozen=True)
class ResolvedEvidence:
    evidence_id: str
    original_input_id: int | None
    segment_input_id: int | None
    text: str
    topic_key: str
    topic_name: str


def normalize_topic(value: str) -> tuple[str, str]:
    # Keep this identical to the dashboard's documented lower(btrim(topic))
    # identity rule. Internal whitespace is significant until topics receive a
    # dedicated normalized table.
    name = value.strip()
    if not name or len(name) > 120:
        raise ValueError("topic names must contain between 1 and 120 characters")
    return name.casefold(), name


async def canonical_theme_ids(
    connection: asyncpg.Connection,
    theme_ids: Sequence[int],
) -> list[int]:
    unique_ids = list(dict.fromkeys(theme_ids))
    if not unique_ids:
        return []
    rows = await connection.fetch(
        """
        WITH RECURSIVE paths AS (
            SELECT id AS starting_id, id, merged_into_id, ARRAY[id]::bigint[] AS path
            FROM themes
            WHERE id = ANY($1::bigint[])

            UNION ALL

            SELECT paths.starting_id, parent.id, parent.merged_into_id,
                   paths.path || parent.id
            FROM paths
            JOIN themes AS parent ON parent.id = paths.merged_into_id
            WHERE NOT parent.id = ANY(paths.path)
        )
        SELECT starting_id, id AS canonical_id
        FROM paths
        WHERE merged_into_id IS NULL
        """,
        unique_ids,
    )
    resolved = {int(row["starting_id"]): int(row["canonical_id"]) for row in rows}
    missing = [theme_id for theme_id in unique_ids if theme_id not in resolved]
    if missing:
        raise ValueError(f"unknown or invalid theme ids: {missing}")
    return list(dict.fromkeys(resolved[theme_id] for theme_id in unique_ids))


async def resolve_evidence(
    connection: asyncpg.Connection,
    evidence_ids: Sequence[str],
) -> list[ResolvedEvidence]:
    if not evidence_ids:
        raise ValueError("at least one evidence item is required")
    if len(evidence_ids) > 100:
        raise ValueError("at most 100 evidence items may be attached")
    if len(set(evidence_ids)) != len(evidence_ids):
        raise ValueError("evidence ids must be unique")

    resolved: list[ResolvedEvidence] = []
    for evidence_id in evidence_ids:
        kind, separator, raw_id = evidence_id.partition(":")
        if separator != ":" or kind not in {"original", "segment"}:
            raise ValueError(f"invalid evidence id: {evidence_id!r}")
        try:
            numeric_id = int(raw_id)
        except ValueError as exc:
            raise ValueError(f"invalid evidence id: {evidence_id!r}") from exc
        if numeric_id < 1:
            raise ValueError(f"invalid evidence id: {evidence_id!r}")

        if kind == "segment":
            row = await connection.fetchrow(
                """
                SELECT
                    segments.original_input_id,
                    segments.id AS segment_input_id,
                    segments.segment_text AS text,
                    lower(btrim(segments.topic)) AS topic_key,
                    btrim(segments.topic) AS topic_name
                FROM segment_inputs AS segments
                JOIN original_inputs AS inputs
                    ON inputs.id = segments.original_input_id
                WHERE
                    segments.id = $1
                    AND inputs.status = 'completed'
                    AND segments.topic IS NOT NULL
                """,
                numeric_id,
            )
        else:
            row = await connection.fetchrow(
                """
                SELECT
                    inputs.id AS original_input_id,
                    NULL::bigint AS segment_input_id,
                    inputs.original_text AS text,
                    lower(btrim(inputs.topic)) AS topic_key,
                    btrim(inputs.topic) AS topic_name
                FROM original_inputs AS inputs
                WHERE
                    inputs.id = $1
                    AND inputs.status = 'completed'
                    AND inputs.topic IS NOT NULL
                    AND NOT EXISTS (
                        SELECT 1 FROM segment_inputs AS segments
                        WHERE segments.original_input_id = inputs.id
                    )
                """,
                numeric_id,
            )
        if row is None:
            raise ValueError(f"evidence does not resolve canonically: {evidence_id}")
        resolved.append(
            ResolvedEvidence(
                evidence_id=evidence_id,
                original_input_id=row["original_input_id"],
                segment_input_id=row["segment_input_id"],
                text=row["text"],
                topic_key=row["topic_key"],
                topic_name=row["topic_name"],
            )
        )
    return resolved


async def create_article_record(
    connection: asyncpg.Connection,
    *,
    title: str,
    structured_content: dict[str, Any],
    rendered_html: str | None,
    generation_metadata: dict[str, Any] | None,
    theme_ids: Sequence[int],
    topic_names: Sequence[str],
    evidence: Sequence[ResolvedEvidence],
    evidence_citations: Sequence[str | None] | None = None,
    status: str = "draft",
    template_version_id: int | None = None,
) -> tuple[int, int]:
    canonical_themes = await canonical_theme_ids(connection, theme_ids)
    normalized_topics = list(dict(normalize_topic(topic) for topic in topic_names).items())
    if not canonical_themes and not normalized_topics:
        raise ValueError("an article requires at least one theme or topic tag")
    if not evidence:
        raise ValueError("an article requires at least one evidence item")
    if status not in {"draft", "ready_for_review"}:
        raise ValueError("new articles must be draft or ready_for_review")

    article_id = await connection.fetchval(
        """
        INSERT INTO articles (title, status, generation_metadata)
        VALUES ($1, $2, $3::jsonb)
        RETURNING id
        """,
        title,
        status,
        json.dumps(generation_metadata) if generation_metadata is not None else None,
    )
    revision_id = await connection.fetchval(
        """
        INSERT INTO article_revisions (
            article_id,
            revision_number,
            title,
            structured_content,
            rendered_html,
            template_version_id
        )
        VALUES ($1, 1, $2, $3::jsonb, $4, $5)
        RETURNING id
        """,
        article_id,
        title,
        json.dumps(structured_content),
        rendered_html,
        template_version_id,
    )
    await connection.execute(
        "UPDATE articles SET current_revision_id = $2 WHERE id = $1",
        article_id,
        revision_id,
    )
    if canonical_themes:
        await connection.executemany(
            "INSERT INTO article_themes (article_id, theme_id) VALUES ($1, $2)",
            [(article_id, theme_id) for theme_id in canonical_themes],
        )
    if normalized_topics:
        await connection.executemany(
            """
            INSERT INTO article_topics (article_id, topic_key, topic_name)
            VALUES ($1, $2, $3)
            """,
            [
                (article_id, topic_key, topic_name)
                for topic_key, topic_name in normalized_topics
            ],
        )
    citations = list(evidence_citations or [None] * len(evidence))
    if len(citations) != len(evidence):
        raise ValueError("evidence citations must align with evidence")
    await connection.executemany(
        """
        INSERT INTO article_evidence (
            revision_id,
            original_input_id,
            segment_input_id,
            evidence_order,
            citation_id,
            topic_key
        )
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        [
            (
                revision_id,
                item.original_input_id,
                item.segment_input_id,
                order,
                citations[order],
                item.topic_key,
            )
            for order, item in enumerate(evidence)
        ],
    )
    await connection.execute(
        """
        INSERT INTO article_audit (article_id, revision_id, action)
        VALUES ($1, $2, 'created')
        """,
        article_id,
        revision_id,
    )
    return int(article_id), int(revision_id)
