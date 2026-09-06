import json
from typing import Any

import asyncpg
from fastapi import APIRouter, HTTPException, Query, Request, status

from triage_processor.api.dashboard_queries import (
    evidence_list_query,
    taxonomy_detail_query,
)
from triage_processor.api.generation_schemas import (
    GenerationJobCreate,
    GenerationJobListResponse,
    GenerationJobResponse,
    TemplateCreate,
    TemplatePreviewRequest,
    TemplatePreviewResponse,
    TemplateResponse,
    TemplateVersionCreate,
    TemplateVersionResponse,
)
from triage_processor.templates import render_template, validate_template_source

router = APIRouter(tags=["article-generation"])


def _template_version(row: Any) -> TemplateVersionResponse:
    return TemplateVersionResponse(
        id=row["id"],
        version=row["version"],
        html_source=row["html_source"],
        allowed_placeholders=list(row["allowed_placeholders"]),
        used_by_article_count=int(row["used_by_article_count"]),
        created_by=row["created_by"],
        created_at=row["created_at"],
    )


async def _template_response(
    connection: asyncpg.Connection,
    template_id: int,
) -> TemplateResponse | None:
    row = await connection.fetchrow(
        """
        SELECT id, name, description, status, created_at, updated_at
        FROM article_templates WHERE id = $1
        """,
        template_id,
    )
    if row is None:
        return None
    versions = await connection.fetch(
        """
        SELECT versions.id, versions.version, versions.html_source,
               versions.allowed_placeholders, versions.created_by,
               versions.created_at,
               count(DISTINCT revisions.article_id) AS used_by_article_count
        FROM article_template_versions AS versions
        LEFT JOIN article_revisions AS revisions
            ON revisions.template_version_id = versions.id
        WHERE versions.template_id = $1
        GROUP BY versions.id
        ORDER BY versions.version DESC
        """,
        template_id,
    )
    return TemplateResponse(
        **dict(row),
        versions=[_template_version(item) for item in versions],
    )


@router.get("/article-templates", response_model=list[TemplateResponse])
async def list_templates(request: Request) -> list[TemplateResponse]:
    async with request.app.state.db_pool.acquire() as connection:
        rows = await connection.fetch(
            "SELECT id FROM article_templates ORDER BY lower(name), id"
        )
        responses = []
        for row in rows:
            response = await _template_response(connection, row["id"])
            if response is not None:
                responses.append(response)
    return responses


@router.post(
    "/article-templates",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_template(payload: TemplateCreate, request: Request) -> TemplateResponse:
    try:
        placeholders = validate_template_source(payload.html_source)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    async with request.app.state.db_pool.acquire() as connection:
        async with connection.transaction():
            try:
                template_id = await connection.fetchval(
                    """
                    INSERT INTO article_templates (name, description)
                    VALUES ($1, $2) RETURNING id
                    """,
                    payload.name,
                    payload.description,
                )
            except asyncpg.UniqueViolationError as error:
                raise HTTPException(
                    status_code=409,
                    detail="a template with this name already exists",
                ) from error
            await connection.execute(
                """
                INSERT INTO article_template_versions (
                    template_id, version, html_source,
                    allowed_placeholders, created_by
                ) VALUES ($1, 1, $2, $3, $4)
                """,
                template_id,
                payload.html_source,
                placeholders,
                payload.created_by,
            )
            response = await _template_response(connection, template_id)
    if response is None:  # pragma: no cover
        raise RuntimeError("created template disappeared")
    return response


@router.get("/article-templates/{template_id}", response_model=TemplateResponse)
async def get_template(template_id: int, request: Request) -> TemplateResponse:
    async with request.app.state.db_pool.acquire() as connection:
        response = await _template_response(connection, template_id)
    if response is None:
        raise HTTPException(status_code=404, detail="template not found")
    return response


@router.post(
    "/article-templates/{template_id}/versions",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_template_version(
    template_id: int,
    payload: TemplateVersionCreate,
    request: Request,
) -> TemplateResponse:
    try:
        placeholders = validate_template_source(payload.html_source)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    async with request.app.state.db_pool.acquire() as connection:
        async with connection.transaction():
            template = await connection.fetchrow(
                "SELECT status FROM article_templates WHERE id = $1 FOR UPDATE",
                template_id,
            )
            if template is None:
                raise HTTPException(status_code=404, detail="template not found")
            if template["status"] != "active":
                raise HTTPException(status_code=409, detail="archived templates cannot be versioned")
            next_version = await connection.fetchval(
                """
                SELECT COALESCE(max(version), 0) + 1
                FROM article_template_versions WHERE template_id = $1
                """,
                template_id,
            )
            await connection.execute(
                """
                INSERT INTO article_template_versions (
                    template_id, version, html_source,
                    allowed_placeholders, created_by
                ) VALUES ($1, $2, $3, $4, $5)
                """,
                template_id,
                next_version,
                payload.html_source,
                placeholders,
                payload.created_by,
            )
            await connection.execute(
                "UPDATE article_templates SET updated_at = CURRENT_TIMESTAMP WHERE id = $1",
                template_id,
            )
            response = await _template_response(connection, template_id)
    if response is None:  # pragma: no cover
        raise RuntimeError("versioned template disappeared")
    return response


@router.post(
    "/article-templates/{template_id}/preview",
    response_model=TemplatePreviewResponse,
)
async def preview_template(
    template_id: int,
    payload: TemplatePreviewRequest,
    request: Request,
) -> TemplatePreviewResponse:
    async with request.app.state.db_pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT versions.html_source
            FROM article_template_versions AS versions
            WHERE versions.id = $1 AND versions.template_id = $2
            """,
            payload.version_id,
            template_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="template version not found")
    try:
        rendered = render_template(
            row["html_source"],
            {
                "title": payload.title,
                "standfirst": payload.standfirst,
                "sections": payload.sections,
            },
        )
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=f"invalid preview content: {error}") from error
    return TemplatePreviewResponse(rendered_html=rendered)


@router.post("/article-templates/{template_id}/archive", response_model=TemplateResponse)
async def archive_template(template_id: int, request: Request) -> TemplateResponse:
    async with request.app.state.db_pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            UPDATE article_templates
            SET status = 'archived', updated_at = CURRENT_TIMESTAMP
            WHERE id = $1 RETURNING id
            """,
            template_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="template not found")
        response = await _template_response(connection, template_id)
    if response is None:  # pragma: no cover
        raise RuntimeError("archived template disappeared")
    return response


def _job_response(row: Any) -> GenerationJobResponse:
    return GenerationJobResponse.model_validate(dict(row))


async def _load_job(connection: asyncpg.Connection, job_id: int) -> GenerationJobResponse | None:
    row = await connection.fetchrow(
        """
        SELECT id, status, strategy, taxonomy_type, taxonomy_key,
               taxonomy_name, template_version_id, editorial_guidance,
               attempts, available_at, last_error, resulting_article_id,
               status_url, created_at, updated_at
        FROM article_generation_jobs WHERE id = $1
        """,
        job_id,
    )
    return _job_response(row) if row is not None else None


@router.get("/article-generation-jobs", response_model=GenerationJobListResponse)
async def list_generation_jobs(
    request: Request,
    job_status: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> GenerationJobListResponse:
    if job_status not in {None, "pending", "processing", "completed", "failed", "dismissed"}:
        raise HTTPException(status_code=422, detail="invalid generation job status")
    offset = (page - 1) * page_size
    if offset > 100_000:
        raise HTTPException(status_code=422, detail="page offset is too large")
    predicate = "$1::text IS NULL OR status = $1"
    async with request.app.state.db_pool.acquire() as connection:
        total = await connection.fetchval(
            f"SELECT count(*) FROM article_generation_jobs WHERE {predicate}",
            job_status,
        )
        rows = await connection.fetch(
            f"""
            SELECT id, status, strategy, taxonomy_type, taxonomy_key,
                   taxonomy_name, template_version_id, editorial_guidance,
                   attempts, available_at, last_error, resulting_article_id,
                   status_url, created_at, updated_at
            FROM article_generation_jobs
            WHERE {predicate}
            ORDER BY updated_at DESC, id DESC
            OFFSET $2 LIMIT $3
            """,
            job_status,
            offset,
            page_size,
        )
    return GenerationJobListResponse(
        items=[_job_response(row) for row in rows],
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )


@router.post(
    "/article-generation-jobs",
    response_model=GenerationJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_generation_job(
    payload: GenerationJobCreate,
    request: Request,
) -> GenerationJobResponse:
    taxonomy_key: int | str
    if payload.taxonomy_type == "theme":
        try:
            taxonomy_key = int(payload.taxonomy_key)
        except ValueError as error:
            raise HTTPException(status_code=422, detail="theme key must be an integer") from error
        if taxonomy_key < 1:
            raise HTTPException(status_code=422, detail="theme key must be positive")
    else:
        taxonomy_key = payload.taxonomy_key.strip()

    async with request.app.state.db_pool.acquire() as connection:
        async with connection.transaction():
            template = await connection.fetchrow(
                """
                SELECT versions.id
                FROM article_template_versions AS versions
                JOIN article_templates AS templates ON templates.id = versions.template_id
                WHERE versions.id = $1 AND templates.status = 'active'
                """,
                payload.template_version_id,
            )
            if template is None:
                raise HTTPException(status_code=422, detail="active template version not found")
            taxonomy = await connection.fetchrow(
                taxonomy_detail_query(payload.taxonomy_type),
                taxonomy_key,
            )
            if taxonomy is None or int(taxonomy["evidence_count"]) < 1:
                raise HTTPException(status_code=422, detail="taxonomy target has no evidence")
            rows = await connection.fetch(
                evidence_list_query(payload.taxonomy_type),
                taxonomy_key,
                0,
                100,
            )
            evidence_by_id = {row["id"]: row for row in rows}
            if payload.evidence_ids is None:
                selected = list(rows)
            else:
                missing = [item for item in payload.evidence_ids if item not in evidence_by_id]
                if missing:
                    raise HTTPException(
                        status_code=422,
                        detail=f"evidence is outside the selected target: {missing}",
                    )
                selected = [evidence_by_id[item] for item in payload.evidence_ids]
            if not selected:
                raise HTTPException(status_code=422, detail="at least one evidence item is required")
            job_id = await connection.fetchval(
                """
                INSERT INTO article_generation_jobs (
                    strategy, taxonomy_type, taxonomy_key, taxonomy_name,
                    template_version_id, editorial_guidance, status_url
                ) VALUES ($1, $2, $3, $4, $5, $6, 'pending')
                RETURNING id
                """,
                payload.strategy,
                payload.taxonomy_type,
                str(taxonomy_key),
                taxonomy["name"],
                payload.template_version_id,
                payload.editorial_guidance,
            )
            status_url = f"/article-generation-jobs/{job_id}"
            await connection.execute(
                "UPDATE article_generation_jobs SET status_url = $2 WHERE id = $1",
                job_id,
                status_url,
            )
            await connection.executemany(
                """
                INSERT INTO article_generation_job_evidence (
                    job_id, original_input_id, segment_input_id, evidence_order,
                    evidence_text, topic_key, topic_name
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                [
                    (
                        job_id,
                        row["original_input_id"] if row["type"] == "original" else None,
                        int(row["id"].split(":", 1)[1]) if row["type"] == "segment" else None,
                        order,
                        row["excerpt"],
                        row["topic_key"],
                        row["topic_name"],
                    )
                    for order, row in enumerate(selected)
                ],
            )
            response = await _load_job(connection, job_id)
    if response is None:  # pragma: no cover
        raise RuntimeError("created generation job disappeared")
    return response


@router.get("/article-generation-jobs/{job_id}", response_model=GenerationJobResponse)
async def get_generation_job(job_id: int, request: Request) -> GenerationJobResponse:
    async with request.app.state.db_pool.acquire() as connection:
        response = await _load_job(connection, job_id)
    if response is None:
        raise HTTPException(status_code=404, detail="generation job not found")
    return response


@router.post("/article-generation-jobs/{job_id}/retry", response_model=GenerationJobResponse)
async def retry_generation_job(job_id: int, request: Request) -> GenerationJobResponse:
    async with request.app.state.db_pool.acquire() as connection:
        async with connection.transaction():
            row = await connection.fetchrow(
                "SELECT status FROM article_generation_jobs WHERE id = $1 FOR UPDATE",
                job_id,
            )
            if row is None:
                raise HTTPException(status_code=404, detail="generation job not found")
            if row["status"] in {"processing", "completed"}:
                raise HTTPException(status_code=409, detail="job cannot be retried in its current state")
            if row["status"] != "pending":
                await connection.execute(
                    """
                    UPDATE article_generation_jobs SET status = 'pending', attempts = 0,
                        available_at = CURRENT_TIMESTAMP, locked_at = NULL,
                        locked_by = NULL, last_error = NULL, dismissed_at = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = $1
                    """,
                    job_id,
                )
            response = await _load_job(connection, job_id)
    assert response is not None
    return response


@router.post("/article-generation-jobs/{job_id}/dismiss", response_model=GenerationJobResponse)
async def dismiss_generation_job(job_id: int, request: Request) -> GenerationJobResponse:
    async with request.app.state.db_pool.acquire() as connection:
        async with connection.transaction():
            row = await connection.fetchrow(
                "SELECT status FROM article_generation_jobs WHERE id = $1 FOR UPDATE",
                job_id,
            )
            if row is None:
                raise HTTPException(status_code=404, detail="generation job not found")
            if row["status"] in {"processing", "completed"}:
                raise HTTPException(status_code=409, detail="job cannot be dismissed in its current state")
            if row["status"] != "dismissed":
                await connection.execute(
                    """
                    UPDATE article_generation_jobs SET status = 'dismissed',
                        dismissed_at = CURRENT_TIMESTAMP, locked_at = NULL,
                        locked_by = NULL, updated_at = CURRENT_TIMESTAMP
                    WHERE id = $1
                    """,
                    job_id,
                )
            response = await _load_job(connection, job_id)
    assert response is not None
    return response
