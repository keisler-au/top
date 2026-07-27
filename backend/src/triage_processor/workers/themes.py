import argparse
import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass
from typing import Annotated, Literal, Protocol

import asyncpg
from pydantic import BaseModel, Field, StringConstraints, model_validator

from triage_processor.clients.llm import StructuredChatClient
from triage_processor.config import DATABASE_URL
from triage_processor.job_queue import QueueSettings, run_job_loop
from triage_processor.workers.low_information import is_low_information

LOGGER = logging.getLogger(__name__)
THEME_WORKER_LOCK_ID = 847_319_204

RequiredName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
]
RequiredText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
]

SYSTEM_PROMPT = """\
Evaluate the supplied topic for inclusion in a broader recurring theme.

You are being shown one topic, the questions that gave it context, and a sample
of its complete evidence membership. Decide whether the topic belongs to an
existing theme, warrants a new theme, should update one theme, or supports
merging existing themes. Use the topic name, questions, and sample evidence.
The proposed theme name must be concise and contain 1–3 words.

Return JSON with exactly this shape:
{
  "action": "reuse|new|merge|update",
  "existing_theme_ids": [1],
  "proposed_name": "Concise Theme",
  "proposed_description": "The recurring message represented by this theme",
  "rationale": "Why the topic supports this suggestion",
  "topics": ["Supplied Topic"]
}

Rules:
- Only link the supplied topic.
- new: existing_theme_ids must be empty.
- reuse or update: include exactly one existing theme id.
- merge: include at least two existing theme ids.
- Return JSON only, without Markdown or commentary.
"""


@dataclass(frozen=True)
class AnalysisUnit:
    entity_type: Literal["original", "segment"]
    entity_id: int
    original_input_id: int
    text: str
    topic: str
    question_id: int | None
    question_text: str | None


@dataclass(frozen=True)
class TopicCluster:
    topic_name: str
    member_units: tuple[AnalysisUnit, ...]
    distinct_question_ids: frozenset[int]
    distinct_question_texts: tuple[str, ...]
    rich_member_count: int


@dataclass(frozen=True)
class StoredThemeSuggestion:
    id: int
    action: Literal["reuse", "new", "merge", "update"]
    proposed_name: str
    proposed_description: str
    existing_theme_ids: tuple[int, ...]
    topics: tuple[str, ...]


class ThemeDecision(BaseModel):
    action: Literal["reuse", "new", "merge", "update"]
    existing_theme_ids: list[int] = Field(default_factory=list)
    proposed_name: RequiredName
    proposed_description: RequiredText
    rationale: RequiredText
    topics: list[RequiredName]

    @model_validator(mode="after")
    def validate_action(self) -> "ThemeDecision":
        ids = self.existing_theme_ids
        if len(ids) != len(set(ids)):
            raise ValueError("existing_theme_ids must be unique")
        if self.action == "new" and ids:
            raise ValueError("new themes cannot reference existing themes")
        if self.action in {"reuse", "update"} and len(ids) != 1:
            raise ValueError(f"{self.action} requires exactly one existing theme")
        if self.action == "merge" and len(ids) < 2:
            raise ValueError("merge requires at least two existing themes")
        if not self.topics or len(self.topics) != len(
            {topic.casefold() for topic in self.topics}
        ):
            raise ValueError("topics must be non-empty and unique")
        return self


class ThemeSuggester(Protocol):
    async def suggest(self, context: dict[str, object]) -> ThemeDecision: ...


class LocalThemeLLMClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_seconds: float = 120,
    ) -> None:
        self._client = StructuredChatClient(
            base_url=base_url,
            model=model,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )

    async def suggest(self, context: dict[str, object]) -> ThemeDecision:
        result = await self._client.complete(
            system_prompt=SYSTEM_PROMPT,
            user_content=json.dumps(context, ensure_ascii=False),
        )
        return ThemeDecision.model_validate(result)

    async def close(self) -> None:
        await self._client.close()


def build_topic_clusters(units: list[AnalysisUnit]) -> list[TopicCluster]:
    grouped_units: dict[str, list[AnalysisUnit]] = {}
    display_names: dict[str, str] = {}
    for unit in units:
        canonical_topic = unit.topic.casefold()
        display_names.setdefault(canonical_topic, unit.topic)
        grouped_units.setdefault(canonical_topic, []).append(unit)

    clusters: list[TopicCluster] = []
    for canonical_topic, members in grouped_units.items():
        ordered_members = tuple(
            sorted(
                members,
                key=lambda unit: (unit.entity_type, unit.entity_id),
            )
        )
        question_ids = frozenset(
            unit.question_id
            for unit in ordered_members
            if unit.question_id is not None
        )
        question_texts = tuple(
            dict.fromkeys(
                unit.question_text
                for unit in ordered_members
                if unit.question_id is not None
                and unit.question_text is not None
            )
        )
        clusters.append(
            TopicCluster(
                topic_name=display_names[canonical_topic],
                member_units=ordered_members,
                distinct_question_ids=question_ids,
                distinct_question_texts=question_texts,
                rich_member_count=sum(
                    not is_low_information(unit.text)
                    for unit in ordered_members
                ),
            )
        )
    return clusters


def is_cluster_eligible(
    cluster: TopicCluster,
    *,
    min_rich_units: int,
    min_distinct_questions_low_info: int,
) -> bool:
    if min_rich_units < 1:
        raise ValueError("min_rich_units must be at least 1")
    if min_distinct_questions_low_info < 1:
        raise ValueError(
            "min_distinct_questions_low_info must be at least 1"
        )
    if cluster.rich_member_count >= min_rich_units:
        return True
    return (
        cluster.rich_member_count == 0
        and len(cluster.distinct_question_ids)
        >= min_distinct_questions_low_info
    )


def topic_cluster_fingerprint(cluster: TopicCluster) -> str:
    digest = hashlib.sha256()
    digest.update(cluster.topic_name.casefold().encode())
    for unit in sorted(
        cluster.member_units,
        key=lambda member: (member.entity_type, member.entity_id),
    ):
        digest.update(b"|")
        digest.update(unit.entity_type.encode())
        digest.update(b":")
        digest.update(str(unit.entity_id).encode())
    return digest.hexdigest()


def sample_cluster_evidence(
    cluster: TopicCluster,
    limit: int,
) -> list[str]:
    if limit < 1:
        raise ValueError("sample evidence limit must be at least 1")

    selected: list[AnalysisUnit] = []
    selected_keys: set[tuple[str, int]] = set()
    represented_questions: set[int] = set()
    for unit in cluster.member_units:
        if unit.question_id is None or unit.question_id in represented_questions:
            continue
        selected.append(unit)
        selected_keys.add((unit.entity_type, unit.entity_id))
        represented_questions.add(unit.question_id)
        if len(selected) == limit:
            return [unit.text for unit in selected]

    for unit in cluster.member_units:
        key = (unit.entity_type, unit.entity_id)
        if key in selected_keys:
            continue
        selected.append(unit)
        if len(selected) == limit:
            break
    return [unit.text for unit in selected]


async def _load_analysis_units(
    connection: asyncpg.Connection,
) -> list[AnalysisUnit]:
    rows = await connection.fetch(
        """
        WITH analysis_units AS (
            SELECT
                'segment'::text AS entity_type,
                segments.id AS entity_id,
                inputs.id AS original_input_id,
                segments.segment_text AS text,
                segments.topic,
                inputs.question_id,
                questions.question_text
            FROM original_inputs AS inputs
            JOIN segment_inputs AS segments
                ON segments.original_input_id = inputs.id
            LEFT JOIN questions
                ON questions.id = inputs.question_id
            WHERE
                inputs.status = 'completed'
                AND segments.topic IS NOT NULL

            UNION ALL

            SELECT
                'original'::text AS entity_type,
                inputs.id AS entity_id,
                inputs.id AS original_input_id,
                inputs.original_text AS text,
                inputs.topic,
                inputs.question_id,
                questions.question_text
            FROM original_inputs AS inputs
            LEFT JOIN questions
                ON questions.id = inputs.question_id
            WHERE
                inputs.status = 'completed'
                AND inputs.topic IS NOT NULL
        )
        SELECT *
        FROM analysis_units
        ORDER BY lower(topic), entity_type, entity_id, topic
        """
    )
    return [
        AnalysisUnit(
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            original_input_id=row["original_input_id"],
            text=row["text"],
            topic=row["topic"],
            question_id=row["question_id"],
            question_text=row["question_text"],
        )
        for row in rows
    ]


async def _load_existing_themes(
    connection: asyncpg.Connection,
    topics: list[str],
    limit: int,
) -> list[dict[str, object]]:
    rows = await connection.fetch(
        """
        SELECT
            themes.id,
            themes.name,
            themes.description,
            COALESCE(
                array_agg(theme_topics.topic)
                    FILTER (WHERE theme_topics.topic IS NOT NULL),
                ARRAY[]::text[]
            ) AS topics,
            COUNT(*) FILTER (
                WHERE lower(theme_topics.topic) = ANY($1::text[])
            ) AS relevance
        FROM themes
        LEFT JOIN theme_topics ON theme_topics.theme_id = themes.id
        WHERE themes.merged_into_id IS NULL
        GROUP BY themes.id
        ORDER BY relevance DESC, themes.updated_at DESC, themes.id
        LIMIT $2
        """,
        [topic.casefold() for topic in topics],
        limit,
    )
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "topics": list(row["topics"]),
        }
        for row in rows
    ]


def _validate_decision(
    decision: ThemeDecision,
    cluster: TopicCluster,
    existing_themes: list[dict[str, object]],
) -> tuple[str, list[str]]:
    themes_by_id = {theme["id"]: theme for theme in existing_themes}
    unknown_ids = set(decision.existing_theme_ids) - set(themes_by_id)
    if unknown_ids:
        raise ValueError(f"LLM referenced unknown theme ids: {sorted(unknown_ids)}")

    themes_by_name = {
        str(theme["name"]).casefold(): theme["id"]
        for theme in existing_themes
    }
    matching_theme_id = themes_by_name.get(decision.proposed_name.casefold())
    if decision.action == "new" and matching_theme_id is not None:
        raise ValueError("LLM proposed a new theme using an existing theme name")
    if (
        decision.action in {"update", "merge"}
        and matching_theme_id is not None
        and matching_theme_id not in decision.existing_theme_ids
    ):
        raise ValueError(
            "LLM proposed a name belonging to an unrelated existing theme"
        )

    canonical_topic = cluster.topic_name
    unknown_topics = {
        topic
        for topic in decision.topics
        if topic.casefold() != canonical_topic.casefold()
    }
    if unknown_topics:
        raise ValueError(
            f"LLM linked topics outside the evidence cluster: "
            f"{sorted(unknown_topics)}"
        )

    return decision.proposed_name, [canonical_topic]


async def _save_suggestion(
    connection: asyncpg.Connection,
    *,
    cluster: TopicCluster,
    decision: ThemeDecision,
    proposed_name: str,
    topics: list[str],
) -> int | None:
    suggestion = await connection.fetchrow(
        """
        INSERT INTO theme_suggestions (
            action,
            proposed_name,
            proposed_description,
            rationale,
            group_fingerprint
        )
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (group_fingerprint) DO NOTHING
        RETURNING id
        """,
        decision.action,
        proposed_name,
        decision.proposed_description,
        decision.rationale,
        topic_cluster_fingerprint(cluster),
    )
    if suggestion is None:
        return None

    suggestion_id = suggestion["id"]
    if decision.existing_theme_ids:
        await connection.executemany(
            """
            INSERT INTO theme_suggestion_existing_themes (suggestion_id, theme_id)
            VALUES ($1, $2)
            """,
            [
                (suggestion_id, theme_id)
                for theme_id in decision.existing_theme_ids
            ],
        )
    await connection.executemany(
        """
        INSERT INTO theme_suggestion_topics (suggestion_id, topic)
        VALUES ($1, $2)
        """,
        [(suggestion_id, topic) for topic in topics],
    )
    await connection.executemany(
        """
        INSERT INTO theme_suggestion_evidence (
            suggestion_id,
            original_input_id,
            segment_input_id
        )
        VALUES ($1, $2, $3)
        """,
        [
            (
                suggestion_id,
                unit.entity_id if unit.entity_type == "original" else None,
                unit.entity_id if unit.entity_type == "segment" else None,
            )
            for unit in cluster.member_units
        ],
    )
    return suggestion_id


async def _resolve_theme_roots(
    connection: asyncpg.Connection,
    theme_ids: list[int] | tuple[int, ...],
) -> dict[int, int]:
    if not theme_ids:
        return {}

    rows = await connection.fetch(
        """
        WITH RECURSIVE theme_paths AS (
            SELECT
                themes.id AS starting_id,
                themes.id,
                themes.merged_into_id,
                ARRAY[themes.id]::bigint[] AS path
            FROM themes
            WHERE themes.id = ANY($1::bigint[])

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
        )
        SELECT starting_id, id AS root_id
        FROM theme_paths
        WHERE merged_into_id IS NULL
        """,
        list(theme_ids),
    )
    roots = {row["starting_id"]: row["root_id"] for row in rows}
    missing = set(theme_ids) - set(roots)
    if missing:
        raise ValueError(
            f"theme ids do not resolve to live themes: {sorted(missing)}"
        )
    return roots


async def _validate_live_theme_name(
    connection: asyncpg.Connection,
    *,
    proposed_name: str,
    allowed_theme_ids: set[int],
) -> None:
    conflicting_id = await connection.fetchval(
        """
        SELECT id
        FROM themes
        WHERE
            lower(name) = lower($1)
            AND merged_into_id IS NULL
            AND NOT (id = ANY($2::bigint[]))
        LIMIT 1
        """,
        proposed_name,
        list(allowed_theme_ids),
    )
    if conflicting_id is not None:
        raise ValueError(
            "proposed theme name belongs to an unrelated live theme "
            f"(id {conflicting_id})"
        )


async def _link_topics(
    connection: asyncpg.Connection,
    *,
    theme_id: int,
    topics: tuple[str, ...],
) -> None:
    await connection.executemany(
        """
        INSERT INTO theme_topics (theme_id, topic)
        VALUES ($1, $2)
        ON CONFLICT DO NOTHING
        """,
        [(theme_id, topic) for topic in topics],
    )


async def _materialize_suggestion(
    connection: asyncpg.Connection,
    suggestion: StoredThemeSuggestion,
) -> int:
    roots = await _resolve_theme_roots(
        connection,
        suggestion.existing_theme_ids,
    )
    root_ids = sorted(set(roots.values()))

    if suggestion.action == "new":
        inserted = await connection.fetchrow(
            """
            INSERT INTO themes (name, description)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
            suggestion.proposed_name,
            suggestion.proposed_description,
        )
        if inserted is not None:
            canonical_theme_id = inserted["id"]
        else:
            canonical_theme_id = await connection.fetchval(
                """
                SELECT id
                FROM themes
                WHERE
                    lower(name) = lower($1)
                    AND merged_into_id IS NULL
                """,
                suggestion.proposed_name,
            )
            if canonical_theme_id is None:
                raise ValueError(
                    "proposed new theme name conflicts with a merged theme"
                )
    elif suggestion.action in {"reuse", "update"}:
        if len(root_ids) != 1:
            raise ValueError(
                f"{suggestion.action} requires one live theme"
            )
        canonical_theme_id = root_ids[0]
        if suggestion.action == "update":
            await _validate_live_theme_name(
                connection,
                proposed_name=suggestion.proposed_name,
                allowed_theme_ids={canonical_theme_id},
            )
            await connection.execute(
                """
                UPDATE themes
                SET
                    name = $2,
                    description = $3,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                """,
                canonical_theme_id,
                suggestion.proposed_name,
                suggestion.proposed_description,
            )
        else:
            await connection.execute(
                """
                UPDATE themes
                SET updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                """,
                canonical_theme_id,
            )
    elif suggestion.action == "merge":
        if not root_ids:
            raise ValueError("merge requires at least one live theme")
        canonical_theme_id = root_ids[0]
        losing_theme_ids = root_ids[1:]
        await _validate_live_theme_name(
            connection,
            proposed_name=suggestion.proposed_name,
            allowed_theme_ids=set(root_ids),
        )
        conflicting_loser_id = await connection.fetchval(
            """
            SELECT id
            FROM themes
            WHERE
                lower(name) = lower($1)
                AND id = ANY($2::bigint[])
            LIMIT 1
            """,
            suggestion.proposed_name,
            losing_theme_ids,
        )
        if conflicting_loser_id is not None:
            await connection.execute(
                """
                UPDATE themes
                SET
                    name = left(name, 80)
                        || ' [merged #'
                        || id::text
                        || ']',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                """,
                conflicting_loser_id,
            )

        for losing_theme_id in losing_theme_ids:
            await connection.execute(
                """
                INSERT INTO theme_topics (theme_id, topic)
                SELECT $1, topic
                FROM theme_topics
                WHERE theme_id = $2
                ON CONFLICT DO NOTHING
                """,
                canonical_theme_id,
                losing_theme_id,
            )
            await connection.execute(
                "DELETE FROM theme_topics WHERE theme_id = $1",
                losing_theme_id,
            )

        if losing_theme_ids:
            await connection.execute(
                """
                UPDATE themes
                SET merged_into_id = $1, updated_at = CURRENT_TIMESTAMP
                WHERE merged_into_id = ANY($2::bigint[])
                """,
                canonical_theme_id,
                losing_theme_ids,
            )
            await connection.execute(
                """
                UPDATE themes
                SET merged_into_id = $1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ANY($2::bigint[])
                """,
                canonical_theme_id,
                losing_theme_ids,
            )

        await connection.execute(
            """
            UPDATE themes
            SET
                name = $2,
                description = $3,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $1
            """,
            canonical_theme_id,
            suggestion.proposed_name,
            suggestion.proposed_description,
        )
    else:
        raise ValueError(
            f"unsupported theme action: {suggestion.action}"
        )

    await _link_topics(
        connection,
        theme_id=canonical_theme_id,
        topics=suggestion.topics,
    )
    await connection.execute(
        """
        UPDATE theme_suggestions
        SET
            materialized_theme_id = $2,
            materialized_at = CURRENT_TIMESTAMP
        WHERE id = $1 AND materialized_at IS NULL
        """,
        suggestion.id,
        canonical_theme_id,
    )
    return canonical_theme_id


async def _load_pending_suggestion(
    connection: asyncpg.Connection,
    suggestion_id: int,
) -> StoredThemeSuggestion | None:
    row = await connection.fetchrow(
        """
        SELECT
            id,
            action,
            proposed_name,
            proposed_description
        FROM theme_suggestions
        WHERE id = $1 AND materialized_at IS NULL
        FOR UPDATE
        """,
        suggestion_id,
    )
    if row is None:
        return None

    existing_theme_ids = await connection.fetch(
        """
        SELECT theme_id
        FROM theme_suggestion_existing_themes
        WHERE suggestion_id = $1
        ORDER BY theme_id
        """,
        suggestion_id,
    )
    topics = await connection.fetch(
        """
        SELECT topic
        FROM theme_suggestion_topics
        WHERE suggestion_id = $1
        ORDER BY lower(topic), topic
        """,
        suggestion_id,
    )
    return StoredThemeSuggestion(
        id=row["id"],
        action=row["action"],
        proposed_name=row["proposed_name"],
        proposed_description=row["proposed_description"],
        existing_theme_ids=tuple(
            item["theme_id"] for item in existing_theme_ids
        ),
        topics=tuple(item["topic"] for item in topics),
    )


async def materialize_pending_suggestions(
    connection: asyncpg.Connection,
) -> int:
    rows = await connection.fetch(
        """
        SELECT id
        FROM theme_suggestions
        WHERE materialized_at IS NULL
        ORDER BY id
        """
    )
    materialized = 0
    for row in rows:
        async with connection.transaction():
            suggestion = await _load_pending_suggestion(
                connection,
                row["id"],
            )
            if suggestion is None:
                continue
            await _materialize_suggestion(connection, suggestion)
            materialized += 1
    return materialized


async def process_cycle(
    pool: asyncpg.Pool,
    suggester: ThemeSuggester,
    *,
    sample_evidence_limit: int,
    theme_limit: int,
    min_rich_units: int,
    min_distinct_questions_low_info: int,
) -> int:
    if sample_evidence_limit < 1 or theme_limit < 1:
        raise ValueError("limits must be at least 1")
    if min_rich_units < 1 or min_distinct_questions_low_info < 1:
        raise ValueError("eligibility thresholds must be at least 1")

    async with pool.acquire() as connection:
        locked = await connection.fetchval(
            "SELECT pg_try_advisory_lock($1)",
            THEME_WORKER_LOCK_ID,
        )
        if not locked:
            return 0

        try:
            await materialize_pending_suggestions(connection)
            units = await _load_analysis_units(connection)
            clusters = build_topic_clusters(units)
            saved = 0
            for cluster in clusters:
                if not is_cluster_eligible(
                    cluster,
                    min_rich_units=min_rich_units,
                    min_distinct_questions_low_info=(
                        min_distinct_questions_low_info
                    ),
                ):
                    continue

                fingerprint = topic_cluster_fingerprint(cluster)
                exists = await connection.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM theme_suggestions
                        WHERE group_fingerprint = $1
                    )
                    """,
                    fingerprint,
                )
                if exists:
                    continue

                existing_themes = await _load_existing_themes(
                    connection,
                    [cluster.topic_name],
                    theme_limit,
                )
                decision = await suggester.suggest(
                    {
                        "topic": cluster.topic_name,
                        "questions": [
                            {"question_text": question_text}
                            for question_text in cluster.distinct_question_texts
                        ],
                        "sample_evidence": sample_cluster_evidence(
                            cluster,
                            sample_evidence_limit,
                        ),
                        "member_count": len(cluster.member_units),
                        "existing_themes": existing_themes,
                    }
                )
                proposed_name, linked_topics = _validate_decision(
                    decision,
                    cluster,
                    existing_themes,
                )
                async with connection.transaction():
                    suggestion_id = await _save_suggestion(
                        connection,
                        cluster=cluster,
                        decision=decision,
                        proposed_name=proposed_name,
                        topics=linked_topics,
                    )
                    if suggestion_id is not None:
                        await _materialize_suggestion(
                            connection,
                            StoredThemeSuggestion(
                                id=suggestion_id,
                                action=decision.action,
                                proposed_name=proposed_name,
                                proposed_description=(
                                    decision.proposed_description
                                ),
                                existing_theme_ids=tuple(
                                    decision.existing_theme_ids
                                ),
                                topics=tuple(linked_topics),
                            ),
                        )
                        saved += 1
            return saved
        finally:
            await connection.execute(
                "SELECT pg_advisory_unlock($1)",
                THEME_WORKER_LOCK_ID,
            )


async def run_worker(
    *,
    once: bool,
    interval: float,
    sample_evidence_limit: int,
    theme_limit: int,
    min_rich_units: int,
    min_distinct_questions_low_info: int,
) -> None:
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2)
    queue_settings = QueueSettings.from_env()
    suggester = LocalThemeLLMClient(
        base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
        model=os.getenv("LLM_MODEL", "qwen3:4b"),
        api_key=os.getenv("LLM_API_KEY"),
        timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "120")),
    )
    try:
        async with pool.acquire() as connection:
            materialized = await materialize_pending_suggestions(connection)
            LOGGER.info(
                "Theme worker materialized %s pending suggestions at startup",
                materialized,
            )

        async def handle(_input_id: int) -> None:
            saved = await process_cycle(
                pool,
                suggester,
                sample_evidence_limit=sample_evidence_limit,
                theme_limit=theme_limit,
                min_rich_units=min_rich_units,
                min_distinct_questions_low_info=(
                    min_distinct_questions_low_info
                ),
            )
            LOGGER.info("Theme cycle saved %s suggestions", saved)

        await run_job_loop(
            pool,
            job_type="themes",
            handler=handle,
            once=once,
            poll_interval=interval,
            settings=queue_settings,
        )
    finally:
        await suggester.close()
        await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Infer themes from completed topic clusters."
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--interval",
        type=float,
        default=float(os.getenv("THEME_WORKER_INTERVAL", "2")),
    )
    parser.add_argument(
        "--sample-evidence-limit",
        type=int,
        default=int(os.getenv("THEME_SAMPLE_EVIDENCE_LIMIT", "5")),
    )
    parser.add_argument(
        "--theme-limit",
        type=int,
        default=int(os.getenv("THEME_EXISTING_LIMIT", "50")),
    )
    parser.add_argument(
        "--min-rich-units",
        type=int,
        default=int(os.getenv("THEME_MIN_RICH_UNITS", "2")),
    )
    parser.add_argument(
        "--min-distinct-questions-low-info",
        type=int,
        default=int(
            os.getenv("THEME_MIN_DISTINCT_QUESTIONS_LOW_INFO", "3")
        ),
    )
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("--interval must be positive")
    if (
        args.sample_evidence_limit < 1
        or args.theme_limit < 1
        or args.min_rich_units < 1
        or args.min_distinct_questions_low_info < 1
    ):
        parser.error("limits and eligibility thresholds must be at least 1")

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(
        run_worker(
            once=args.once,
            interval=args.interval,
            sample_evidence_limit=args.sample_evidence_limit,
            theme_limit=args.theme_limit,
            min_rich_units=args.min_rich_units,
            min_distinct_questions_low_info=(
                args.min_distinct_questions_low_info
            ),
        )
    )


if __name__ == "__main__":
    main()
