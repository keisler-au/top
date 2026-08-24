from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Path, Query, Request, status

from triage_processor.api.dashboard_queries import (
    DASHBOARD_SUMMARY_QUERY,
    evidence_count_query,
    evidence_list_query,
    recommendation_query,
    taxonomy_count_query,
    taxonomy_detail_query,
    taxonomy_list_query,
)
from triage_processor.api.dashboard_schemas import (
    DashboardSummaryResponse,
    EvidenceItemResponse,
    EvidencePageResponse,
    EvidenceQuestionContextResponse,
    RecommendationItemResponse,
    RecommendationResponse,
    RecommendationStrategy,
    TaxonomyItemResponse,
    TaxonomyPageResponse,
    TaxonomyType,
)

router = APIRouter(tags=["dashboard"])
MAX_PAGE_OFFSET = 100_000

SortField = Literal["name", "evidence", "articles", "approved_articles"]
SortDirection = Literal["asc", "desc"]


def _normalized_search(search: str | None) -> str | None:
    if search is None:
        return None
    normalized = search.strip()
    return normalized or None


def _offset(page: int, page_size: int) -> int:
    offset = (page - 1) * page_size
    if offset > MAX_PAGE_OFFSET:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"page offset must not exceed {MAX_PAGE_OFFSET}",
        )
    return offset


def _taxonomy_key(taxonomy_type: TaxonomyType, raw_key: str) -> int | str:
    if taxonomy_type == "theme":
        try:
            key = int(raw_key)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="theme key must be a positive integer",
            ) from exc
        if key < 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="theme key must be a positive integer",
            )
        return key

    key = raw_key.strip()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="topic key must be non-empty",
        )
    return key


def _taxonomy_item(
    row: Any,
    taxonomy_type: TaxonomyType,
) -> TaxonomyItemResponse:
    evidence_count = int(row["evidence_count"])
    approved_count = int(row["approved_article_count"])
    if evidence_count == 0:
        coverage_state = "no_evidence"
    elif approved_count == 0:
        coverage_state = "uncovered"
    else:
        coverage_state = "covered"

    return TaxonomyItemResponse(
        type=taxonomy_type,
        key=row["key"],
        name=row["name"],
        description=row["description"],
        evidence_count=evidence_count,
        article_count=int(row["article_count"]),
        approved_article_count=approved_count,
        coverage_state=coverage_state,
        generation_eligible=evidence_count > 0,
    )


@router.get("/dashboard/summary", response_model=DashboardSummaryResponse)
async def dashboard_summary(request: Request) -> DashboardSummaryResponse:
    async with request.app.state.db_pool.acquire() as connection:
        row = await connection.fetchrow(DASHBOARD_SUMMARY_QUERY)
    if row is None:
        raise RuntimeError("dashboard summary query returned no row")
    return DashboardSummaryResponse.model_validate(dict(row))


@router.get("/taxonomy", response_model=TaxonomyPageResponse)
async def list_taxonomy(
    request: Request,
    taxonomy_type: Annotated[TaxonomyType, Query(alias="type")],
    search: str | None = None,
    sort: SortField = "evidence",
    direction: SortDirection = "desc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> TaxonomyPageResponse:
    offset = _offset(page, page_size)
    search = _normalized_search(search)
    async with request.app.state.db_pool.acquire() as connection:
        total = await connection.fetchval(
            taxonomy_count_query(taxonomy_type),
            search,
        )
        rows = await connection.fetch(
            taxonomy_list_query(
                taxonomy_type,
                sort=sort,
                direction=direction,
            ),
            search,
            offset,
            page_size,
        )
    return TaxonomyPageResponse(
        items=[_taxonomy_item(row, taxonomy_type) for row in rows],
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )


@router.get(
    "/taxonomy/{taxonomy_type}/{taxonomy_key:path}/evidence",
    response_model=EvidencePageResponse,
)
async def list_taxonomy_evidence(
    request: Request,
    taxonomy_type: Annotated[TaxonomyType, Path()],
    taxonomy_key: str,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> EvidencePageResponse:
    key = _taxonomy_key(taxonomy_type, taxonomy_key)
    offset = _offset(page, page_size)

    async with request.app.state.db_pool.acquire() as connection:
        taxonomy = await connection.fetchrow(
            taxonomy_detail_query(taxonomy_type),
            key,
        )
        if taxonomy is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{taxonomy_type} not found",
            )
        total = await connection.fetchval(
            evidence_count_query(taxonomy_type),
            key,
        )
        rows = await connection.fetch(
            evidence_list_query(taxonomy_type),
            key,
            offset,
            page_size,
        )

    items: list[EvidenceItemResponse] = []
    for row in rows:
        data = dict(row)
        question_context = None
        if data.get("question_key") is not None:
            question_context = EvidenceQuestionContextResponse(
                form_key=data["form_key"],
                form_id=data.get("form_id"),
                question_key=data["question_key"],
                question_version=data["question_version"],
                question_text=data["question_text"],
            )
        items.append(
            EvidenceItemResponse(
                id=data["id"],
                type=data["type"],
                excerpt=data["excerpt"],
                original_text=data["original_text"],
                original_input_id=data["original_input_id"],
                segment_order=data["segment_order"],
                topic_key=data["topic_key"],
                topic_name=data["topic_name"],
                source=data["source"],
                submission_key=data["submission_key"],
                source_record_key=data["source_record_key"],
                question_context=question_context,
                created_at=data["created_at"],
            )
        )

    return EvidencePageResponse(
        items=items,
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )


@router.get(
    "/taxonomy/{taxonomy_type}/{taxonomy_key:path}",
    response_model=TaxonomyItemResponse,
)
async def taxonomy_detail(
    request: Request,
    taxonomy_type: Annotated[TaxonomyType, Path()],
    taxonomy_key: str,
) -> TaxonomyItemResponse:
    key = _taxonomy_key(taxonomy_type, taxonomy_key)
    async with request.app.state.db_pool.acquire() as connection:
        row = await connection.fetchrow(
            taxonomy_detail_query(taxonomy_type),
            key,
        )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{taxonomy_type} not found",
        )
    return _taxonomy_item(row, taxonomy_type)


@router.get(
    "/recommendations/articles",
    response_model=RecommendationResponse,
)
async def article_recommendations(
    request: Request,
    taxonomy_type: Annotated[TaxonomyType, Query(alias="type")],
    strategy: RecommendationStrategy,
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
) -> RecommendationResponse:
    async with request.app.state.db_pool.acquire() as connection:
        rows = await connection.fetch(
            recommendation_query(taxonomy_type, strategy),
            limit,
        )

    items: list[RecommendationItemResponse] = []
    for row in rows:
        base = _taxonomy_item(row, taxonomy_type)
        if strategy == "most-evidence":
            explanation = (
                f"Recommended because it has {base.evidence_count} evidence "
                f"items and {base.approved_article_count} approved articles."
            )
        else:
            explanation = (
                "Recommended because it has "
                f"{base.approved_article_count} approved articles for "
                f"{base.evidence_count} evidence items."
            )
        items.append(
            RecommendationItemResponse(
                **base.model_dump(),
                explanation=explanation,
            )
        )

    return RecommendationResponse(
        taxonomy_type=taxonomy_type,
        strategy=strategy,
        items=items,
    )
