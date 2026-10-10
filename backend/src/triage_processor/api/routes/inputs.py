import json
from datetime import date
from typing import Any, Literal

import asyncpg
from fastapi import APIRouter, HTTPException, Query, Request, status

from triage_processor.api.schemas import (
    InputCreate,
    InputResponse,
    QuestionContext,
)

router = APIRouter(prefix="/inputs", tags=["inputs"])
MAX_INPUT_LIST_LIMIT = 100
MAX_INPUT_LIST_OFFSET = 100_000


async def resolve_question(
    connection: asyncpg.Connection,
    *,
    source: str,
    question_context: QuestionContext,
) -> dict[str, Any]:
    form_source_id = None
    if question_context.form_id is not None:
        form_source = await connection.fetchrow(
            """
            SELECT id
            FROM form_sources
            WHERE source = $1 AND form_id = $2
            """,
            source,
            question_context.form_id,
        )
        if form_source is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="form_id is not registered for this source",
            )
        if question_context.form_key != question_context.form_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="form_key must match the registered form_id",
            )
        form_source_id = form_source["id"]

    identity_parameters = (
        source,
        question_context.form_key,
        question_context.question_key,
        question_context.question_version,
    )
    row = await connection.fetchrow(
        """
        SELECT
            questions.id,
            questions.form_key,
            questions.question_key,
            questions.question_version,
            questions.question_text,
            questions.form_source_id,
            form_sources.form_id
        FROM questions
        LEFT JOIN form_sources
            ON form_sources.id = questions.form_source_id
        WHERE
            questions.source = $1
            AND questions.form_key = $2
            AND questions.question_key = $3
            AND questions.question_version = $4
        """,
        *identity_parameters,
    )

    if row is None:
        row = await connection.fetchrow(
            """
            INSERT INTO questions (
                source,
                form_key,
                question_key,
                question_version,
                question_text,
                form_source_id
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (
                source,
                form_key,
                question_key,
                question_version
            ) DO NOTHING
            RETURNING
                id,
                form_key,
                question_key,
                question_version,
                question_text,
                form_source_id,
                $7::text AS form_id
            """,
            *identity_parameters,
            question_context.question_text,
            form_source_id,
            question_context.form_id,
        )

        if row is None:
            row = await connection.fetchrow(
                """
                SELECT
                    questions.id,
                    questions.form_key,
                    questions.question_key,
                    questions.question_version,
                    questions.question_text,
                    questions.form_source_id,
                    form_sources.form_id
                FROM questions
                LEFT JOIN form_sources
                    ON form_sources.id = questions.form_source_id
                WHERE
                    questions.source = $1
                    AND questions.form_key = $2
                    AND questions.question_key = $3
                    AND questions.question_version = $4
                """,
                *identity_parameters,
            )

    if row is None:
        raise RuntimeError("question disappeared during concurrent resolution")

    resolved_question = dict(row)
    if resolved_question["question_text"] != question_context.question_text:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "question_text does not match the existing question identity; "
                "increment question_version"
            ),
        )
    if (
        question_context.form_id is not None
        and resolved_question["form_source_id"] != form_source_id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="question identity belongs to a different registered form",
        )
    return resolved_question


@router.post(
    "",
    response_model=InputResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_input(
    payload: InputCreate,
    request: Request,
) -> InputResponse:
    async with request.app.state.db_pool.acquire() as connection:
        async with connection.transaction():
            resolved_question = await resolve_question(
                connection,
                source=payload.source,
                question_context=payload.question_context,
            )
            question_id = resolved_question["id"]
            row = await connection.fetchrow(
                """
                INSERT INTO original_inputs (
                    original_text,
                    source,
                    question_id,
                    submission_key,
                    source_record_key
                )
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (source, source_record_key)
                    WHERE source_record_key IS NOT NULL
                    DO NOTHING
                RETURNING
                    id,
                    original_text,
                    source,
                    status,
                    question_id,
                    submission_key,
                    source_record_key,
                    created_at
                """,
                payload.original_text,
                payload.source,
                question_id,
                payload.submission_key,
                payload.source_record_key,
            )

            if row is None:
                row = await connection.fetchrow(
                    """
                    SELECT
                        id,
                        original_text,
                        source,
                        status,
                        question_id,
                        submission_key,
                        source_record_key,
                        created_at
                    FROM original_inputs
                    WHERE source = $1 AND source_record_key = $2
                    """,
                    payload.source,
                    payload.source_record_key,
                )
                if row is None:
                    raise RuntimeError(
                        "source record disappeared during concurrent resolution"
                    )
                if (
                    row["original_text"] != payload.original_text
                    or row["question_id"] != question_id
                    or row["submission_key"] != payload.submission_key
                ):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            "source_record_key already exists with different "
                            "input data"
                        ),
                    )

    response_data = dict(row)
    response_data.setdefault("source_record_key", payload.source_record_key)
    # New evidence is deliberately outside the immutable published snapshot.
    # Never use the retired string topic as a provisional classification.
    response_data["topics"] = []
    response_data["themes"] = []
    response_data["published_taxonomy_run_id"] = None
    response_data["question_context"] = (
        {
            key: resolved_question.get(key)
            for key in (
                "form_key",
                "question_key",
                "question_version",
                "question_text",
                "form_id",
            )
        }
    )
    return InputResponse.model_validate(response_data)


def _validate_list_filters(
    *,
    source: str | None,
    form_key: str | None,
    question_key: str | None,
    question_version: int | None,
    submission_key: str | None,
) -> tuple[str | None, str | None, str | None, str | None]:
    values = {
        "source": source,
        "form_key": form_key,
        "question_key": question_key,
        "submission_key": submission_key,
    }
    normalized = {
        key: value.strip() if value is not None else None
        for key, value in values.items()
    }
    empty_names = [
        key
        for key, value in normalized.items()
        if value is not None and not value
    ]
    if empty_names:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"query parameters must be non-empty: {empty_names}",
        )

    normalized_source = normalized["source"]
    normalized_form_key = normalized["form_key"]
    if (normalized_source is None) != (normalized_form_key is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="source and form_key must be supplied together",
        )
    if (
        normalized["question_key"] is not None
        or normalized["submission_key"] is not None
    ) and (normalized_source is None or normalized_form_key is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "question_key and submission_key require source and form_key"
            ),
        )
    if question_version is not None and normalized["question_key"] is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="question_version requires question_key",
        )

    return (
        normalized_source,
        normalized_form_key,
        normalized["question_key"],
        normalized["submission_key"],
    )


@router.get(
    "",
    response_model=list[InputResponse],
    summary="List inputs using bounded offset/limit pagination",
)
async def list_inputs(
    request: Request,
    source: str | None = None,
    form_key: str | None = None,
    question_key: str | None = None,
    question_version: int | None = Query(default=None, ge=1),
    submission_key: str | None = None,
    search: str | None = Query(default=None, max_length=500),
    processing_status: Literal[
        "new", "ineligible", "ready_for_embedding", "ready_for_analysis", "completed"
    ] | None = Query(default=None, alias="status"),
    topic: str | None = Query(default=None, max_length=200),
    theme: str | None = Query(default=None, max_length=200),
    has_topic: bool | None = None,
    created_from: date | None = None,
    created_to: date | None = None,
    offset: int = Query(
        default=0,
        ge=0,
        le=MAX_INPUT_LIST_OFFSET,
        description=(
            "Number of matching rows to skip; bounded for this "
            "low-throughput API."
        ),
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=MAX_INPUT_LIST_LIMIT,
        description="Maximum number of rows to return.",
    ),
) -> list[InputResponse]:
    (
        source,
        form_key,
        question_key,
        submission_key,
    ) = _validate_list_filters(
        source=source,
        form_key=form_key,
        question_key=question_key,
        question_version=question_version,
        submission_key=submission_key,
    )

    text_filters = []
    for name, value in (("search", search), ("topic", topic), ("theme", theme)):
        normalized = value.strip() if value is not None else None
        if normalized == "":
            raise HTTPException(status_code=422, detail=f"{name} must be non-empty")
        text_filters.append(normalized)
    search, topic, theme = text_filters
    if created_from and created_to and created_from > created_to:
        raise HTTPException(status_code=422, detail="created_from must not be after created_to")

    async with request.app.state.db_pool.acquire() as connection:
        rows = await connection.fetch(
            """
            WITH published_taxonomy_run AS (
                SELECT id FROM taxonomy_runs WHERE status = 'published'
            ),
            input_topics AS (
                SELECT DISTINCT evidence.original_input_id AS input_id,
                    revisions.topic_id AS id, revisions.name
                FROM published_taxonomy_run AS published
                JOIN taxonomy_run_evidence AS evidence
                    ON evidence.taxonomy_run_id = published.id
                JOIN topic_memberships AS memberships
                    ON memberships.taxonomy_run_id = published.id
                    AND memberships.evidence_id = evidence.id
                JOIN topic_revisions AS revisions
                    ON revisions.id = memberships.topic_revision_id
                    AND revisions.taxonomy_run_id = published.id
            ),
            input_themes AS (
                SELECT DISTINCT evidence.original_input_id AS input_id,
                    themes.theme_id AS id, themes.name, themes.description
                FROM published_taxonomy_run AS published
                JOIN taxonomy_run_evidence AS evidence
                    ON evidence.taxonomy_run_id = published.id
                JOIN topic_memberships AS memberships
                    ON memberships.taxonomy_run_id = published.id
                    AND memberships.evidence_id = evidence.id
                JOIN theme_revision_topics AS links
                    ON links.taxonomy_run_id = published.id
                    AND links.topic_revision_id = memberships.topic_revision_id
                JOIN theme_revisions AS themes
                    ON themes.id = links.theme_revision_id
                    AND themes.taxonomy_run_id = published.id
            )
            SELECT
                inputs.id,
                inputs.original_text,
                inputs.source,
                inputs.status,
                inputs.question_id,
                inputs.submission_key,
                inputs.source_record_key,
                inputs.created_at,
                questions.form_source_id,
                questions.form_key,
                questions.question_key,
                questions.question_version,
                questions.question_text,
                form_sources.form_id,
                (SELECT id FROM published_taxonomy_run) AS published_taxonomy_run_id,
                COALESCE(
                    (
                        SELECT jsonb_agg(
                            jsonb_build_object('id', topics.id, 'name', topics.name)
                            ORDER BY lower(topics.name), topics.id
                        )
                        FROM input_topics AS topics
                        WHERE topics.input_id = inputs.id
                    ),
                    '[]'::jsonb
                ) AS topics,
                COALESCE(
                    (
                        SELECT jsonb_agg(
                            jsonb_build_object(
                                'id', linked_themes.id,
                                'name', linked_themes.name,
                                'description', linked_themes.description
                            )
                            ORDER BY
                                lower(linked_themes.name),
                                linked_themes.id
                        )
                        FROM (
                            SELECT id, name, description
                            FROM input_themes
                            WHERE input_themes.input_id = inputs.id
                        ) AS linked_themes
                    ),
                    '[]'::jsonb
                ) AS themes
            FROM original_inputs AS inputs
            JOIN questions
                ON questions.id = inputs.question_id
            LEFT JOIN form_sources
                ON form_sources.id = questions.form_source_id
            WHERE
                ($1::text IS NULL OR questions.source = $1)
                AND ($2::text IS NULL OR questions.form_key = $2)
                AND ($3::text IS NULL OR questions.question_key = $3)
                AND (
                    $4::integer IS NULL
                    OR questions.question_version = $4
                )
                AND (
                    $5::text IS NULL
                    OR inputs.submission_key = $5
                )
                AND ($8::text IS NULL OR inputs.status = $8)
                AND ($9::text IS NULL OR strpos(lower(inputs.original_text), lower($9)) > 0
                     OR strpos(lower(questions.question_text), lower($9)) > 0)
                AND ($10::text IS NULL OR EXISTS (
                    SELECT 1 FROM input_topics t WHERE t.input_id=inputs.id
                    AND strpos(lower(t.name), lower($10)) > 0))
                AND ($11::text IS NULL OR EXISTS (
                    SELECT 1 FROM input_themes t WHERE t.input_id=inputs.id
                    AND strpos(lower(t.name), lower($11)) > 0))
                AND ($12::boolean IS NULL OR $12 = EXISTS (
                    SELECT 1 FROM input_topics t WHERE t.input_id=inputs.id))
                AND ($13::date IS NULL OR inputs.created_at >= ($13::date::timestamp AT TIME ZONE 'UTC'))
                AND ($14::date IS NULL OR inputs.created_at < (($14::date + 1)::timestamp AT TIME ZONE 'UTC'))
            ORDER BY inputs.id
            OFFSET $6
            LIMIT $7
            """,
            source,
            form_key,
            question_key,
            question_version,
            submission_key,
            offset,
            limit,
            processing_status,
            search,
            topic,
            theme,
            has_topic,
            created_from,
            created_to,
        )

    responses: list[InputResponse] = []
    for row in rows:
        response_data = dict(row)
        response_data.setdefault("source_record_key", None)
        response_data["question_context"] = {
            key: response_data.get(key)
            for key in (
                "form_key",
                "question_key",
                "question_version",
                "question_text",
                "form_id",
            )
        }
        for association in ("topics", "themes"):
            value = response_data[association]
            response_data[association] = (
                json.loads(value) if isinstance(value, str) else value
            )
        responses.append(InputResponse.model_validate(response_data))
    return responses
