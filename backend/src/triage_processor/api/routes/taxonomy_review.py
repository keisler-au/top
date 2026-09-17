"""Candidate-run review and bounded publication-gate operations."""

import os

import asyncpg
from fastapi import APIRouter, HTTPException, Request, status

from triage_processor.api.taxonomy_review_schemas import (
    TaxonomyRunCreate,
    TaxonomyRunCreated,
    TaxonomyRunDecision,
    TaxonomyRunReview,
    TaxonomyRunSummary,
    TaxonomyRunTopicReview,
)
from triage_processor.api.security import require_operator
from triage_processor.taxonomy_snapshots import (
    IdempotencyConflictError,
    SnapshotRequest,
    SnapshotValidationError,
    create_taxonomy_snapshot,
)

router = APIRouter(prefix="/taxonomy-runs", tags=["taxonomy review"])

_SUMMARY_SQL = """
SELECT run.id, run.status, run.source_cutoff, run.updated_at,
       count(DISTINCT revisions.id)::bigint AS topic_count,
       count(DISTINCT memberships.evidence_id) FILTER (WHERE memberships.decision = 'noise')::bigint AS noise_count,
       count(DISTINCT themes.id)::bigint AS theme_count,
       count(DISTINCT attempts.id) FILTER (WHERE NOT attempts.accepted)::bigint AS validation_failure_count,
       count(DISTINCT members.evidence_id) FILTER (
           WHERE published.id IS NOT NULL AND NOT EXISTS (
               SELECT 1 FROM topic_memberships prior_members
               JOIN topic_revisions prior_revisions ON prior_revisions.id = prior_members.topic_revision_id
               WHERE prior_members.taxonomy_run_id = published.id
                 AND EXISTS (
                    SELECT 1
                    FROM taxonomy_run_evidence prior_evidence
                    JOIN taxonomy_run_evidence candidate_evidence
                      ON candidate_evidence.id = members.evidence_id
                    WHERE prior_evidence.id = prior_members.evidence_id
                      AND prior_evidence.taxonomy_run_id = published.id
                      AND prior_evidence.original_input_id = candidate_evidence.original_input_id
                      AND prior_evidence.segment_input_id IS NOT DISTINCT FROM candidate_evidence.segment_input_id
                 )
                 AND prior_revisions.topic_id = revisions.topic_id
           )
       )::bigint AS changed_membership_count
FROM taxonomy_runs run
LEFT JOIN topic_revisions revisions ON revisions.taxonomy_run_id = run.id
LEFT JOIN taxonomy_cluster_memberships memberships ON memberships.taxonomy_run_id = run.id
LEFT JOIN taxonomy_candidate_themes themes ON themes.taxonomy_run_id = run.id
LEFT JOIN taxonomy_topic_naming_attempts attempts ON attempts.taxonomy_run_id = run.id
LEFT JOIN topic_memberships members ON members.taxonomy_run_id = run.id AND members.topic_revision_id = revisions.id
LEFT JOIN taxonomy_runs published ON published.status = 'published'
WHERE run.id = $1
GROUP BY run.id
"""


def _summary(row: asyncpg.Record) -> TaxonomyRunSummary:
    return TaxonomyRunSummary(
        id=row["id"], status=row["status"], source_cutoff=row["source_cutoff"],
        updated_at=row["updated_at"], topic_count=int(row["topic_count"]),
        noise_count=int(row["noise_count"]), theme_count=int(row["theme_count"]),
        validation_failure_count=int(row["validation_failure_count"]),
        changed_membership_count=int(row["changed_membership_count"]),
    )


@router.post("", response_model=TaxonomyRunCreated, status_code=status.HTTP_201_CREATED)
async def create_taxonomy_run(
    payload: TaxonomyRunCreate, request: Request
) -> TaxonomyRunCreated:
    """Atomically freeze canonical evidence, then queue the committed run."""
    await require_operator(request, mutation=True)
    snapshot_request = SnapshotRequest(**payload.model_dump())
    try:
        result = await create_taxonomy_snapshot(request.app.state.db_pool, snapshot_request)
    except SnapshotValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "invalid_taxonomy_snapshot", "counts": error.counts},
        ) from error
    except IdempotencyConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "taxonomy_idempotency_conflict"},
        ) from error
    return TaxonomyRunCreated(
        id=result.id,
        status=result.status,
        source_cutoff=result.source_cutoff,
        evidence_count=result.evidence_count,
        embedding_dimension=result.embedding_dimension,
        queued=result.queued,
        reused=result.reused,
    )


@router.get("/{run_id}", response_model=TaxonomyRunReview)
async def review_taxonomy_run(run_id: int, request: Request) -> TaxonomyRunReview:
    await require_operator(request, mutation=False)
    async with request.app.state.db_pool.acquire() as connection:
        summary = await connection.fetchrow(_SUMMARY_SQL, run_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="taxonomy run not found")
        rows = await connection.fetch("""
            SELECT revisions.id, revisions.topic_id, revisions.name,
                   revisions.literal_description, revisions.support_count,
                   revisions.continuity_decision,
                   COALESCE(array_agg(representatives.evidence_id ORDER BY representatives.representative_order)
                       FILTER (WHERE representatives.evidence_id IS NOT NULL), ARRAY[]::bigint[]) AS representative_evidence_ids
            FROM topic_revisions revisions
            LEFT JOIN topic_representative_evidence representatives
              ON representatives.topic_revision_id = revisions.id
             AND representatives.taxonomy_run_id = revisions.taxonomy_run_id
            WHERE revisions.taxonomy_run_id = $1
            GROUP BY revisions.id
            ORDER BY revisions.name COLLATE "C", revisions.id
        """, run_id)
    base = _summary(summary)
    return TaxonomyRunReview(
        **base.model_dump(), candidate_theme_count=base.theme_count,
        topics=[TaxonomyRunTopicReview(
            id=row["id"], topic_id=row["topic_id"], name=row["name"],
            description=row["literal_description"], support_count=row["support_count"],
            continuity_decision=row["continuity_decision"],
            representative_evidence_ids=list(row["representative_evidence_ids"]),
        ) for row in rows],
    )


async def _decide(run_id: int, payload: TaxonomyRunDecision, request: Request, function: str) -> TaxonomyRunSummary:
    async with request.app.state.db_pool.acquire() as connection:
        try:
            row = await connection.fetchrow(
                f"SELECT * FROM {function}($1, $2, $3, $4)", run_id,
                payload.expected_updated_at, payload.operator, payload.note,
            )
        except asyncpg.PostgresError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "taxonomy_decision_conflict"},
            ) from error
        if row is None:  # pragma: no cover - functions either return or raise
            raise HTTPException(status_code=409, detail="taxonomy run changed concurrently")
        summary = await connection.fetchrow(_SUMMARY_SQL, run_id)
    return _summary(summary)


@router.post("/{run_id}/publish", response_model=TaxonomyRunSummary)
async def publish_taxonomy_run(run_id: int, payload: TaxonomyRunDecision, request: Request) -> TaxonomyRunSummary:
    await require_operator(request, mutation=True)
    if os.getenv("TAXONOMY_PUBLICATION_ENABLED", "false").strip().lower() != "true":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "taxonomy_publication_disabled"},
        )
    async with request.app.state.db_pool.acquire() as connection:
        gate = await connection.fetchrow(
            "SELECT gate_passed, failures FROM taxonomy_release_attestations WHERE taxonomy_run_id=$1",
            run_id,
        )
    if gate is None or not gate["gate_passed"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "taxonomy_publication_gate_failed",
                "failures": list(gate["failures"]) if gate is not None else ["attestation_missing"],
            },
        )
    return await _decide(run_id, payload, request, "publish_taxonomy_run")


@router.post("/{run_id}/reject", response_model=TaxonomyRunSummary)
async def reject_taxonomy_run(run_id: int, payload: TaxonomyRunDecision, request: Request) -> TaxonomyRunSummary:
    await require_operator(request, mutation=True)
    return await _decide(run_id, payload, request, "reject_taxonomy_run")


@router.post("/{run_id}/schedule", response_model=TaxonomyRunSummary, status_code=status.HTTP_202_ACCEPTED)
async def schedule_taxonomy_run(run_id: int, request: Request) -> TaxonomyRunSummary:
    """Queue an existing frozen run; creation of its snapshot remains explicit."""
    await require_operator(request, mutation=True)
    async with request.app.state.db_pool.acquire() as connection:
        try:
            await connection.fetchrow("SELECT * FROM enqueue_taxonomy_run($1)", run_id)
        except asyncpg.PostgresError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "taxonomy_schedule_conflict"},
            ) from error
        summary = await connection.fetchrow(_SUMMARY_SQL, run_id)
    return _summary(summary)

