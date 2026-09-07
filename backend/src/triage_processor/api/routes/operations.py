import asyncpg
from fastapi import APIRouter, Request

from triage_processor.api.operations_schemas import (
    OperationsSummaryResponse,
    QueueStageMetrics,
)

router = APIRouter(prefix="/operations", tags=["operations"])


def _queue_metrics(row: asyncpg.Record, *, stage: str) -> QueueStageMetrics:
    return QueueStageMetrics(
        stage=stage,
        pending=int(row["pending"]),
        processing=int(row["processing"]),
        retrying=int(row["retrying"]),
        failed=int(row["failed"]),
        oldest_ready_wait_seconds=(
            int(row["oldest_ready_wait_seconds"])
            if row["oldest_ready_wait_seconds"] is not None
            else None
        ),
    )


@router.get("/summary", response_model=OperationsSummaryResponse)
async def operations_summary(request: Request) -> OperationsSummaryResponse:
    """Return bounded operational counters without queue payloads or source text."""
    async with request.app.state.db_pool.acquire() as connection:
        pipeline_rows = await connection.fetch(
            """
            SELECT job_type AS stage,
                   count(*) FILTER (WHERE status = 'pending' AND available_at <= CURRENT_TIMESTAMP) AS pending,
                   count(*) FILTER (WHERE status = 'processing') AS processing,
                   count(*) FILTER (WHERE status = 'pending' AND available_at > CURRENT_TIMESTAMP) AS retrying,
                   count(*) FILTER (WHERE status = 'failed') AS failed,
                   extract(epoch FROM max(CURRENT_TIMESTAMP - available_at)
                       FILTER (WHERE status = 'pending' AND available_at <= CURRENT_TIMESTAMP))::bigint
                       AS oldest_ready_wait_seconds
            FROM worker_jobs
            GROUP BY job_type
            ORDER BY job_type
            """
        )
        topic = await connection.fetchrow(
            """
            SELECT
                count(*) FILTER (WHERE NOT accepted)::bigint AS corrections,
                (SELECT count(*) FROM worker_jobs WHERE job_type = 'topics' AND status = 'failed')::bigint AS terminal_failures
            FROM topic_assignment_attempts
            """
        )
        theme = await connection.fetchrow(
            """
            SELECT
                (SELECT max(completed_at) FROM worker_jobs WHERE job_type = 'themes' AND status = 'completed') AS last_refresh,
                (SELECT count(*) FROM theme_suggestions WHERE materialized_at IS NULL)::bigint AS pending_materializations
            """
        )
        generation = await connection.fetchrow(
            """
            SELECT
                count(*) FILTER (WHERE status = 'pending' AND available_at <= CURRENT_TIMESTAMP) AS pending,
                count(*) FILTER (WHERE status = 'processing') AS processing,
                count(*) FILTER (WHERE status = 'pending' AND available_at > CURRENT_TIMESTAMP) AS retrying,
                count(*) FILTER (WHERE status = 'failed') AS failed,
                extract(epoch FROM max(CURRENT_TIMESTAMP - available_at)
                    FILTER (WHERE status = 'pending' AND available_at <= CURRENT_TIMESTAMP))::bigint AS oldest_ready_wait_seconds,
                avg(extract(epoch FROM completed_at - created_at)) FILTER (WHERE status = 'completed')::bigint AS average_duration
            FROM article_generation_jobs
            """
        )
        forms = await connection.fetchrow(
            """
            SELECT
                count(*) FILTER (WHERE enabled)::bigint AS enabled_sources,
                count(*) FILTER (WHERE enabled AND last_error IS NOT NULL)::bigint AS poll_failures,
                extract(epoch FROM max(CURRENT_TIMESTAMP - last_polled_at)
                    FILTER (WHERE enabled AND last_polled_at IS NOT NULL))::bigint AS oldest_cursor_age
            FROM form_sources
            """
        )
        approvals = await connection.fetchval(
            """
            SELECT count(*) FROM article_audit
            WHERE action = 'approved' AND created_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
            """
        )
    return OperationsSummaryResponse(
        evidence_pipeline=[_queue_metrics(row, stage=row["stage"]) for row in pipeline_rows],
        topic_validation_corrections=int(topic["corrections"]),
        topic_terminal_failures=int(topic["terminal_failures"]),
        last_theme_refresh_at=theme["last_refresh"],
        pending_theme_materializations=int(theme["pending_materializations"]),
        article_generation=_queue_metrics(generation, stage="article_generation"),
        average_generation_duration_seconds=(
            int(generation["average_duration"])
            if generation["average_duration"] is not None
            else None
        ),
        enabled_form_sources=int(forms["enabled_sources"]),
        form_poll_failures=int(forms["poll_failures"]),
        oldest_form_cursor_age_seconds=(
            int(forms["oldest_cursor_age"])
            if forms["oldest_cursor_age"] is not None
            else None
        ),
        approvals_last_24_hours=int(approvals),
    )
