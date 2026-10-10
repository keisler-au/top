"""Internal admin run reads and protected publication-gate mutations."""

import os
import json

import asyncpg
from fastapi import APIRouter, HTTPException, Request, status

from triage_processor.api.taxonomy_review_schemas import (
    TaxonomyClusterReview,
    TaxonomyTopicAntecedent,
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
from triage_processor.taxonomy_automation import reconcile_manual_snapshot

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
    await reconcile_manual_snapshot(
        request.app.state.db_pool, run_id=result.id, cutoff=result.source_cutoff,
        policy_version=os.getenv("TAXONOMY_AUTOMATION_POLICY_VERSION", "taxonomy-automation-v3"),
    )
    return TaxonomyRunCreated(
        id=result.id,
        status=result.status,
        source_cutoff=result.source_cutoff,
        evidence_count=result.evidence_count,
        embedding_dimension=result.embedding_dimension,
        queued=result.queued,
        reused=result.reused,
    )


@router.get("")
async def list_taxonomy_runs(request: Request) -> list[dict]:
    async with request.app.state.db_pool.acquire() as connection:
        rows = await connection.fetch("SELECT id,status FROM taxonomy_runs ORDER BY id DESC LIMIT 50")
    return [dict(row) for row in rows]


@router.get("/{run_id}/topics/{revision_id}/evidence")
async def review_topic_evidence(run_id: int, revision_id: int, request: Request, offset: int = 0) -> dict:
    if not 0 <= offset <= 100000:
        raise HTTPException(status_code=422, detail="invalid offset")
    async with request.app.state.db_pool.acquire() as connection:
        if not await connection.fetchval("SELECT EXISTS(SELECT 1 FROM topic_revisions WHERE taxonomy_run_id=$1 AND id=$2)",run_id,revision_id):
            raise HTTPException(status_code=404, detail="topic not found in run")
        rows = await connection.fetch("""SELECT e.id, e.original_input_id, e.segment_input_id,
            COALESCE(s.segment_text,i.original_text) AS text
            FROM topic_memberships m JOIN taxonomy_run_evidence e ON e.taxonomy_run_id=m.taxonomy_run_id AND e.id=m.evidence_id
            JOIN original_inputs i ON i.id=e.original_input_id LEFT JOIN segment_inputs s ON s.id=e.segment_input_id
            WHERE m.taxonomy_run_id=$1 AND m.topic_revision_id=$2 ORDER BY e.id LIMIT 50 OFFSET $3""",run_id,revision_id,offset)
    return {"items": [dict(row) for row in rows], "offset": offset, "page_size":50}


@router.get("/{run_id}", response_model=TaxonomyRunReview)
async def review_taxonomy_run(run_id: int, request: Request) -> TaxonomyRunReview:
    async with request.app.state.db_pool.acquire() as connection:
        async with connection.transaction(isolation='repeatable_read', readonly=True):
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
                ORDER BY revisions.name COLLATE "C", revisions.id LIMIT 101
            """, run_id)
            clusters = await connection.fetch("""
                SELECT c.id,c.question_id,c.member_count AS support_count,c.eligible,c.failure_reasons,
                       p.id AS provisional_topic_id,p.name AS provisional_name,
                       COALESCE((SELECT a.validation_errors FROM taxonomy_topic_naming_attempts a
                         WHERE a.taxonomy_run_id=c.taxonomy_run_id AND a.cluster_candidate_id=c.id
                         ORDER BY a.attempt_number DESC LIMIT 1),ARRAY[]::text[]) AS naming_errors
                FROM taxonomy_cluster_candidates c LEFT JOIN taxonomy_provisional_topics p
                  ON p.taxonomy_run_id=c.taxonomy_run_id AND p.cluster_candidate_id=c.id
                WHERE c.taxonomy_run_id=$1 ORDER BY c.id LIMIT 101
            """,run_id)
            antecedents = await connection.fetch("""
                SELECT a.topic_revision_id,a.provisional_topic_id,p.name,p.description,
                       c.question_id,c.member_count AS support_count,a.relationship,
                       a.reconciliation_decision_id
                FROM taxonomy_canonical_topic_antecedents a
                JOIN taxonomy_provisional_topics p
                  ON p.taxonomy_run_id=a.taxonomy_run_id AND p.id=a.provisional_topic_id
                JOIN taxonomy_cluster_candidates c
                  ON c.taxonomy_run_id=p.taxonomy_run_id AND c.id=p.cluster_candidate_id
                WHERE a.taxonomy_run_id=$1 AND a.topic_revision_id=ANY($2::bigint[])
                ORDER BY a.provisional_topic_id
            """,run_id,[row["id"] for row in rows[:100]])
            coverage = await connection.fetchval("SELECT taxonomy_publication_facts($1)",run_id)
            coverage = json.loads(coverage) if isinstance(coverage,str) else coverage
            gate = await connection.fetchrow("SELECT gate_passed,failures,threshold_version FROM taxonomy_release_attestations WHERE taxonomy_run_id=$1",run_id)
    base = _summary(summary)
    return TaxonomyRunReview(
        **base.model_dump(), candidate_theme_count=base.theme_count,
        topics=[TaxonomyRunTopicReview(
            id=row["id"], topic_id=row["topic_id"], name=row["name"],
            description=row["literal_description"], support_count=row["support_count"],
            continuity_decision=row["continuity_decision"],
            representative_evidence_ids=list(row["representative_evidence_ids"]),
            antecedent_provisional_topic_ids=[a["provisional_topic_id"] for a in antecedents if a["topic_revision_id"]==row["id"]],
            antecedents=[TaxonomyTopicAntecedent(
                id=a["provisional_topic_id"],name=a["name"],description=a["description"],
                question_id=a["question_id"],support_count=a["support_count"],
                relationship=a["relationship"],reconciliation_decision_id=a["reconciliation_decision_id"],
            ) for a in antecedents if a["topic_revision_id"]==row["id"]],
        ) for row in rows[:100]],
        evidence_count=coverage["evidence_count"],
        evidence_with_topic_count=coverage["evidence_with_topic_count"],
        evidence_without_topic_count=coverage["evidence_without_topic_count"],
        gate_passed=gate["gate_passed"] if gate else None,
        publication_failures=list(gate["failures"]) if gate else [],
        threshold_version=gate["threshold_version"] if gate else None,
        truncated=len(rows)>100 or len(clusters)>100,
        clusters=[TaxonomyClusterReview(
            id=c["id"],question_id=c["question_id"],support_count=c["support_count"],
            outcome="labelled" if c["provisional_topic_id"] else "unresolved",
            reasons=list(c["failure_reasons"]) + list(c["naming_errors"]),
            provisional_topic_id=c["provisional_topic_id"],provisional_name=c["provisional_name"],
        ) for c in clusters[:100]],
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
        async with connection.transaction():
            try:
                await connection.fetchrow("SELECT * FROM enqueue_taxonomy_run($1)", run_id)
            except asyncpg.PostgresError as error:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"code": "taxonomy_schedule_conflict"},
                ) from error
            await connection.execute(
                """UPDATE taxonomy_automation_decisions
                   SET status='reserved', failure_code=NULL
                   WHERE taxonomy_run_id=$1 AND status IN ('failed','snapshotted')""", run_id,
            )
            summary = await connection.fetchrow(_SUMMARY_SQL, run_id)
    return _summary(summary)
