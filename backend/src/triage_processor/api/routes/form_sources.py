import asyncpg
from fastapi import APIRouter, HTTPException, Query, Request, status

from triage_processor.api.form_source_schemas import (
    FormSourceCreate,
    FormSourcePageResponse,
    FormSourceResponse,
    FormSourceUpdate,
    form_source_response,
)

router = APIRouter(prefix="/form-sources", tags=["form sources"])
FORM_SOURCE_COLUMNS = """
    id,
    source,
    form_id,
    spreadsheet_id,
    sheet_name,
    ignored_headers,
    enabled,
    last_read_row,
    poll_interval_seconds,
    next_poll_at,
    last_polled_at,
    last_error,
    created_at,
    updated_at
"""
MAX_FORM_SOURCE_OFFSET = 100_000


def _conflict_detail(row: asyncpg.Record, payload: FormSourceCreate) -> str:
    if row["form_id"] == payload.form_id:
        return "form_id is already registered"
    return "spreadsheet and sheet name are already registered"


async def _existing_conflict(
    connection: asyncpg.Connection,
    *,
    form_id: str,
    spreadsheet_id: str,
    sheet_name: str,
    exclude_id: int | None = None,
) -> asyncpg.Record | None:
    return await connection.fetchrow(
        """
        SELECT id, form_id
        FROM form_sources
        WHERE
            source = 'google-sheets'
            AND ($4::bigint IS NULL OR id <> $4)
            AND (
                form_id = $1
                OR (spreadsheet_id = $2 AND sheet_name = $3)
            )
        ORDER BY id
        LIMIT 1
        """,
        form_id,
        spreadsheet_id,
        sheet_name,
        exclude_id,
    )


@router.get("", response_model=FormSourcePageResponse)
async def list_form_sources(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> FormSourcePageResponse:
    offset = (page - 1) * page_size
    if offset > MAX_FORM_SOURCE_OFFSET:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"page offset must not exceed {MAX_FORM_SOURCE_OFFSET}",
        )
    async with request.app.state.db_pool.acquire() as connection:
        total = await connection.fetchval(
            "SELECT count(*)::bigint FROM form_sources"
        )
        rows = await connection.fetch(
            f"""
            SELECT {FORM_SOURCE_COLUMNS}
            FROM form_sources
            ORDER BY id
            OFFSET $1
            LIMIT $2
            """,
            offset,
            page_size,
        )
    return FormSourcePageResponse(
        items=[form_source_response(row) for row in rows],
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=FormSourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_form_source(
    payload: FormSourceCreate,
    request: Request,
) -> FormSourceResponse:
    async with request.app.state.db_pool.acquire() as connection:
        conflict = await _existing_conflict(
            connection,
            form_id=payload.form_id,
            spreadsheet_id=payload.spreadsheet_id,
            sheet_name=payload.sheet_name,
        )
        if conflict is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_conflict_detail(conflict, payload),
            )
        try:
            row = await connection.fetchrow(
                f"""
                INSERT INTO form_sources (
                    source,
                    form_id,
                    spreadsheet_id,
                    sheet_name,
                    ignored_headers,
                    poll_interval_seconds,
                    enabled
                )
                VALUES ('google-sheets', $1, $2, $3, $4, $5, $6)
                RETURNING {FORM_SOURCE_COLUMNS}
                """,
                payload.form_id,
                payload.spreadsheet_id,
                payload.sheet_name,
                payload.ignored_headers,
                payload.poll_interval_seconds,
                payload.enabled,
            )
        except asyncpg.UniqueViolationError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="form or spreadsheet sheet is already registered",
            ) from exc
    if row is None:
        raise RuntimeError("form source insert returned no row")
    return form_source_response(row)


@router.get("/{form_source_id}", response_model=FormSourceResponse)
async def get_form_source(
    form_source_id: int,
    request: Request,
) -> FormSourceResponse:
    async with request.app.state.db_pool.acquire() as connection:
        row = await connection.fetchrow(
            f"""
            SELECT {FORM_SOURCE_COLUMNS}
            FROM form_sources
            WHERE id = $1
            """,
            form_source_id,
        )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="form source not found",
        )
    return form_source_response(row)


@router.patch("/{form_source_id}", response_model=FormSourceResponse)
async def update_form_source(
    form_source_id: int,
    payload: FormSourceUpdate,
    request: Request,
) -> FormSourceResponse:
    async with request.app.state.db_pool.acquire() as connection:
        current = await connection.fetchrow(
            """
            SELECT id, form_id, spreadsheet_id, sheet_name
            FROM form_sources
            WHERE id = $1
            """,
            form_source_id,
        )
        if current is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="form source not found",
            )
        spreadsheet_id = payload.spreadsheet_id or current["spreadsheet_id"]
        sheet_name = payload.sheet_name or current["sheet_name"]
        conflict = await _existing_conflict(
            connection,
            form_id=current["form_id"],
            spreadsheet_id=spreadsheet_id,
            sheet_name=sheet_name,
            exclude_id=form_source_id,
        )
        if conflict is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="spreadsheet and sheet name are already registered",
            )
        try:
            row = await connection.fetchrow(
                f"""
                UPDATE form_sources
                SET
                    spreadsheet_id = COALESCE($2, spreadsheet_id),
                    sheet_name = COALESCE($3, sheet_name),
                    ignored_headers = COALESCE($4, ignored_headers),
                    poll_interval_seconds = COALESCE(
                        $5,
                        poll_interval_seconds
                    ),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                RETURNING {FORM_SOURCE_COLUMNS}
                """,
                form_source_id,
                payload.spreadsheet_id,
                payload.sheet_name,
                payload.ignored_headers,
                payload.poll_interval_seconds,
            )
        except asyncpg.UniqueViolationError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="spreadsheet and sheet name are already registered",
            ) from exc
    if row is None:
        raise RuntimeError("form source disappeared during update")
    return form_source_response(row)


async def _set_enabled(
    form_source_id: int,
    *,
    enabled: bool,
    request: Request,
) -> FormSourceResponse:
    async with request.app.state.db_pool.acquire() as connection:
        row = await connection.fetchrow(
            f"""
            UPDATE form_sources
            SET
                enabled = $2,
                next_poll_at = CASE
                    WHEN $2 THEN CURRENT_TIMESTAMP
                    ELSE next_poll_at
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $1
            RETURNING {FORM_SOURCE_COLUMNS}
            """,
            form_source_id,
            enabled,
        )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="form source not found",
        )
    return form_source_response(row)


@router.post("/{form_source_id}/enable", response_model=FormSourceResponse)
async def enable_form_source(
    form_source_id: int,
    request: Request,
) -> FormSourceResponse:
    return await _set_enabled(form_source_id, enabled=True, request=request)


@router.post("/{form_source_id}/disable", response_model=FormSourceResponse)
async def disable_form_source(
    form_source_id: int,
    request: Request,
) -> FormSourceResponse:
    return await _set_enabled(form_source_id, enabled=False, request=request)

