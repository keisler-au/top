"""Bounded status of the newest taxonomy run for administrative readers."""

from typing import Any, Literal


CandidateStatus = Literal[
    "published", "running_candidate", "quality_blocked", "candidate_failed"
]


async def current_candidate_status(
    connection: Any, *, automatic_policy_version: str | None = None
) -> CandidateStatus | None:
    """Prefer the newest run's state over failures from superseded candidates."""
    row = await connection.fetchrow(
        """
        SELECT run.status, gate.gate_passed,
               EXISTS (SELECT 1 FROM taxonomy_run_stages stage
                       WHERE stage.taxonomy_run_id=run.id
                         AND stage.status IN ('failed','cancelled')) AS stage_failed
        FROM taxonomy_runs run
        LEFT JOIN taxonomy_automation_decisions decision ON decision.taxonomy_run_id=run.id
        LEFT JOIN taxonomy_release_attestations gate ON gate.taxonomy_run_id=run.id
        WHERE $1::text IS NULL OR (decision.policy_version=$1
              AND decision.idempotency_key LIKE 'automatic:%')
        ORDER BY run.id DESC LIMIT 1
        """, automatic_policy_version,
    )
    if row is None:
        return None
    if row["status"] == "published":
        return "published"
    if row["status"] == "superseded":
        return None
    if row["gate_passed"] is False and row["status"] in {"running", "failed", "ready_for_review"}:
        return "quality_blocked"
    if row["status"] in {"failed", "rejected"} or row["stage_failed"]:
        return "candidate_failed"
    return "running_candidate"
