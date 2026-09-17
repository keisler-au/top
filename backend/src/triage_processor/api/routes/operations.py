import asyncpg
from fastapi import APIRouter, Request

from triage_processor.api.operations_schemas import (
    OperationsSummaryResponse,
    QueueStageMetrics,
    TaxonomyRunMetrics,
)
from triage_processor.api.security import require_operator

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
    await require_operator(request, mutation=False)
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
        taxonomy = await connection.fetchrow(
            """
            SELECT
                count(*) FILTER (WHERE jobs.status IN ('pending', 'processing'))::bigint AS active,
                count(*) FILTER (WHERE runs.status = 'ready_for_review')::bigint AS review_backlog,
                max(runs.published_at) AS last_published_at,
                count(DISTINCT evidence.id)::bigint AS snapshot_evidence_count,
                count(DISTINCT memberships.evidence_id) FILTER (WHERE memberships.decision = 'noise')::bigint AS noise_count,
                count(DISTINCT attempts.id) FILTER (WHERE NOT attempts.accepted)::bigint AS validation_failures
            FROM taxonomy_runs runs
            LEFT JOIN taxonomy_run_jobs jobs ON jobs.taxonomy_run_id = runs.id
            LEFT JOIN taxonomy_run_evidence evidence ON evidence.taxonomy_run_id = runs.id
            LEFT JOIN taxonomy_cluster_memberships memberships ON memberships.taxonomy_run_id = runs.id
            LEFT JOIN taxonomy_topic_naming_attempts attempts ON attempts.taxonomy_run_id = runs.id
            """
        )
    return OperationsSummaryResponse(
        evidence_pipeline=[_queue_metrics(row, stage=row["stage"]) for row in pipeline_rows],
        topic_validation_corrections=0,
        topic_terminal_failures=0,
        last_theme_refresh_at=None,
        pending_theme_materializations=0,
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
        taxonomy_runs=TaxonomyRunMetrics(
            active=int(taxonomy["active"]), review_backlog=int(taxonomy["review_backlog"]),
            snapshot_evidence_count=int(taxonomy["snapshot_evidence_count"]), noise_count=int(taxonomy["noise_count"]),
            validation_failures=int(taxonomy["validation_failures"]), last_published_at=taxonomy["last_published_at"],
        ),
    )
