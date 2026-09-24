import asyncpg
from fastapi import APIRouter, Request

from triage_processor.api.operations_schemas import (
    OperationsSummaryResponse,
    QueueStageMetrics,
    TaxonomyRunMetrics,
)
from triage_processor.api.security import require_operator
from triage_processor.taxonomy_status import current_candidate_status

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
                (SELECT count(*) FROM taxonomy_run_jobs WHERE status IN ('pending','processing')) AS active,
                (SELECT count(*) FROM taxonomy_runs WHERE status='ready_for_review') AS review_backlog,
                (SELECT max(published_at) FROM taxonomy_runs) AS last_published_at,
                (SELECT count(*) FROM taxonomy_run_evidence) AS snapshot_evidence_count,
                (SELECT count(*) FROM taxonomy_cluster_memberships WHERE decision='noise') AS noise_count,
                (SELECT count(*) FROM taxonomy_topic_naming_attempts WHERE NOT accepted) AS validation_failures
            """
        )
        automation = await connection.fetchrow("""
            SELECT checkpoint.policy_version, checkpoint.last_failure_code,
                   checkpoint.scheduler_heartbeat_expires_at < CURRENT_TIMESTAMP AS scheduler_expired,
                   checkpoint.scheduler_heartbeat_expires_at IS NULL AS scheduler_never_started,
                   count(inputs.id) FILTER (WHERE inputs.status IN ('new','ready_for_embedding'))::bigint AS preparing_evidence,
                   EXISTS (SELECT 1 FROM worker_jobs WHERE status='failed') AS evidence_failed,
                   EXISTS (SELECT 1 FROM taxonomy_runs WHERE status='published') AS has_published
            FROM taxonomy_automation_checkpoints checkpoint
            FULL JOIN original_inputs inputs ON TRUE
            GROUP BY checkpoint.policy_version, checkpoint.last_failure_code,
                     checkpoint.scheduler_heartbeat_expires_at
            ORDER BY checkpoint.policy_version NULLS LAST
            LIMIT 1
        """)
        if automation is None:
            automation = {"policy_version": None, "last_failure_code": None,
                          "preparing_evidence": 0, "has_published": False,
                          "evidence_failed": False, "scheduler_expired": False,
                          "scheduler_never_started": True}
        candidate = await current_candidate_status(
            connection, automatic_policy_version=automation["policy_version"]
        )
        if candidate == "quality_blocked":
            automation_state = "blocked_by_quality"
        elif candidate == "candidate_failed":
            automation_state = "blocked_by_failure"
        elif candidate == "running_candidate":
            automation_state = "running_candidate"
        elif automation["last_failure_code"] == "policy_disabled":
            automation_state = "blocked_by_policy"
        elif automation["last_failure_code"]:
            automation_state = "blocked_by_failure"
        elif automation["has_published"]:
            automation_state = "automatically_published"
        elif automation["evidence_failed"]:
            automation_state = "blocked_by_failure"
        elif automation["scheduler_expired"] or automation["scheduler_never_started"]:
            automation_state = "scheduler_unavailable"
        elif automation["preparing_evidence"]:
            automation_state = "preparing_evidence"
        else:
            automation_state = "waiting_for_automation"
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
            automation_state=automation_state,
            automation_policy_version=automation["policy_version"],
            automation_failure_code=automation["last_failure_code"],
        ),
    )
