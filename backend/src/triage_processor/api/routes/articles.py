import json
from typing import Annotated, Any, Literal

import asyncpg
from fastapi import APIRouter, HTTPException, Query, Request, status

from triage_processor.api.article_schemas import (
    ArticleAuditResponse,
    ArticleCreate,
    ArticleEvidenceResponse,
    ArticleListResponse,
    ArticlePatch,
    ArticlePreviewRequest,
    ArticlePreviewResponse,
    ArticleResponse,
    ArticleRevisionResponse,
    ArticleTopic,
    ArticleTransition,
)
from triage_processor.articles import (
    ResolvedEvidence,
    canonical_theme_ids,
    create_article_record,
    normalize_topic,
    resolve_evidence,
)
from triage_processor.templates import render_template, sanitize_html

router = APIRouter(prefix="/articles", tags=["articles"])
MAX_PAGE_OFFSET = 100_000

ARTICLE_ORDER_BY = {
    ("updated", "desc"): "articles.updated_at DESC, articles.id DESC",
    ("updated", "asc"): "articles.updated_at ASC, articles.id ASC",
    ("title", "asc"): "lower(articles.title) ASC, articles.id ASC",
    ("title", "desc"): "lower(articles.title) DESC, articles.id DESC",
    ("status", "asc"): "articles.status ASC, articles.updated_at DESC, articles.id DESC",
    ("status", "desc"): "articles.status DESC, articles.updated_at DESC, articles.id DESC",
}


def article_order_by(sort: str, direction: str) -> str:
    return ARTICLE_ORDER_BY[(sort, direction)]


def _json_object(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise RuntimeError("database JSON value is not an object")
    return value


async def _article_response(
    connection: asyncpg.Connection,
    article_id: int,
) -> ArticleResponse | None:
    row = await connection.fetchrow(
        """
        SELECT
            articles.id,
            articles.title,
            articles.status,
            articles.generation_metadata,
            articles.approved_at,
            articles.archived_at,
            articles.created_at,
            articles.updated_at,
            revisions.id AS revision_id,
            revisions.revision_number,
            revisions.title AS revision_title,
            revisions.structured_content,
            revisions.rendered_html,
            revisions.template_version_id,
            revisions.created_at AS revision_created_at,
            (SELECT count(*) FROM article_evidence
             WHERE revision_id = revisions.id) AS evidence_count
        FROM articles
        JOIN article_revisions AS revisions
            ON revisions.id = articles.current_revision_id
        WHERE articles.id = $1
        """,
        article_id,
    )
    if row is None:
        return None
    theme_rows = await connection.fetch(
        "SELECT theme_id FROM article_themes WHERE article_id = $1 ORDER BY theme_id",
        article_id,
    )
    topic_rows = await connection.fetch(
        """
        SELECT topic_name FROM article_topics
        WHERE article_id = $1 ORDER BY lower(topic_name), topic_key
        """,
        article_id,
    )
    return ArticleResponse(
        id=row["id"],
        title=row["title"],
        status=row["status"],
        current_revision=ArticleRevisionResponse(
            id=row["revision_id"],
            revision_number=row["revision_number"],
            title=row["revision_title"],
            structured_content=_json_object(row["structured_content"]) or {},
            rendered_html=row["rendered_html"],
            template_version_id=row["template_version_id"],
            created_at=row["revision_created_at"],
        ),
        generation_metadata=_json_object(row["generation_metadata"]),
        theme_ids=[item["theme_id"] for item in theme_rows],
        topics=[ArticleTopic(name=item["topic_name"]) for item in topic_rows],
        evidence_count=int(row["evidence_count"]),
        approved_at=row["approved_at"],
        archived_at=row["archived_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _article_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="article not found")


@router.post("", response_model=ArticleResponse, status_code=status.HTTP_201_CREATED)
async def create_article(payload: ArticleCreate, request: Request) -> ArticleResponse:
    try:
        async with request.app.state.db_pool.acquire() as connection:
            async with connection.transaction():
                evidence = await resolve_evidence(
                    connection,
                    [item.evidence_id for item in payload.evidence],
                )
                article_id, _ = await create_article_record(
                    connection,
                    title=payload.title,
                    structured_content=payload.structured_content,
                    rendered_html=(
                        sanitize_html(payload.rendered_html)
                        if payload.rendered_html is not None
                        else None
                    ),
                    generation_metadata=payload.generation_metadata,
                    theme_ids=payload.theme_ids,
                    topic_names=[item.name for item in payload.topics],
                    evidence=evidence,
                    evidence_citations=[item.citation_id for item in payload.evidence],
                )
                response = await _article_response(connection, article_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if response is None:  # pragma: no cover - inserted in same transaction
        raise RuntimeError("created article disappeared")
    return response


@router.get("", response_model=ArticleListResponse)
async def list_articles(
    request: Request,
    lifecycle_status: Annotated[str | None, Query(alias="status")] = None,
    theme_id: Annotated[int | None, Query(ge=1)] = None,
    topic: str | None = None,
    search: str | None = None,
    sort: Literal["updated", "title", "status"] = "updated",
    direction: Literal["asc", "desc"] = "desc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> ArticleListResponse:
    if lifecycle_status not in {None, "draft", "ready_for_review", "approved", "archived"}:
        raise HTTPException(status_code=422, detail="invalid article status")
    topic_key = normalize_topic(topic)[0] if topic and topic.strip() else None
    search = search.strip() if search and search.strip() else None
    offset = (page - 1) * page_size
    if offset > MAX_PAGE_OFFSET:
        raise HTTPException(status_code=422, detail="page offset is too large")
    predicate = """
        ($1::text IS NULL OR articles.status = $1)
        AND ($2::bigint IS NULL OR EXISTS (
            SELECT 1 FROM article_themes
            WHERE article_id = articles.id AND theme_id = $2
        ))
        AND ($3::text IS NULL OR EXISTS (
            SELECT 1 FROM article_topics
            WHERE article_id = articles.id AND topic_key = $3
        ))
        AND ($4::text IS NULL OR articles.title ILIKE '%' || $4 || '%')
    """
    async with request.app.state.db_pool.acquire() as connection:
        total = await connection.fetchval(
            f"SELECT count(*) FROM articles WHERE {predicate}",
            lifecycle_status,
            theme_id,
            topic_key,
            search,
        )
        rows = await connection.fetch(
            f"""
            SELECT articles.id FROM articles
            WHERE {predicate}
            ORDER BY {article_order_by(sort, direction)}
            OFFSET $5 LIMIT $6
            """,
            lifecycle_status,
            theme_id,
            topic_key,
            search,
            offset,
            page_size,
        )
        items = []
        for row in rows:
            item = await _article_response(connection, row["id"])
            if item is not None:
                items.append(item)
    return ArticleListResponse(items=items, total=int(total or 0), page=page, page_size=page_size)


@router.get("/{article_id}", response_model=ArticleResponse)
async def get_article(article_id: int, request: Request) -> ArticleResponse:
    async with request.app.state.db_pool.acquire() as connection:
        response = await _article_response(connection, article_id)
    if response is None:
        raise _article_not_found()
    return response


@router.post("/{article_id}/preview", response_model=ArticlePreviewResponse)
async def preview_article(
    article_id: int,
    payload: ArticlePreviewRequest,
    request: Request,
) -> ArticlePreviewResponse:
    async with request.app.state.db_pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT revisions.id, versions.html_source
            FROM articles
            JOIN article_revisions AS revisions
                ON revisions.id = articles.current_revision_id
            LEFT JOIN article_template_versions AS versions
                ON versions.id = revisions.template_version_id
            WHERE articles.id = $1
            """,
            article_id,
        )
    if row is None:
        raise _article_not_found()
    if payload.expected_revision_id is not None and row["id"] != payload.expected_revision_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="article changed since it was loaded; refresh before previewing",
        )
    if row["html_source"] is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="article revision has no template and cannot be previewed",
        )
    try:
        rendered = render_template(
            row["html_source"],
            {**payload.structured_content, "title": payload.title},
        )
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"invalid structured article content: {error}",
        ) from error
    return ArticlePreviewResponse(rendered_html=rendered)


async def _current_evidence(
    connection: asyncpg.Connection,
    revision_id: int,
) -> tuple[list[ResolvedEvidence], list[str | None]]:
    rows = await connection.fetch(
        """
        SELECT
            evidence.original_input_id,
            evidence.segment_input_id,
            evidence.citation_id,
            evidence.topic_key,
            COALESCE(segments.segment_text, inputs.original_text) AS text,
            COALESCE(segments.topic, inputs.topic) AS topic_name
        FROM article_evidence AS evidence
        LEFT JOIN original_inputs AS inputs
            ON inputs.id = evidence.original_input_id
        LEFT JOIN segment_inputs AS segments
            ON segments.id = evidence.segment_input_id
        WHERE evidence.revision_id = $1
        ORDER BY evidence.evidence_order
        """,
        revision_id,
    )
    evidence = [
        ResolvedEvidence(
            evidence_id=(
                f"segment:{row['segment_input_id']}"
                if row["segment_input_id"] is not None
                else f"original:{row['original_input_id']}"
            ),
            original_input_id=row["original_input_id"],
            segment_input_id=row["segment_input_id"],
            text=row["text"],
            topic_key=row["topic_key"],
            topic_name=row["topic_name"],
        )
        for row in rows
    ]
    return evidence, [row["citation_id"] for row in rows]


@router.patch("/{article_id}", response_model=ArticleResponse)
async def patch_article(
    article_id: int,
    payload: ArticlePatch,
    request: Request,
) -> ArticleResponse:
    try:
        async with request.app.state.db_pool.acquire() as connection:
            async with connection.transaction():
                current = await connection.fetchrow(
                    """
                    SELECT articles.status, articles.current_revision_id,
                           revisions.revision_number, revisions.title,
                           revisions.structured_content, revisions.rendered_html,
                           revisions.template_version_id
                    FROM articles
                    JOIN article_revisions AS revisions
                        ON revisions.id = articles.current_revision_id
                    WHERE articles.id = $1
                    FOR UPDATE OF articles
                    """,
                    article_id,
                )
                if current is None:
                    raise _article_not_found()
                if current["status"] != "draft":
                    raise HTTPException(
                        status_code=409,
                        detail="only draft articles can be edited",
                    )
                if (
                    payload.expected_revision_id is not None
                    and current["current_revision_id"] != payload.expected_revision_id
                ):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="article changed since it was loaded; refresh before saving",
                    )

                fields = payload.model_fields_set
                revision_changed = bool(
                    fields & {"title", "structured_content", "rendered_html", "evidence"}
                )
                revision_id = current["current_revision_id"]
                if revision_changed:
                    if payload.evidence is not None:
                        evidence = await resolve_evidence(
                            connection,
                            [item.evidence_id for item in payload.evidence],
                        )
                        citations = [item.citation_id for item in payload.evidence]
                    else:
                        evidence, citations = await _current_evidence(connection, revision_id)
                    title = payload.title or current["title"]
                    content = (
                        payload.structured_content
                        if payload.structured_content is not None
                        else _json_object(current["structured_content"]) or {}
                    )
                    rendered_html = (
                        (
                            sanitize_html(payload.rendered_html)
                            if payload.rendered_html is not None
                            else None
                        )
                        if "rendered_html" in fields
                        else current["rendered_html"]
                    )
                    revision_id = await connection.fetchval(
                        """
                        INSERT INTO article_revisions (
                            article_id, revision_number, title, structured_content,
                            rendered_html, template_version_id
                        ) VALUES ($1, $2, $3, $4::jsonb, $5, $6)
                        RETURNING id
                        """,
                        article_id,
                        current["revision_number"] + 1,
                        title,
                        json.dumps(content),
                        rendered_html,
                        current["template_version_id"],
                    )
                    await connection.executemany(
                        """
                        INSERT INTO article_evidence (
                            revision_id, original_input_id, segment_input_id,
                            evidence_order, citation_id, topic_key
                        ) VALUES ($1, $2, $3, $4, $5, $6)
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
                        UPDATE articles SET title = $2, current_revision_id = $3,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = $1
                        """,
                        article_id,
                        title,
                        revision_id,
                    )
                    await connection.execute(
                        """
                        INSERT INTO article_audit (article_id, revision_id, action)
                        VALUES ($1, $2, 'revised')
                        """,
                        article_id,
                        revision_id,
                    )

                if payload.theme_ids is not None or payload.topics is not None:
                    existing_themes = await connection.fetch(
                        "SELECT theme_id FROM article_themes WHERE article_id = $1",
                        article_id,
                    )
                    existing_topics = await connection.fetch(
                        "SELECT topic_name FROM article_topics WHERE article_id = $1",
                        article_id,
                    )
                    themes = await canonical_theme_ids(
                        connection,
                        payload.theme_ids
                        if payload.theme_ids is not None
                        else [row["theme_id"] for row in existing_themes],
                    )
                    topics = (
                        [normalize_topic(item.name) for item in payload.topics]
                        if payload.topics is not None
                        else [normalize_topic(row["topic_name"]) for row in existing_topics]
                    )
                    if not themes and not topics:
                        raise ValueError("an article requires at least one theme or topic tag")
                    await connection.execute("DELETE FROM article_themes WHERE article_id = $1", article_id)
                    await connection.execute("DELETE FROM article_topics WHERE article_id = $1", article_id)
                    if themes:
                        await connection.executemany(
                            "INSERT INTO article_themes (article_id, theme_id) VALUES ($1, $2)",
                            [(article_id, item) for item in themes],
                        )
                    if topics:
                        await connection.executemany(
                            "INSERT INTO article_topics (article_id, topic_key, topic_name) VALUES ($1, $2, $3)",
                            [(article_id, key, name) for key, name in dict(topics).items()],
                        )
                    await connection.execute(
                        "UPDATE articles SET updated_at = CURRENT_TIMESTAMP WHERE id = $1",
                        article_id,
                    )
                if "generation_metadata" in fields:
                    await connection.execute(
                        "UPDATE articles SET generation_metadata = $2::jsonb, updated_at = CURRENT_TIMESTAMP WHERE id = $1",
                        article_id,
                        json.dumps(payload.generation_metadata) if payload.generation_metadata is not None else None,
                    )
                response = await _article_response(connection, article_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if response is None:  # pragma: no cover
        raise RuntimeError("updated article disappeared")
    return response


async def _transition(
    connection: asyncpg.Connection,
    *,
    article_id: int,
    from_statuses: set[str],
    to_status: str,
    action: str,
    payload: ArticleTransition,
) -> ArticleResponse:
    row = await connection.fetchrow(
        """
        SELECT articles.status, articles.current_revision_id,
               revisions.structured_content, revisions.rendered_html,
               (SELECT count(*) FROM article_themes WHERE article_id = articles.id)
                 + (SELECT count(*) FROM article_topics WHERE article_id = articles.id)
                 AS tag_count,
               (SELECT count(*) FROM article_evidence
                WHERE revision_id = articles.current_revision_id) AS evidence_count
        FROM articles
        JOIN article_revisions AS revisions ON revisions.id = articles.current_revision_id
        WHERE articles.id = $1
        FOR UPDATE OF articles
        """,
        article_id,
    )
    if row is None:
        raise _article_not_found()
    if row["status"] not in from_statuses:
        raise HTTPException(status_code=409, detail=f"article cannot be {action} from {row['status']}")
    if to_status in {"ready_for_review", "approved"}:
        if row["rendered_html"] is None or int(row["tag_count"]) < 1 or int(row["evidence_count"]) < 1:
            raise HTTPException(
                status_code=409,
                detail="article requires rendered content, taxonomy tags, and evidence",
            )
    await connection.execute(
        """
        UPDATE articles
        SET status = $2,
            approved_at = CASE WHEN $2 = 'approved' THEN CURRENT_TIMESTAMP ELSE NULL END,
            archived_at = CASE WHEN $2 = 'archived' THEN CURRENT_TIMESTAMP ELSE NULL END,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = $1
        """,
        article_id,
        to_status,
    )
    await connection.execute(
        """
        INSERT INTO article_audit (article_id, revision_id, action, actor, note)
        VALUES ($1, $2, $3, $4, $5)
        """,
        article_id,
        row["current_revision_id"],
        action,
        payload.actor,
        payload.note,
    )
    response = await _article_response(connection, article_id)
    if response is None:  # pragma: no cover
        raise RuntimeError("transitioned article disappeared")
    return response


async def _run_transition(
    request: Request,
    article_id: int,
    payload: ArticleTransition,
    *,
    from_statuses: set[str],
    to_status: str,
    action: str,
) -> ArticleResponse:
    async with request.app.state.db_pool.acquire() as connection:
        async with connection.transaction():
            return await _transition(
                connection,
                article_id=article_id,
                from_statuses=from_statuses,
                to_status=to_status,
                action=action,
                payload=payload,
            )


@router.post("/{article_id}/submit", response_model=ArticleResponse)
async def submit_article(article_id: int, payload: ArticleTransition, request: Request) -> ArticleResponse:
    return await _run_transition(request, article_id, payload, from_statuses={"draft"}, to_status="ready_for_review", action="submitted")


@router.post("/{article_id}/approve", response_model=ArticleResponse)
async def approve_article(article_id: int, payload: ArticleTransition, request: Request) -> ArticleResponse:
    return await _run_transition(request, article_id, payload, from_statuses={"ready_for_review"}, to_status="approved", action="approved")


@router.post("/{article_id}/return-to-draft", response_model=ArticleResponse)
async def return_article_to_draft(article_id: int, payload: ArticleTransition, request: Request) -> ArticleResponse:
    return await _run_transition(request, article_id, payload, from_statuses={"ready_for_review", "approved"}, to_status="draft", action="returned_to_draft")


@router.post("/{article_id}/archive", response_model=ArticleResponse)
async def archive_article(article_id: int, payload: ArticleTransition, request: Request) -> ArticleResponse:
    return await _run_transition(request, article_id, payload, from_statuses={"draft", "ready_for_review", "approved"}, to_status="archived", action="archived")


@router.get("/{article_id}/evidence", response_model=list[ArticleEvidenceResponse])
async def article_evidence(article_id: int, request: Request) -> list[ArticleEvidenceResponse]:
    async with request.app.state.db_pool.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT evidence.id, evidence.evidence_order, evidence.citation_id,
                   evidence.topic_key, evidence.original_input_id,
                   evidence.segment_input_id,
                   COALESCE(segments.segment_text, source_inputs.original_text) AS text,
                   source_inputs.id AS source_input_id,
                   source_inputs.original_text,
                   COALESCE(segments.topic, source_inputs.topic) AS topic_name,
                   source_inputs.source,
                   source_inputs.submission_key,
                   questions.form_key,
                   questions.question_key,
                   questions.question_version,
                   questions.question_text
            FROM articles
            JOIN article_evidence AS evidence
                ON evidence.revision_id = articles.current_revision_id
            LEFT JOIN segment_inputs AS segments ON segments.id = evidence.segment_input_id
            JOIN original_inputs AS source_inputs
                ON source_inputs.id = COALESCE(
                    evidence.original_input_id,
                    segments.original_input_id
                )
            LEFT JOIN questions ON questions.id = source_inputs.question_id
            WHERE articles.id = $1
            ORDER BY evidence.evidence_order
            """,
            article_id,
        )
        exists = await connection.fetchval("SELECT EXISTS (SELECT 1 FROM articles WHERE id = $1)", article_id)
    if not exists:
        raise _article_not_found()
    return [
        ArticleEvidenceResponse(
            id=row["id"],
            evidence_id=(f"segment:{row['segment_input_id']}" if row["segment_input_id"] is not None else f"original:{row['original_input_id']}"),
            evidence_order=row["evidence_order"],
            citation_id=row["citation_id"],
            topic_key=row["topic_key"],
            text=row["text"],
            original_input_id=row["source_input_id"],
            evidence_type=(
                "segment" if row["segment_input_id"] is not None else "original"
            ),
            original_text=row["original_text"],
            topic_name=row["topic_name"],
            source=row["source"],
            submission_key=row["submission_key"],
            question_context=(
                {
                    "form_key": row["form_key"],
                    "question_key": row["question_key"],
                    "question_version": row["question_version"],
                    "question_text": row["question_text"],
                }
                if row["question_key"] is not None
                else None
            ),
        )
        for row in rows
    ]


@router.get("/{article_id}/history", response_model=list[ArticleAuditResponse])
async def article_history(article_id: int, request: Request) -> list[ArticleAuditResponse]:
    async with request.app.state.db_pool.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT id, revision_id, action, actor, note, created_at
            FROM article_audit WHERE article_id = $1
            ORDER BY created_at DESC, id DESC
            """,
            article_id,
        )
        exists = await connection.fetchval("SELECT EXISTS (SELECT 1 FROM articles WHERE id = $1)", article_id)
    if not exists:
        raise _article_not_found()
    return [ArticleAuditResponse.model_validate(dict(row)) for row in rows]
