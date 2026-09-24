"""Durable, policy-driven creation of batch-taxonomy snapshots.

This module deliberately delegates admission and queueing to
``create_taxonomy_snapshot``.  Its own database records only coordinate the
decision and make a crash replayable with the same immutable snapshot key.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os

import asyncpg

from triage_processor.taxonomy_snapshots import (
    SnapshotRequest,
    SnapshotValidationError,
    create_taxonomy_snapshot,
    _enqueue_if_possible,
    _CANONICAL_EVIDENCE_SQL,
    _source_hash,
    _validation_counts,
)

MIN_CLUSTER_SIZE = 3
MIN_SAMPLES = 2


@dataclass(frozen=True)
class AutomationPolicy:
    enabled: bool = True
    poll_interval: float = 10
    minimum_evidence: int = MIN_CLUSTER_SIZE
    quiet_seconds: float = 30
    version: str = "taxonomy-automation-v2"
    embedding_model: str = "nomic-embed-text"
    embedding_representation: str = "mixed"
    embedding_dimension: int = 768
    clustering_model: str = "hdbscan-0.8.44"
    topic_model: str = "qwen3:4b-instruct"
    theme_model: str = "qwen3:4b-instruct"
    topic_prompt_version: str = "taxonomy-topic-v1"
    theme_prompt_version: str = "taxonomy-theme-v1"

    @classmethod
    def from_env(cls) -> "AutomationPolicy":
        policy = cls(
            enabled=os.getenv("TAXONOMY_AUTOMATION_ENABLED", "true").strip().lower() == "true",
            poll_interval=float(os.getenv("TAXONOMY_POLL_INTERVAL", "10")),
            minimum_evidence=int(os.getenv("TAXONOMY_AUTOMATION_MINIMUM_EVIDENCE", "3")),
            quiet_seconds=float(os.getenv("TAXONOMY_AUTOMATION_QUIET_SECONDS", "30")),
            version=os.getenv("TAXONOMY_AUTOMATION_POLICY_VERSION", "taxonomy-automation-v2").strip(),
            embedding_model=os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text").strip(),
            embedding_representation=os.getenv("TAXONOMY_EMBEDDING_REPRESENTATION", "mixed").strip(),
            embedding_dimension=int(os.getenv("TAXONOMY_EMBEDDING_DIMENSION", "768")),
            clustering_model=os.getenv("TAXONOMY_CLUSTERING_MODEL", "hdbscan-0.8.44").strip(),
            topic_model=os.getenv("TAXONOMY_TOPIC_MODEL", os.getenv("LLM_MODEL", "qwen3:4b-instruct")).strip(),
            theme_model=os.getenv("TAXONOMY_THEME_MODEL", os.getenv("LLM_MODEL", "qwen3:4b-instruct")).strip(),
            topic_prompt_version=os.getenv("TAXONOMY_TOPIC_PROMPT_VERSION", "taxonomy-topic-v1").strip(),
            theme_prompt_version=os.getenv("TAXONOMY_THEME_PROMPT_VERSION", "taxonomy-theme-v1").strip(),
        )
        policy.validate()
        return policy

    def validate(self) -> None:
        if self.poll_interval <= 0 or self.minimum_evidence < MIN_CLUSTER_SIZE or self.quiet_seconds < 0:
            raise ValueError("taxonomy automation cadence, minimum evidence, and quiet interval are invalid")
        if self.embedding_dimension < 1:
            raise ValueError("TAXONOMY_EMBEDDING_DIMENSION must be positive")
        if any(not value for value in (
            self.version, self.embedding_model, self.embedding_representation,
            self.clustering_model, self.topic_model, self.theme_model,
            self.topic_prompt_version, self.theme_prompt_version,
        )):
            raise ValueError("taxonomy automation provenance values must be non-empty")

    def snapshot_request(
        self, *, idempotency_key: str, after_cutoff: datetime | None,
        source_cutoff: datetime | None = None,
    ) -> SnapshotRequest:
        return SnapshotRequest(
            idempotency_key=idempotency_key,
            configuration={
                "version": self.version,
                "clustering": {"algorithm": self.clustering_model, "min_cluster_size": MIN_CLUSTER_SIZE, "min_samples": MIN_SAMPLES},
                "automation_policy_version": self.version,
            },
            embedding_model=self.embedding_model,
            embedding_representation=self.embedding_representation,
            embedding_dimension=self.embedding_dimension,
            clustering_model=self.clustering_model,
            topic_model=self.topic_model,
            theme_model=self.theme_model,
            topic_prompt_version=self.topic_prompt_version,
            theme_prompt_version=self.theme_prompt_version,
            after_cutoff=after_cutoff,
            source_cutoff=source_cutoff,
        )


@dataclass(frozen=True)
class AutomationResult:
    state: str
    run_id: int | None = None
    reason: str | None = None


async def promote_automatic_candidates(pool: asyncpg.Pool, policy: AutomationPolicy) -> int:
    """Promote one or more ready automatic candidates through the DB gate.

    The database function owns the lifecycle transition, published-run swap,
    and immutable decision. Replaying this call is safe after a scheduler
    restart because an already published run is returned unchanged.
    """
    if not policy.enabled:
        return 0
    async with pool.acquire() as connection:
        candidate_ids = await connection.fetch(
            """SELECT run.id
               FROM taxonomy_runs run
               JOIN taxonomy_automation_decisions decision ON decision.taxonomy_run_id=run.id
               JOIN taxonomy_release_attestations gate ON gate.taxonomy_run_id=run.id AND gate.gate_passed
               WHERE run.status='ready_for_review'
                 AND decision.idempotency_key LIKE 'automatic:%'
                 AND decision.policy_version=$1
               ORDER BY run.id""",
            policy.version,
        )
        promoted = 0
        for row in candidate_ids:
            await connection.fetchrow(
                "SELECT * FROM publish_taxonomy_run_automatically($1,$2)", row["id"], policy.version
            )
            promoted += 1
        return promoted


async def _record_automation_block(pool: asyncpg.Pool, policy: AutomationPolicy, code: str) -> None:
    async with pool.acquire() as connection:
        await connection.execute(
            """INSERT INTO taxonomy_automation_checkpoints(singleton,policy_version,last_failure_code)
               VALUES(TRUE,$1,$2)
               ON CONFLICT (singleton) DO UPDATE
               SET policy_version=EXCLUDED.policy_version,last_failure_code=EXCLUDED.last_failure_code""",
            policy.version, code,
        )


async def record_scheduler_heartbeat(pool: asyncpg.Pool, policy: AutomationPolicy) -> None:
    """Give readers a bounded signal that scheduler polling is still alive."""
    lease_seconds = max(60.0, policy.poll_interval * 3)
    async with pool.acquire() as connection:
        await connection.execute(
            """INSERT INTO taxonomy_automation_checkpoints(
                   singleton,policy_version,last_scheduler_heartbeat_at,scheduler_heartbeat_expires_at)
               VALUES(TRUE,$1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP + ($2 * INTERVAL '1 second'))
               ON CONFLICT (singleton) DO UPDATE SET
                   policy_version=EXCLUDED.policy_version,
                   evaluation_failure_attempts=CASE WHEN taxonomy_automation_checkpoints.policy_version
                       IS DISTINCT FROM EXCLUDED.policy_version THEN 0
                       ELSE taxonomy_automation_checkpoints.evaluation_failure_attempts END,
                   evaluation_next_attempt_at=CASE WHEN taxonomy_automation_checkpoints.policy_version
                       IS DISTINCT FROM EXCLUDED.policy_version THEN NULL
                       ELSE taxonomy_automation_checkpoints.evaluation_next_attempt_at END,
                   last_failure_code=CASE WHEN taxonomy_automation_checkpoints.policy_version
                       IS DISTINCT FROM EXCLUDED.policy_version THEN NULL
                       ELSE taxonomy_automation_checkpoints.last_failure_code END,
                   last_scheduler_heartbeat_at=EXCLUDED.last_scheduler_heartbeat_at,
                   scheduler_heartbeat_expires_at=EXCLUDED.scheduler_heartbeat_expires_at""",
            policy.version, lease_seconds,
        )


async def automation_evaluation_due(pool: asyncpg.Pool) -> bool:
    async with pool.acquire() as connection:
        return bool(await connection.fetchval(
            """SELECT evaluation_failure_attempts < 3 AND
                      (evaluation_next_attempt_at IS NULL OR evaluation_next_attempt_at <= CURRENT_TIMESTAMP)
               FROM taxonomy_automation_checkpoints WHERE singleton"""
        ))


async def record_evaluation_failure(pool: asyncpg.Pool) -> int:
    """Bound non-snapshot evaluation errors; a policy version change resets them."""
    async with pool.acquire() as connection:
        return await connection.fetchval(
            """UPDATE taxonomy_automation_checkpoints
               SET evaluation_failure_attempts=evaluation_failure_attempts+1,
                   evaluation_next_attempt_at=CASE WHEN evaluation_failure_attempts+1 >= 3 THEN NULL
                       ELSE CURRENT_TIMESTAMP + (LEAST(60, 5 * POWER(2, evaluation_failure_attempts)) * INTERVAL '1 second') END,
                   last_failure_code='automation_error'
               WHERE singleton RETURNING evaluation_failure_attempts"""
        )


async def clear_evaluation_failures(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as connection:
        await connection.execute(
            """UPDATE taxonomy_automation_checkpoints
               SET evaluation_failure_attempts=0,evaluation_next_attempt_at=NULL
               WHERE singleton AND evaluation_failure_attempts <> 0"""
        )


async def _record_reserved_exception(pool: asyncpg.Pool, decision_id: int) -> AutomationResult:
    """Bound a reserved decision's failed attempts without storing error text."""
    async with pool.acquire() as connection:
        async with connection.transaction():
            attempt = await connection.fetchval(
                """UPDATE taxonomy_automation_decisions
                   SET failure_attempts=failure_attempts+1,
                       status=CASE WHEN failure_attempts+1 >= 3 THEN 'failed' ELSE 'reserved' END,
                       failure_code=CASE WHEN failure_attempts+1 >= 3 THEN 'snapshot_error' ELSE 'snapshot_retrying' END,
                       next_attempt_at=CASE WHEN failure_attempts+1 >= 3 THEN NULL
                           ELSE CURRENT_TIMESTAMP + (LEAST(60, 5 * POWER(2, failure_attempts)) * INTERVAL '1 second') END
                   WHERE id=$1 AND status='reserved' RETURNING failure_attempts""",
                decision_id,
            )
            if attempt is None:
                return AutomationResult("blocked", reason="snapshot_error")
            code = "snapshot_error" if attempt >= 3 else "snapshot_retrying"
            await connection.execute(
                "UPDATE taxonomy_automation_checkpoints SET last_failure_code=$1 WHERE singleton",
                code,
            )
    return AutomationResult("blocked" if attempt >= 3 else "waiting", reason=code)


async def _finish_reserved_decision(pool: asyncpg.Pool, policy: AutomationPolicy, decision: asyncpg.Record) -> AutomationResult:
    if decision["next_attempt_at"] is not None:
        async with pool.acquire() as connection:
            retry_due = await connection.fetchval(
                "SELECT CURRENT_TIMESTAMP >= $1", decision["next_attempt_at"]
            )
        if not retry_due:
            return AutomationResult("waiting", reason="snapshot_retrying")
    try:
        result = await create_taxonomy_snapshot(
            pool, policy.snapshot_request(
                idempotency_key=decision["idempotency_key"],
                after_cutoff=(decision["predecessor_cutoff"]
                              if decision["membership_mode"] == "post_cutoff" else None),
                source_cutoff=decision["snapshot_cutoff"],
            ),
        )
    except SnapshotValidationError:
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "UPDATE taxonomy_automation_decisions SET status='failed', failure_code='snapshot_invalid' WHERE id=$1 AND status='reserved'",
                    decision["id"],
                )
                await connection.execute(
                    "UPDATE taxonomy_automation_checkpoints SET last_failure_code='snapshot_invalid' WHERE singleton"
                )
        return AutomationResult("blocked", reason="snapshot_invalid")
    except Exception:
        return await _record_reserved_exception(pool, decision["id"])
    try:
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """UPDATE taxonomy_automation_decisions SET status='snapshotted', taxonomy_run_id=$2,
                           failure_code=NULL,next_attempt_at=NULL
                       WHERE id=$1 AND status='reserved'""", decision["id"], result.id,
                )
                await connection.execute(
                    """UPDATE taxonomy_automation_checkpoints
                       SET policy_version=$1,last_considered_cutoff=$2,last_failure_code=NULL WHERE singleton""",
                    policy.version, result.source_cutoff,
                )
    except Exception:
        return await _record_reserved_exception(pool, decision["id"])
    return AutomationResult("created" if not result.reused else "recovered", result.id)


async def evaluate_automation(pool: asyncpg.Pool, policy: AutomationPolicy) -> AutomationResult:
    """Reserve or replay one policy decision, then use the normal snapshot path."""
    policy.validate()
    if not policy.enabled:
        await _record_automation_block(pool, policy, "policy_disabled")
        return AutomationResult("disabled", reason="policy_disabled")
    # Resume the reserved identity before considering newer evidence or the
    # active-run guard: a crash may have committed its snapshot without linking
    # the decision or queueing the run.
    async with pool.acquire() as connection:
        reserved = await connection.fetchrow(
            "SELECT * FROM taxonomy_automation_decisions WHERE status='reserved' AND policy_version=$1 ORDER BY id LIMIT 1",
            policy.version,
        )
        pending = await connection.fetch(
            """SELECT run.id FROM taxonomy_runs run
               JOIN taxonomy_automation_decisions decision ON decision.taxonomy_run_id=run.id
               WHERE run.status='pending' AND decision.status='snapshotted'
               ORDER BY run.id"""
        )
    if reserved is not None:
        return await _finish_reserved_decision(pool, policy, reserved)
    for row in pending:
        await _enqueue_if_possible(pool, row["id"])
    await promote_automatic_candidates(pool, policy)
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                "INSERT INTO taxonomy_automation_checkpoints(singleton,policy_version) VALUES(TRUE,$1) ON CONFLICT DO NOTHING",
                policy.version,
            )
            checkpoint = await connection.fetchrow(
                "SELECT * FROM taxonomy_automation_checkpoints WHERE singleton FOR UPDATE"
            )
            published_cutoff = await connection.fetchval(
                "SELECT max(source_cutoff) FROM taxonomy_runs WHERE status='published'"
            )
            if published_cutoff is not None:
                await connection.execute(
                    "UPDATE taxonomy_automation_checkpoints SET last_published_cutoff=$1, policy_version=$2 WHERE singleton",
                    published_cutoff, policy.version,
                )
                checkpoint = await connection.fetchrow(
                    "SELECT * FROM taxonomy_automation_checkpoints WHERE singleton"
                )
            active = await connection.fetchval(
                "SELECT EXISTS (SELECT 1 FROM taxonomy_runs WHERE status IN ('pending','running'))"
            )
            if active:
                await connection.execute(
                    "UPDATE taxonomy_automation_checkpoints SET last_failure_code=NULL WHERE singleton"
                )
                return AutomationResult("waiting", reason="candidate_active")
            snapshot_cutoff = await connection.fetchval("SELECT CURRENT_TIMESTAMP")
            # Admission validates the same complete canonical set that will be
            # frozen. A publication cutoff can never filter replacement members.
            rows = await connection.fetch(_CANONICAL_EVIDENCE_SQL, snapshot_cutoff, None)
            request = policy.snapshot_request(idempotency_key="admission", after_cutoff=None)
            counts = _validation_counts(rows, request)
            if any(counts[name] for name in ("model_mismatch", "representation_mismatch", "dimension_mismatch")):
                await connection.execute("UPDATE taxonomy_automation_checkpoints SET last_failure_code='snapshot_invalid' WHERE singleton")
                return AutomationResult("blocked", reason="snapshot_invalid")
            if counts["missing_embedding"]:
                failed_preparation = await connection.fetchval(
                    """SELECT EXISTS (SELECT 1 FROM worker_jobs job
                       JOIN original_inputs input ON input.id=job.original_input_id
                       WHERE job.status='failed' AND input.status IN ('ready_for_analysis','completed'))"""
                )
                code = "evidence_failed" if failed_preparation else None
                await connection.execute(
                    "UPDATE taxonomy_automation_checkpoints SET last_failure_code=$1 WHERE singleton", code
                )
                return AutomationResult("blocked" if code else "waiting", reason=code or "preparing_evidence")
            if counts["canonical_evidence"] < policy.minimum_evidence:
                await connection.execute("UPDATE taxonomy_automation_checkpoints SET last_failure_code=NULL WHERE singleton")
                return AutomationResult("waiting", reason="minimum_evidence")
            cutoff = max(
                max(row["target_created_at"], row["embedding_created_at"])
                for row in rows
            )
            quiet = await connection.fetchval(
                "SELECT CURRENT_TIMESTAMP - $1 >= ($2 * INTERVAL '1 second')", cutoff, policy.quiet_seconds
            )
            if not quiet:
                await connection.execute("UPDATE taxonomy_automation_checkpoints SET last_failure_code=NULL WHERE singleton")
                return AutomationResult("waiting", reason="debouncing")
            fingerprint = _source_hash(rows)
            key = f"automatic:{policy.version}:{fingerprint}"
            decision = await connection.fetchrow(
                "SELECT * FROM taxonomy_automation_decisions WHERE idempotency_key=$1 FOR UPDATE", key
            )
            if decision is not None and decision["status"] == "failed":
                await connection.execute(
                    "UPDATE taxonomy_automation_checkpoints SET last_failure_code=$1 WHERE singleton",
                    decision["failure_code"],
                )
                return AutomationResult("blocked", decision["taxonomy_run_id"], decision["failure_code"])
            if decision is not None and decision["status"] == "snapshotted":
                run = await connection.fetchrow(
                    """SELECT run.status, gate.gate_passed FROM taxonomy_runs run
                       LEFT JOIN taxonomy_release_attestations gate ON gate.taxonomy_run_id=run.id
                       WHERE run.id=$1""", decision["taxonomy_run_id"],
                )
                code = (
                    "quality_gate_failed" if run["gate_passed"] is False else
                    "candidate_failed" if run["status"] in {"failed", "rejected"} else None
                )
                await connection.execute(
                    "UPDATE taxonomy_automation_checkpoints SET last_failure_code=$1 WHERE singleton", code
                )
                return AutomationResult(
                    "blocked" if code else "waiting",
                    decision["taxonomy_run_id"],
                    code or "unchanged_evidence",
                )
            if decision is None:
                decision = await connection.fetchrow(
                    """INSERT INTO taxonomy_automation_decisions
                       (idempotency_key,policy_version,evidence_cutoff,predecessor_cutoff,
                        membership_mode,snapshot_cutoff,status)
                       VALUES($1,$2,$3,$4,'cumulative',$5,'reserved') RETURNING *""",
                    key, policy.version, cutoff, checkpoint["last_published_cutoff"], snapshot_cutoff,
                )
    return await _finish_reserved_decision(pool, policy, decision)


async def reconcile_manual_snapshot(pool: asyncpg.Pool, *, run_id: int, cutoff: datetime, policy_version: str) -> None:
    """Make an explicit snapshot visible to automation without changing it."""
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                "INSERT INTO taxonomy_automation_checkpoints(singleton,policy_version,last_considered_cutoff) VALUES(TRUE,$1,$2) ON CONFLICT (singleton) DO UPDATE SET policy_version=EXCLUDED.policy_version,last_considered_cutoff=GREATEST(taxonomy_automation_checkpoints.last_considered_cutoff,EXCLUDED.last_considered_cutoff)",
                policy_version, cutoff,
            )
            await connection.execute(
                """INSERT INTO taxonomy_automation_decisions
                   (idempotency_key,policy_version,evidence_cutoff,status,taxonomy_run_id)
                   VALUES($1,$2,$3,'manual',$4) ON CONFLICT (idempotency_key) DO NOTHING""",
                f"manual:{run_id}", policy_version, cutoff, run_id,
            )
