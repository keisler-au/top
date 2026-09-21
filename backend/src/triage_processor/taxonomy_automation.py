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


@dataclass(frozen=True)
class AutomationPolicy:
    enabled: bool = True
    poll_interval: float = 10
    minimum_evidence: int = 1
    quiet_seconds: float = 30
    version: str = "taxonomy-automation-v1"
    embedding_model: str = "nomic-embed-text"
    embedding_representation: str = "question-answer"
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
            minimum_evidence=int(os.getenv("TAXONOMY_AUTOMATION_MINIMUM_EVIDENCE", "1")),
            quiet_seconds=float(os.getenv("TAXONOMY_AUTOMATION_QUIET_SECONDS", "30")),
            version=os.getenv("TAXONOMY_AUTOMATION_POLICY_VERSION", "taxonomy-automation-v1").strip(),
            embedding_model=os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text").strip(),
            embedding_representation=os.getenv("TAXONOMY_EMBEDDING_REPRESENTATION", "question-answer").strip(),
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
        if self.poll_interval <= 0 or self.minimum_evidence < 1 or self.quiet_seconds < 0:
            raise ValueError("taxonomy automation cadence, minimum evidence, and quiet interval are invalid")
        if self.embedding_dimension < 1:
            raise ValueError("TAXONOMY_EMBEDDING_DIMENSION must be positive")
        if any(not value for value in (
            self.version, self.embedding_model, self.embedding_representation,
            self.clustering_model, self.topic_model, self.theme_model,
            self.topic_prompt_version, self.theme_prompt_version,
        )):
            raise ValueError("taxonomy automation provenance values must be non-empty")

    def snapshot_request(self, *, idempotency_key: str, after_cutoff: datetime | None) -> SnapshotRequest:
        return SnapshotRequest(
            idempotency_key=idempotency_key,
            configuration={
                "version": self.version,
                "clustering": {"algorithm": self.clustering_model},
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


_ELIGIBLE_SQL = """
WITH canonical_targets AS (
    SELECT inputs.id AS original_input_id, NULL::bigint AS segment_input_id,
           inputs.created_at AS target_created_at
    FROM original_inputs inputs
    WHERE inputs.status IN ('ready_for_analysis','completed')
      AND inputs.created_at > COALESCE($1, '-infinity'::timestamptz)
      AND NOT EXISTS (SELECT 1 FROM segment_inputs segments WHERE segments.original_input_id=inputs.id)
    UNION ALL
    SELECT inputs.id, segments.id, segments.created_at
    FROM original_inputs inputs JOIN segment_inputs segments ON segments.original_input_id=inputs.id
    WHERE inputs.status IN ('ready_for_analysis','completed')
      AND segments.created_at > COALESCE($1, '-infinity'::timestamptz)
)
SELECT count(*)::int AS evidence_count, max(GREATEST(target_created_at, embeddings.created_at)) AS evidence_cutoff
FROM canonical_targets targets
JOIN input_embeddings embeddings ON (
    (targets.segment_input_id IS NULL AND embeddings.original_input_id=targets.original_input_id)
    OR (targets.segment_input_id IS NOT NULL AND embeddings.segment_input_id=targets.segment_input_id)
)
WHERE embeddings.embedding_model=$2 AND embeddings.embedding_representation=$3
  AND vector_dims(embeddings.embedding)::int=$4
"""


async def _finish_reserved_decision(pool: asyncpg.Pool, policy: AutomationPolicy, decision: asyncpg.Record) -> AutomationResult:
    try:
        result = await create_taxonomy_snapshot(
            pool, policy.snapshot_request(
                idempotency_key=decision["idempotency_key"],
                after_cutoff=decision["predecessor_cutoff"],
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
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                """UPDATE taxonomy_automation_decisions SET status='snapshotted', taxonomy_run_id=$2
                   WHERE id=$1 AND status='reserved'""", decision["id"], result.id,
            )
            await connection.execute(
                """UPDATE taxonomy_automation_checkpoints
                   SET policy_version=$1,last_considered_cutoff=$2,last_failure_code=NULL WHERE singleton""",
                policy.version, result.source_cutoff,
            )
    return AutomationResult("created" if not result.reused else "recovered", result.id)


async def evaluate_automation(pool: asyncpg.Pool, policy: AutomationPolicy) -> AutomationResult:
    """Reserve or replay one policy decision, then use the normal snapshot path."""
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
        blocked = await connection.fetchval(
            """SELECT CASE
                  WHEN EXISTS (
                    SELECT 1 FROM taxonomy_runs run
                    JOIN taxonomy_automation_decisions decision ON decision.taxonomy_run_id=run.id
                    JOIN taxonomy_release_attestations gate ON gate.taxonomy_run_id=run.id AND NOT gate.gate_passed
                    WHERE run.status='ready_for_review' AND decision.idempotency_key LIKE 'automatic:%'
                  ) THEN 'quality_gate_failed'
                  WHEN EXISTS (
                    SELECT 1 FROM taxonomy_runs run
                    JOIN taxonomy_automation_decisions decision ON decision.taxonomy_run_id=run.id
                    WHERE run.status='failed' AND decision.idempotency_key LIKE 'automatic:%'
                  ) THEN 'candidate_failed'
                  END"""
        )
    if blocked:
        await _record_automation_block(pool, policy, blocked)
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
                "SELECT EXISTS (SELECT 1 FROM taxonomy_runs WHERE status IN ('pending','running','ready_for_review'))"
            )
            if active:
                return AutomationResult("waiting", reason="candidate_active")
            evidence = await connection.fetchrow(
                _ELIGIBLE_SQL, checkpoint["last_published_cutoff"], policy.embedding_model,
                policy.embedding_representation, policy.embedding_dimension,
            )
            if evidence["evidence_count"] < policy.minimum_evidence:
                return AutomationResult("waiting", reason="minimum_evidence")
            cutoff = evidence["evidence_cutoff"]
            quiet = await connection.fetchval(
                "SELECT CURRENT_TIMESTAMP - $1 >= ($2 * INTERVAL '1 second')", cutoff, policy.quiet_seconds
            )
            if not quiet:
                return AutomationResult("waiting", reason="debouncing")
            # Admission and snapshots must use the same canonical membership.
            # Wait for missing vectors instead of permanently poisoning a key
            # while preparation is still completing.
            snapshot_cutoff = await connection.fetchval("SELECT CURRENT_TIMESTAMP")
            rows = await connection.fetch(_CANONICAL_EVIDENCE_SQL, snapshot_cutoff, checkpoint["last_published_cutoff"])
            request = policy.snapshot_request(idempotency_key="admission", after_cutoff=checkpoint["last_published_cutoff"])
            counts = _validation_counts(rows, request)
            if counts["missing_embedding"]:
                return AutomationResult("waiting", reason="preparing_evidence")
            if any(counts[name] for name in ("model_mismatch", "representation_mismatch", "dimension_mismatch")):
                await connection.execute("UPDATE taxonomy_automation_checkpoints SET last_failure_code='snapshot_invalid' WHERE singleton")
                return AutomationResult("blocked", reason="snapshot_invalid")
            fingerprint = _source_hash(rows)
            key = f"automatic:{policy.version}:{fingerprint}"
            prior = await connection.fetchrow(
                """SELECT run.id, run.status FROM taxonomy_runs run
                   JOIN taxonomy_automation_decisions decision ON decision.taxonomy_run_id=run.id
                   WHERE run.source_snapshot_sha256=$1 AND decision.policy_version=$2
                     AND decision.idempotency_key LIKE 'automatic:%'
                   ORDER BY run.id DESC LIMIT 1""", fingerprint, policy.version,
            )
            if prior is not None and prior["status"] in {"failed", "rejected"}:
                return AutomationResult("blocked", prior["id"], "candidate_failed")
            decision = await connection.fetchrow(
                "SELECT * FROM taxonomy_automation_decisions WHERE idempotency_key=$1 FOR UPDATE", key
            )
            if decision is not None and decision["status"] == "failed":
                return AutomationResult("blocked", decision["taxonomy_run_id"], decision["failure_code"])
            if decision is not None and decision["status"] == "snapshotted":
                run_status = await connection.fetchval(
                    "SELECT status FROM taxonomy_runs WHERE id=$1", decision["taxonomy_run_id"]
                )
                # Never turn a terminal failed/rejected candidate into an
                # implicit retry.  The protected schedule endpoint is the
                # explicit recovery action for that exact frozen snapshot.
                return AutomationResult(
                    "blocked" if run_status in {"failed", "rejected"} else "recovered",
                    decision["taxonomy_run_id"],
                    "candidate_failed" if run_status == "failed" else None,
                )
            if decision is None:
                decision = await connection.fetchrow(
                    """INSERT INTO taxonomy_automation_decisions
                       (idempotency_key,policy_version,evidence_cutoff,predecessor_cutoff,status)
                       VALUES($1,$2,$3,$4,'reserved') RETURNING *""",
                    key, policy.version, cutoff, checkpoint["last_published_cutoff"],
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
