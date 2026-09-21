"""Leased, durable lifecycle operations for batch-taxonomy run stages."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

import asyncpg


STAGES = (
    "snapshot",
    "clustering",
    "topic_naming",
    "theme_inference",
    "theme_reconciliation",
    "quality",
    "ready_for_publication",
)

MAX_AUDIT_JSON_BYTES = 32_768


def _utf8_prefix(value: str, maximum_bytes: int) -> str:
    """Return the longest character prefix that fits in a UTF-8 byte budget."""
    encoded = value.encode("utf-8")
    if len(encoded) <= maximum_bytes:
        return value
    return encoded[:maximum_bytes].decode("utf-8", errors="ignore")


def bounded_audit_object(value: dict[str, object], *, max_bytes: int = MAX_AUDIT_JSON_BYTES) -> dict[str, object]:
    """Make a JSON audit object safe to retain without accepting unbounded LLM data.

    Normal responses retain their full structured value.  Oversized responses
    are replaced with bounded metadata and a deterministic preview, preserving
    enough information to correlate an attempt without retaining arbitrary
    model output in PostgreSQL.
    """
    if max_bytes < 256:
        raise ValueError("audit payload byte limit must be at least 256")
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    digest = sha256(encoded).hexdigest()
    metadata = {
        "_audit_truncated": True,
        "original_bytes": len(encoded),
        "original_sha256": digest,
    }
    # Reserve enough room for the metadata and JSON punctuation; calculate the
    # actual JSON size again below to handle non-ASCII preview characters.
    preview_budget = max_bytes - len(json.dumps(metadata, separators=(",", ":")).encode("utf-8")) - 32
    preview = _utf8_prefix(encoded.decode("utf-8", errors="replace"), max(0, preview_budget))
    bounded = {**metadata, "preview": preview}
    while len(json.dumps(bounded, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > max_bytes:
        preview = _utf8_prefix(preview, max(0, len(preview.encode("utf-8")) - 1))
        bounded["preview"] = preview
    return bounded


@dataclass(frozen=True)
class ClaimedStage:
    id: int
    run_id: int
    stage: str
    attempt: int
    lease_owner: str


async def record_model_request(
    pool: asyncpg.Pool,
    *,
    run_id: int,
    stage: str,
    request_key: str,
    model: str,
    prompt_version: str,
    prompt_sha256: str,
    request_context: dict[str, object],
    claimed_stage: ClaimedStage | None = None,
) -> int:
    """Durably allocate the idempotency identity for one model call.

    Scheduler callers supply ``claimed_stage`` so a worker which has lost a
    lease cannot leave even an audit row behind.  The optional claim keeps the
    low-level helper usable by one-off migration/audit tooling; production
    stage handlers always provide it.
    """
    bounded_context = bounded_audit_object(request_context)
    serialized = json.dumps(
        bounded_context, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    request_hash = sha256(serialized.encode("utf-8")).hexdigest()
    async with pool.acquire() as connection:
        async with connection.transaction():
            if claimed_stage is not None:
                if claimed_stage.run_id != run_id or claimed_stage.stage != stage:
                    raise ValueError("claimed stage does not match model request")
                await require_stage_lease(connection, claimed_stage)
            identifier = await connection.fetchval(
                """
                INSERT INTO taxonomy_model_requests(
                    taxonomy_run_id, stage, request_key, model, prompt_version,
                    prompt_sha256, request_context, request_sha256
                ) VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8)
                ON CONFLICT (taxonomy_run_id, stage, request_key) DO NOTHING
                RETURNING id
                """,
                run_id, stage, request_key,
                model, prompt_version, prompt_sha256, serialized, request_hash,
            )
            if identifier is None:
                # Use a new statement after the conflict wait.  This avoids
                # the statement-snapshot race where a concurrent winner is
                # not yet visible to a combined INSERT/SELECT query.
                identifier = await connection.fetchval(
                    """
                    SELECT id FROM taxonomy_model_requests
                    WHERE taxonomy_run_id = $1 AND stage = $2 AND request_key = $3
                    """,
                    run_id, stage, request_key,
                )
    if identifier is None:
        raise RuntimeError("could not allocate taxonomy model request identity")
    return identifier


async def record_model_response(
    connection: asyncpg.Connection,
    *,
    run_id: int,
    request_id: int,
    raw_response: dict[str, object],
    validation_errors: tuple[str, ...],
    accepted: bool,
) -> bool:
    """Append a model result exactly once; the winner owns candidate writes."""
    identifier = await connection.fetchval(
        """
        INSERT INTO taxonomy_model_responses(
            taxonomy_run_id, taxonomy_model_request_id, raw_response,
            validation_errors, accepted
        ) VALUES ($1,$2,$3::jsonb,$4,$5)
        ON CONFLICT (taxonomy_model_request_id) DO NOTHING
        RETURNING id
        """,
        run_id, request_id, json.dumps(bounded_audit_object(raw_response)),
        list(validation_errors), accepted,
    )
    return identifier is not None


async def record_model_failure(
    pool: asyncpg.Pool,
    *,
    run_id: int,
    request_id: int,
    error: BaseException,
    stage: ClaimedStage | None = None,
) -> None:
    """Append a bounded failed model-call outcome before the stage is retried."""
    async with pool.acquire() as connection:
        async with connection.transaction():
            if stage is not None:
                await require_stage_lease(connection, stage)
            await record_model_response(
                connection,
                run_id=run_id,
                request_id=request_id,
                raw_response={"error_class": bounded_error_class(error)},
                validation_errors=("model_call_failed",),
                accepted=False,
            )


def bounded_error_class(error: BaseException) -> str:
    """Return a stable, non-sensitive failure category suitable for persistence."""
    name = type(error).__name__.lower()
    normalized = "".join(character if character.isalnum() else "_" for character in name)
    normalized = normalized.strip("_") or "unknown_error"
    if not normalized[0].isalpha():
        normalized = f"error_{normalized}"
    return normalized[:80]


def retry_delay_seconds(attempt: int, *, base_seconds: float, max_seconds: float) -> float:
    if attempt < 1:
        raise ValueError("stage attempt must be positive")
    if base_seconds <= 0 or max_seconds < base_seconds:
        raise ValueError("invalid taxonomy stage retry settings")
    return min(base_seconds * (2 ** (attempt - 1)), max_seconds)


async def claim_next_stage(
    pool: asyncpg.Pool,
    *,
    lease_owner: str,
    lease_seconds: float,
    allowed_stages: tuple[str, ...] = STAGES[1:],
) -> ClaimedStage | None:
    """Atomically claim exactly one ready stage whose predecessor completed."""
    if (
        not lease_owner.strip()
        or lease_seconds <= 0
        or not allowed_stages
        or any(stage not in STAGES or stage == "snapshot" for stage in allowed_stages)
    ):
        raise ValueError("lease owner and lease duration must be positive")
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            WITH next_stage AS (
                SELECT candidate.id
                FROM taxonomy_run_stages AS candidate
                JOIN taxonomy_runs AS run ON run.id = candidate.taxonomy_run_id
                JOIN taxonomy_run_jobs AS job ON job.taxonomy_run_id = candidate.taxonomy_run_id
                WHERE run.status IN ('pending', 'running', 'failed')
                  AND job.status IN ('pending', 'processing')
                  AND candidate.stage <> 'snapshot'
                  AND candidate.stage = ANY($4::text[])
                  AND (
                    (candidate.status = 'pending' AND candidate.available_at <= CURRENT_TIMESTAMP)
                    OR (candidate.status = 'running' AND candidate.lease_expires_at < CURRENT_TIMESTAMP)
                  )
                  AND NOT EXISTS (
                    SELECT 1
                    FROM taxonomy_run_stages AS predecessor
                    WHERE predecessor.taxonomy_run_id = candidate.taxonomy_run_id
                      AND array_position($1::text[], predecessor.stage)
                          < array_position($1::text[], candidate.stage)
                      AND predecessor.status <> 'completed'
                  )
                ORDER BY candidate.available_at, candidate.taxonomy_run_id, candidate.id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE taxonomy_run_stages AS stages
            SET status = 'running',
                attempt = stages.attempt + 1,
                lease_owner = $2,
                lease_expires_at = CURRENT_TIMESTAMP + ($3 * INTERVAL '1 second'),
                heartbeat_at = CURRENT_TIMESTAMP,
                started_at = COALESCE(stages.started_at, CURRENT_TIMESTAMP),
                error_class = NULL,
                updated_at = CURRENT_TIMESTAMP
            FROM next_stage
            WHERE stages.id = next_stage.id
            RETURNING stages.id, stages.taxonomy_run_id, stages.stage,
                      stages.attempt, stages.lease_owner
            """,
            list(STAGES),
            lease_owner,
            lease_seconds,
            list(allowed_stages),
        )
    if row is None:
        return None
    return ClaimedStage(
        id=row["id"], run_id=row["taxonomy_run_id"], stage=row["stage"],
        attempt=row["attempt"], lease_owner=row["lease_owner"],
    )


async def renew_stage(
    pool: asyncpg.Pool, stage: ClaimedStage, *, lease_seconds: float
) -> bool:
    if lease_seconds <= 0:
        raise ValueError("lease duration must be positive")
    async with pool.acquire() as connection:
        identifier = await connection.fetchval(
            """
            UPDATE taxonomy_run_stages
            SET lease_expires_at = CURRENT_TIMESTAMP + ($3 * INTERVAL '1 second'),
                heartbeat_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = $1 AND status = 'running' AND lease_owner = $2
              AND lease_expires_at >= CURRENT_TIMESTAMP AND attempt = $4
            RETURNING id
            """,
            stage.id, stage.lease_owner, lease_seconds, stage.attempt,
        )
    return identifier is not None


async def require_stage_lease(connection: asyncpg.Connection, stage: ClaimedStage) -> None:
    """Refuse candidate writes after a worker has lost its stage lease."""
    owned = await connection.fetchval(
        """
        SELECT id FROM taxonomy_run_stages
            WHERE id = $1 AND taxonomy_run_id = $2 AND status = 'running'
              AND lease_owner = $3 AND lease_expires_at >= CURRENT_TIMESTAMP
              AND attempt = $4
        FOR UPDATE
        """,
        stage.id, stage.run_id, stage.lease_owner, stage.attempt,
    )
    if not owned:
        raise RuntimeError("taxonomy stage lease is no longer owned")


async def complete_stage(
    pool: asyncpg.Pool, stage: ClaimedStage, *, output_material: str
) -> bool:
    """Complete only the current lease owner; output identity is immutable."""
    output_hash = sha256(output_material.encode("utf-8")).hexdigest()
    async with pool.acquire() as connection:
        identifier = await connection.fetchval(
            """
            UPDATE taxonomy_run_stages
            SET status = 'completed', lease_owner = NULL, lease_expires_at = NULL,
                heartbeat_at = NULL, completed_at = CURRENT_TIMESTAMP,
                stage_output_sha256 = $3, updated_at = CURRENT_TIMESTAMP
            WHERE id = $1 AND status = 'running' AND lease_owner = $2
              AND lease_expires_at >= CURRENT_TIMESTAMP AND attempt = $4
            RETURNING id
            """,
            stage.id, stage.lease_owner, output_hash, stage.attempt,
        )
    return identifier is not None


async def complete_ready_for_review_stage(
    pool: asyncpg.Pool, stage: ClaimedStage, *, output_material: str
) -> bool:
    """Atomically finish readiness, mark the candidate reviewable, and free its queue slot."""
    if stage.stage != "ready_for_publication":
        raise ValueError("only the readiness stage can complete a taxonomy run")
    output_hash = sha256(output_material.encode("utf-8")).hexdigest()
    async with pool.acquire() as connection:
        async with connection.transaction():
            has_quality = await connection.fetchval(
                "SELECT EXISTS (SELECT 1 FROM taxonomy_release_attestations WHERE taxonomy_run_id=$1)",
                stage.run_id,
            )
            if not has_quality:
                raise ValueError("taxonomy run has no computed release attestation")
            identifier = await connection.fetchval(
                """
                UPDATE taxonomy_run_stages
                SET status = 'completed', lease_owner = NULL, lease_expires_at = NULL,
                    heartbeat_at = NULL, completed_at = CURRENT_TIMESTAMP,
                    stage_output_sha256 = $3, updated_at = CURRENT_TIMESTAMP
                WHERE id = $1 AND taxonomy_run_id = $4 AND stage = 'ready_for_publication'
                  AND status = 'running' AND lease_owner = $2
                  AND lease_expires_at >= CURRENT_TIMESTAMP AND attempt = $5
                RETURNING id
                """,
                stage.id, stage.lease_owner, output_hash, stage.run_id, stage.attempt,
            )
            if identifier is None:
                return False
            await connection.execute(
                """
                UPDATE taxonomy_runs
                SET status = 'ready_for_review', completed_at = CURRENT_TIMESTAMP
                WHERE id = $1 AND status = 'running'
                """, stage.run_id,
            )
            await connection.execute(
                """
                UPDATE taxonomy_run_jobs
                SET status = 'completed', locked_at = NULL, locked_by = NULL,
                    completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE taxonomy_run_id = $1 AND status IN ('pending', 'processing')
                """, stage.run_id,
            )
    return True


async def fail_stage(
    pool: asyncpg.Pool,
    stage: ClaimedStage,
    error: BaseException,
    *,
    max_attempts: int,
    retry_base_seconds: float,
    retry_max_seconds: float,
) -> str | None:
    """Release a failed lease, retrying with bounded exponential backoff."""
    if max_attempts < 1:
        raise ValueError("max attempts must be at least one")
    terminal = stage.attempt >= max_attempts
    next_status = "failed" if terminal else "pending"
    delay = retry_delay_seconds(
        stage.attempt, base_seconds=retry_base_seconds, max_seconds=retry_max_seconds
    )
    async with pool.acquire() as connection:
        async with connection.transaction():
            result = await connection.fetchval(
                """
                UPDATE taxonomy_run_stages
                SET status = $3, lease_owner = NULL, lease_expires_at = NULL,
                    heartbeat_at = NULL,
                    error_class = CASE WHEN $3 = 'failed' THEN $4 ELSE NULL END,
                    available_at = CASE WHEN $3 = 'pending' THEN
                        CURRENT_TIMESTAMP + ($5 * INTERVAL '1 second')
                        ELSE available_at END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1 AND status = 'running' AND lease_owner = $2
                  AND lease_expires_at >= CURRENT_TIMESTAMP AND attempt = $6
                RETURNING status
                """,
                stage.id, stage.lease_owner, next_status, bounded_error_class(error), delay, stage.attempt,
            )
            if result == "failed":
                await _finish_failed_run(connection, stage.run_id, bounded_error_class(error))
            return result


async def _finish_failed_run(connection: asyncpg.Connection, run_id: int, code: str, *, cancelled: bool = False) -> None:
    await connection.execute(
        "UPDATE taxonomy_runs SET status='failed', error_summary=$2 WHERE id=$1 AND status IN ('pending','running','failed')",
        run_id, code,
    )
    await connection.execute(
        """UPDATE taxonomy_run_jobs SET status=$2, locked_at=NULL, locked_by=NULL,
               last_error=$3, updated_at=CURRENT_TIMESTAMP
           WHERE taxonomy_run_id=$1 AND status IN ('pending','processing','failed')""",
        run_id, "cancelled" if cancelled else "failed", code,
    )


async def retry_stage(pool: asyncpg.Pool, stage_id: int) -> bool:
    """Explicitly retry a failed stage and reacquire its run's queue slot."""
    async with pool.acquire() as connection:
        async with connection.transaction():
            run_id = await connection.fetchval(
                "SELECT taxonomy_run_id FROM taxonomy_run_stages WHERE id=$1 AND status = 'failed' FOR UPDATE",
                stage_id,
            )
            if run_id is None:
                return False
            await connection.fetchrow("SELECT * FROM enqueue_taxonomy_run($1)", run_id)
    return True


async def cancel_stage(pool: asyncpg.Pool, stage_id: int) -> bool:
    """Cancel the candidate's remaining work and release its singleton slot."""
    async with pool.acquire() as connection:
        async with connection.transaction():
            run_id = await connection.fetchval(
                """UPDATE taxonomy_run_stages
                   SET status='cancelled', lease_owner=NULL, lease_expires_at=NULL,
                       heartbeat_at=NULL, error_class=NULL, updated_at=CURRENT_TIMESTAMP
                   WHERE id=$1 AND status IN ('pending', 'running', 'failed')
                   RETURNING taxonomy_run_id""", stage_id,
            )
            if run_id is None:
                return False
            await _finish_failed_run(connection, run_id, "candidate_cancelled", cancelled=True)
    return True
