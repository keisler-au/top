import argparse
import asyncio
import hashlib
import json
import logging
import math
import os
from dataclasses import dataclass
from typing import Annotated, Literal, Protocol

import asyncpg
from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.config import DATABASE_URL
from app.llm import StructuredChatClient

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
Identify a recurring theme represented by the supplied group of evidence.

Topics describe what individual inputs are about. Themes describe recurring
messages across multiple inputs. Prefer reusing an existing theme when it fits.
Otherwise propose a new theme, an update to one theme, or a merge of themes.
Only link topic tags supplied with the evidence.

Return JSON with exactly this shape:
{
  "action": "reuse|new|merge|update",
  "existing_theme_ids": [1],
  "proposed_name": "Concise theme name",
  "proposed_description": "The recurring message represented by this theme",
  "rationale": "Why the evidence supports this suggestion",
  "topics": ["Relevant topic"]
}

Rules:
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
    embedding_model: str
    embedding: tuple[float, ...]


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
            timeout=timeout_seconds,
        )

    async def suggest(self, context: dict[str, object]) -> ThemeDecision:
        result = await self._client.complete(
            system_prompt=SYSTEM_PROMPT,
            user_content=json.dumps(context, ensure_ascii=False),
        )
        return ThemeDecision.model_validate(result)

    async def close(self) -> None:
        await self._client.aclose()
def _parse_vector(value: str) -> tuple[float, ...]:
    parsed = json.loads(value)
    if not isinstance(parsed, list) or not parsed:
        raise ValueError("invalid empty embedding")
    vector = tuple(float(component) for component in parsed)
    if not all(math.isfinite(component) for component in vector):
        raise ValueError("embedding components must be finite")
    return vector


def _cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding dimensions must be consistent")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        raise ValueError("embedding vectors cannot have zero magnitude")
    return sum(a * b for a, b in zip(left, right, strict=True)) / (
        left_norm * right_norm
    )


def group_related_units(
    units: list[AnalysisUnit],
    *,
    similarity_threshold: float,
    topic_similarity_threshold: float,
    min_group_size: int,
) -> list[list[AnalysisUnit]]:
    if min_group_size < 2:
        raise ValueError("min_group_size must be at least 2")
    if not -1 <= topic_similarity_threshold <= similarity_threshold <= 1:
        raise ValueError("similarity thresholds are invalid")

    adjacency = [set() for _ in units]
    for left_index, left in enumerate(units):
        for right_index in range(left_index + 1, len(units)):
            right = units[right_index]
            similarity = _cosine_similarity(left.embedding, right.embedding)
            same_topic = left.topic.casefold() == right.topic.casefold()
            if similarity >= similarity_threshold or (
                same_topic and similarity >= topic_similarity_threshold
            ):
                adjacency[left_index].add(right_index)
                adjacency[right_index].add(left_index)

    groups: list[list[AnalysisUnit]] = []
    visited: set[int] = set()
    for start in range(len(units)):
        if start in visited:
            continue
        stack = [start]
        component: list[AnalysisUnit] = []
        while stack:
            index = stack.pop()
            if index in visited:
                continue
            visited.add(index)
            component.append(units[index])
            stack.extend(adjacency[index] - visited)

        distinct_inputs = {unit.original_input_id for unit in component}
        if (
            len(component) >= min_group_size
            and len(distinct_inputs) >= min_group_size
        ):
            groups.append(
                sorted(
                    component,
                    key=lambda unit: (unit.original_input_id, unit.entity_id),
                )
            )
    return groups


def _group_fingerprint(group: list[AnalysisUnit]) -> str:
    keys = sorted(
        (
            f"{unit.entity_type}:{unit.entity_id}:"
            f"{unit.topic.casefold()}:{unit.embedding_model}"
        )
        for unit in group
    )
    return hashlib.sha256("|".join(keys).encode()).hexdigest()


async def _load_candidates(
    connection: asyncpg.Connection,
    limit: int,
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
                embeddings.embedding_model,
                embeddings.embedding::text AS embedding
            FROM original_inputs AS inputs
            JOIN segment_inputs AS segments
                ON segments.original_input_id = inputs.id
            JOIN input_embeddings AS embeddings
                ON embeddings.segment_input_id = segments.id
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
                embeddings.embedding_model,
                embeddings.embedding::text AS embedding
            FROM original_inputs AS inputs
            JOIN input_embeddings AS embeddings
                ON embeddings.original_input_id = inputs.id
            WHERE
                inputs.status = 'completed'
                AND inputs.topic IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM segment_inputs AS segments
                    WHERE segments.original_input_id = inputs.id
                )
        )
        SELECT *
        FROM analysis_units
        ORDER BY original_input_id DESC, entity_type, entity_id
        LIMIT $1
        """,
        limit,
    )
    return [
        AnalysisUnit(
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            original_input_id=row["original_input_id"],
            text=row["text"],
            topic=row["topic"],
            embedding_model=row["embedding_model"],
            embedding=_parse_vector(row["embedding"]),
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
    group: list[AnalysisUnit],
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

    group_topics = {unit.topic.casefold(): unit.topic for unit in group}
    unknown_topics = {
        topic for topic in decision.topics if topic.casefold() not in group_topics
    }
    if unknown_topics:
        raise ValueError(
            f"LLM linked topics outside the evidence group: {sorted(unknown_topics)}"
        )
    canonical_topics = [group_topics[topic.casefold()] for topic in decision.topics]

    proposed_name = decision.proposed_name
    if decision.action == "reuse":
        proposed_name = themes_by_id[decision.existing_theme_ids[0]]["name"]
    return proposed_name, canonical_topics


async def _save_suggestion(
    connection: asyncpg.Connection,
    *,
    group: list[AnalysisUnit],
    decision: ThemeDecision,
    proposed_name: str,
    topics: list[str],
) -> bool:
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
        _group_fingerprint(group),
    )
    if suggestion is None:
        return False

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
            for unit in group
        ],
    )
    return True


async def process_cycle(
    pool: asyncpg.Pool,
    suggester: ThemeSuggester,
    *,
    candidate_limit: int,
    theme_limit: int,
    similarity_threshold: float,
    topic_similarity_threshold: float,
    min_group_size: int,
) -> int:
    async with pool.acquire() as connection:
        locked = await connection.fetchval(
            "SELECT pg_try_advisory_lock($1)",
            THEME_WORKER_LOCK_ID,
        )
        if not locked:
            return 0

        try:
            units = await _load_candidates(connection, candidate_limit)
            compatible_units: dict[tuple[str, int], list[AnalysisUnit]] = {}
            for unit in units:
                key = (unit.embedding_model, len(unit.embedding))
                compatible_units.setdefault(key, []).append(unit)

            groups = []
            for model_units in compatible_units.values():
                groups.extend(
                    group_related_units(
                        model_units,
                        similarity_threshold=similarity_threshold,
                        topic_similarity_threshold=topic_similarity_threshold,
                        min_group_size=min_group_size,
                    )
                )
            saved = 0
            for group in groups:
                fingerprint = _group_fingerprint(group)
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
                topics = list(dict.fromkeys(unit.topic for unit in group))
                existing_themes = await _load_existing_themes(
                    connection,
                    topics,
                    theme_limit,
                )
                decision = await suggester.suggest(
                    {
                        "evidence": [
                            {
                                "entity_type": unit.entity_type,
                                "entity_id": unit.entity_id,
                                "original_input_id": unit.original_input_id,
                                "text": unit.text,
                                "topic": unit.topic,
                            }
                            for unit in group
                        ],
                        "topics": topics,
                        "existing_themes": existing_themes,
                    }
                )
                proposed_name, linked_topics = _validate_decision(
                    decision,
                    group,
                    existing_themes,
                )
                async with connection.transaction():
                    saved += await _save_suggestion(
                        connection,
                        group=group,
                        decision=decision,
                        proposed_name=proposed_name,
                        topics=linked_topics,
                    )
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
    candidate_limit: int,
    theme_limit: int,
    similarity_threshold: float,
    topic_similarity_threshold: float,
    min_group_size: int,
) -> None:
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2)
    suggester = LocalThemeLLMClient(
        base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
        model=os.getenv("LLM_MODEL", "llama3.2"),
        api_key=os.getenv("LLM_API_KEY"),
        timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "120")),
    )
    try:
        while True:
            try:
                saved = await process_cycle(
                    pool,
                    suggester,
                    candidate_limit=candidate_limit,
                    theme_limit=theme_limit,
                    similarity_threshold=similarity_threshold,
                    topic_similarity_threshold=topic_similarity_threshold,
                    min_group_size=min_group_size,
                )
                LOGGER.info("Theme cycle saved %s suggestions", saved)
            except Exception:
                LOGGER.exception("Theme management cycle failed")
                if once:
                    raise
            if once:
                return
            await asyncio.sleep(interval)
    finally:
        await suggester.close()
        await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Suggest recurring themes for human review."
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--interval",
        type=float,
        default=float(os.getenv("THEME_WORKER_INTERVAL", "300")),
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=int(os.getenv("THEME_CANDIDATE_LIMIT", "500")),
    )
    parser.add_argument(
        "--theme-limit",
        type=int,
        default=int(os.getenv("THEME_EXISTING_LIMIT", "50")),
    )
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=float(os.getenv("THEME_SIMILARITY_THRESHOLD", "0.82")),
    )
    parser.add_argument(
        "--topic-similarity-threshold",
        type=float,
        default=float(os.getenv("THEME_TOPIC_SIMILARITY_THRESHOLD", "0.65")),
    )
    parser.add_argument(
        "--min-group-size",
        type=int,
        default=int(os.getenv("THEME_MIN_GROUP_SIZE", "2")),
    )
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("--interval must be positive")
    if args.candidate_limit < 1 or args.theme_limit < 1:
        parser.error("limits must be at least 1")

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(
        run_worker(
            once=args.once,
            interval=args.interval,
            candidate_limit=args.candidate_limit,
            theme_limit=args.theme_limit,
            similarity_threshold=args.similarity_threshold,
            topic_similarity_threshold=args.topic_similarity_threshold,
            min_group_size=args.min_group_size,
        )
    )


if __name__ == "__main__":
    main()
