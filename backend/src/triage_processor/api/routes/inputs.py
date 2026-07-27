import json
from typing import Any

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
    identity_parameters = (
        source,
        question_context.form_key,
        question_context.question_key,
        question_context.question_version,
    )
    row = await connection.fetchrow(
        """
        SELECT id, form_key, question_key, question_version, question_text
        FROM questions
        WHERE
            source = $1
            AND form_key = $2
            AND question_key = $3
            AND question_version = $4
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
                question_text
            )
            VALUES ($1, $2, $3, $4, $5)
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
                question_text
            """,
            *identity_parameters,
            question_context.question_text,
        )

        if row is None:
            row = await connection.fetchrow(
                """
                SELECT
                    id,
                    form_key,
                    question_key,
                    question_version,
                    question_text
                FROM questions
                WHERE
                    source = $1
                    AND form_key = $2
                    AND question_key = $3
                    AND question_version = $4
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
            resolved_question = None
            if payload.question_context is not None:
                resolved_question = await resolve_question(
                    connection,
                    source=payload.source,
                    question_context=payload.question_context,
                )

            question_id = (
                resolved_question["id"]
                if resolved_question is not None
                else None
            )
            row = await connection.fetchrow(
                """
                INSERT INTO original_inputs (
                    original_text,
                    source,
                    question_id,
                    submission_key
                )
                VALUES ($1, $2, $3, $4)
                RETURNING
                    id,
                    original_text,
                    source,
                    status,
                    topic,
                    question_id,
                    submission_key,
                    created_at
                """,
                payload.original_text,
                payload.source,
                question_id,
                payload.submission_key,
            )

    response_data = dict(row)
    response_data["question_context"] = (
        {
            key: resolved_question[key]
            for key in (
                "form_key",
                "question_key",
                "question_version",
                "question_text",
            )
        }
        if resolved_question is not None
        else None
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

    async with request.app.state.db_pool.acquire() as connection:
        rows = await connection.fetch(
            """
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
                SELECT
                    starting_id,
                    id AS canonical_id
                FROM theme_paths
                WHERE merged_into_id IS NULL
            ),
            input_topics AS (
                SELECT id AS input_id, topic
                FROM original_inputs
                WHERE topic IS NOT NULL

                UNION

                SELECT segments.original_input_id, segments.topic
                FROM segment_inputs AS segments
                WHERE segments.topic IS NOT NULL
            )
            SELECT
                inputs.id,
                inputs.original_text,
                inputs.source,
                inputs.status,
                inputs.topic,
                inputs.question_id,
                inputs.submission_key,
                inputs.created_at,
                questions.form_key,
                questions.question_key,
                questions.question_version,
                questions.question_text,
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
                            SELECT DISTINCT
                                canonical.id,
                                canonical.name,
                                canonical.description
                            FROM input_topics
                            JOIN theme_topics
                                ON lower(theme_topics.topic)
                                    = lower(input_topics.topic)
                            JOIN canonical_themes
                                ON canonical_themes.starting_id
                                    = theme_topics.theme_id
                            JOIN themes AS canonical
                                ON canonical.id
                                    = canonical_themes.canonical_id
                            WHERE input_topics.input_id = inputs.id
                        ) AS linked_themes
                    ),
                    '[]'::jsonb
                ) AS themes
            FROM original_inputs AS inputs
            LEFT JOIN questions
                ON questions.id = inputs.question_id
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
        )

    responses: list[InputResponse] = []
    for row in rows:
        response_data = dict(row)
        response_data["question_context"] = (
            {
                key: response_data[key]
                for key in (
                    "form_key",
                    "question_key",
                    "question_version",
                    "question_text",
                )
            }
            if response_data["question_id"] is not None
            else None
        )
        themes = response_data["themes"]
        if isinstance(themes, str):
            themes = json.loads(themes)
        response_data["themes"] = themes
        responses.append(InputResponse.model_validate(response_data))
    return responses
