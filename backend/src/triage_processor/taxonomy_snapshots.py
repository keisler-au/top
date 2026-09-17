"""Atomic creation of immutable, canonical batch-taxonomy snapshots."""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from typing import Any, Mapping

import asyncpg

from triage_processor.config import DATABASE_URL


@dataclass(frozen=True)
class SnapshotRequest:
    idempotency_key: str
    configuration: Mapping[str, Any]
    embedding_model: str
    embedding_representation: str
    embedding_dimension: int
    clustering_model: str
    topic_model: str
    theme_model: str
    topic_prompt_version: str
    theme_prompt_version: str


@dataclass(frozen=True)
class SnapshotResult:
    id: int
    status: str
    source_cutoff: datetime
    evidence_count: int
    embedding_dimension: int
    queued: bool
    reused: bool


class SnapshotValidationError(ValueError):
    """A source snapshot cannot be created; its detail contains counts only."""

    def __init__(self, counts: Mapping[str, int]) -> None:
        self.counts = dict(counts)
        super().__init__("taxonomy snapshot validation failed")


class IdempotencyConflictError(ValueError):
    """The same key was reused for a different immutable snapshot request."""


# The cutoff is supplied by PostgreSQL inside the snapshot transaction. The
# left joins deliberately constrain embeddings to the same cutoff: a vector
# created later cannot be silently admitted to an earlier source snapshot.
_CANONICAL_EVIDENCE_SQL = """
WITH canonical_targets AS (
    SELECT
        inputs.id AS original_input_id,
        NULL::bigint AS segment_input_id
    FROM original_inputs AS inputs
    WHERE inputs.status = 'completed'
      AND inputs.created_at <= $1
      AND NOT EXISTS (
          SELECT 1
          FROM segment_inputs AS segments
          WHERE segments.original_input_id = inputs.id
            AND segments.created_at <= $1
      )

    UNION ALL

    SELECT
        inputs.id AS original_input_id,
        segments.id AS segment_input_id
    FROM original_inputs AS inputs
    JOIN segment_inputs AS segments
      ON segments.original_input_id = inputs.id
     AND segments.created_at <= $1
    WHERE inputs.status = 'completed'
      AND inputs.created_at <= $1
)
SELECT
    targets.original_input_id,
    targets.segment_input_id,
    embeddings.id AS embedding_id,
    embeddings.embedding_model,
    embeddings.embedding_representation,
    vector_dims(embeddings.embedding)::integer AS embedding_dimension
FROM canonical_targets AS targets
LEFT JOIN input_embeddings AS embeddings
  ON embeddings.created_at <= $1
 AND (
     (targets.segment_input_id IS NULL
      AND embeddings.original_input_id = targets.original_input_id)
     OR
     (targets.segment_input_id IS NOT NULL
      AND embeddings.segment_input_id = targets.segment_input_id)
 )
ORDER BY targets.original_input_id, targets.segment_input_id NULLS FIRST
"""


_IDEMPOTENCY_SQL = """
SELECT
    id, status, source_cutoff, snapshot_evidence_count, embedding_dimension,
    configuration, embedding_model, embedding_representation, clustering_model,
    topic_model, theme_model, topic_prompt_version, theme_prompt_version
FROM taxonomy_runs
WHERE idempotency_key = $1
"""


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def validate_snapshot_request(request: SnapshotRequest) -> None:
    string_fields = (
        request.idempotency_key,
        request.embedding_model,
        request.embedding_representation,
        request.clustering_model,
        request.topic_model,
        request.theme_model,
        request.topic_prompt_version,
        request.theme_prompt_version,
    )
    if any(not isinstance(value, str) or not value.strip() for value in string_fields):
        raise ValueError("taxonomy snapshot provenance fields must be non-blank strings")
    if request.embedding_dimension <= 0:
        raise ValueError("embedding_dimension must be positive")
    if not isinstance(request.configuration, Mapping):
        raise ValueError("configuration must be an object")
    version = request.configuration.get("version")
    clustering = request.configuration.get("clustering")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("configuration.version must be a non-blank string")
    if not isinstance(clustering, Mapping):
        raise ValueError("configuration.clustering must be an object")


def _same_request(row: asyncpg.Record, request: SnapshotRequest) -> bool:
    configuration = row["configuration"]
    if isinstance(configuration, str):
        configuration = json.loads(configuration)
    return (
        _canonical_json(configuration) == _canonical_json(request.configuration)
        and row["embedding_model"] == request.embedding_model
        and row["embedding_representation"] == request.embedding_representation
        and row["clustering_model"] == request.clustering_model
        and row["topic_model"] == request.topic_model
        and row["theme_model"] == request.theme_model
        and row["topic_prompt_version"] == request.topic_prompt_version
        and row["theme_prompt_version"] == request.theme_prompt_version
        and row["embedding_dimension"] == request.embedding_dimension
    )


def _result_from_row(row: asyncpg.Record, *, queued: bool, reused: bool) -> SnapshotResult:
    evidence_count = row["snapshot_evidence_count"]
    dimension = row["embedding_dimension"]
    if evidence_count is None or dimension is None:
        raise IdempotencyConflictError("idempotency key belongs to a non-snapshot taxonomy run")
    return SnapshotResult(
        id=row["id"],
        status=row["status"],
        source_cutoff=row["source_cutoff"],
        evidence_count=evidence_count,
        embedding_dimension=dimension,
        queued=queued,
        reused=reused,
    )


def _validation_counts(rows: list[asyncpg.Record], request: SnapshotRequest) -> dict[str, int]:
    canonical_targets = [
        (row["original_input_id"], row["segment_input_id"])
        for row in rows
    ]
    embedding_ids = [row["embedding_id"] for row in rows if row["embedding_id"] is not None]
    counts = {
        "canonical_evidence": len(rows),
        "zero_evidence": int(not rows),
        "missing_embedding": sum(row["embedding_id"] is None for row in rows),
        "model_mismatch": sum(
            row["embedding_id"] is not None
            and row["embedding_model"] != request.embedding_model
            for row in rows
        ),
        "representation_mismatch": sum(
            row["embedding_id"] is not None
            and row["embedding_representation"] != request.embedding_representation
            for row in rows
        ),
        "dimension_mismatch": sum(
            row["embedding_id"] is not None
            and row["embedding_dimension"] != request.embedding_dimension
            for row in rows
        ),
        "duplicate_canonical_target": sum(
            amount - 1 for amount in Counter(canonical_targets).values() if amount > 1
        ),
        "duplicate_embedding": sum(
            amount - 1 for amount in Counter(embedding_ids).values() if amount > 1
        ),
    }
    return counts


def _source_hash(rows: list[asyncpg.Record]) -> str:
    # Hash stable identifiers and vector provenance, never raw source text.
    material = "\n".join(
        ":".join(
            str(value)
            for value in (
                row["original_input_id"],
                row["segment_input_id"] if row["segment_input_id"] is not None else "original",
                row["embedding_id"],
                row["embedding_model"],
                row["embedding_representation"],
                row["embedding_dimension"],
            )
        )
        for row in rows
    )
    return _sha256(material)


def _stage_input_hash(source_hash: str, configuration_hash: str, stage: str) -> str:
    """Bind each stage to the immutable source and configuration it consumes."""
    return _sha256(f"{stage}:{source_hash}:{configuration_hash}")


async def _enqueue_if_possible(pool: asyncpg.Pool, run_id: int) -> bool:
    """Queue after snapshot commit; an active global run leaves this pending."""
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            "SELECT status FROM taxonomy_runs WHERE id = $1", run_id
        )
        if row is None or row["status"] not in {"pending", "failed"}:
            return False
        active = await connection.fetchval(
            "SELECT EXISTS (SELECT 1 FROM taxonomy_run_jobs WHERE status IN ('pending', 'processing'))"
        )
        if active:
            return False
        try:
            await connection.fetchrow("SELECT * FROM enqueue_taxonomy_run($1)", run_id)
        except asyncpg.PostgresError:
            # A concurrent scheduler may have claimed the only active slot.
            own_job = await connection.fetchval(
                "SELECT EXISTS (SELECT 1 FROM taxonomy_run_jobs WHERE taxonomy_run_id = $1)",
                run_id,
            )
            if not own_job:
                active = await connection.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM taxonomy_run_jobs WHERE status IN ('pending', 'processing'))"
                )
                if active:
                    return False
                raise
        return True


async def create_taxonomy_snapshot(
    pool: asyncpg.Pool, request: SnapshotRequest
) -> SnapshotResult:
    """Create one immutable run snapshot and queue it only after commit."""
    validate_snapshot_request(request)
    created = False
    async with pool.acquire() as connection:
        async with connection.transaction():
            existing = await connection.fetchrow(_IDEMPOTENCY_SQL, request.idempotency_key)
            if existing is not None:
                if not _same_request(existing, request):
                    raise IdempotencyConflictError(
                        "idempotency key was already used for different taxonomy provenance"
                    )
                result = _result_from_row(existing, queued=False, reused=True)
            else:
                cutoff = await connection.fetchval("SELECT CURRENT_TIMESTAMP")
                evidence = await connection.fetch(_CANONICAL_EVIDENCE_SQL, cutoff)
                counts = _validation_counts(evidence, request)
                if any(
                    counts[key]
                    for key in (
                        "zero_evidence",
                        "missing_embedding",
                        "model_mismatch",
                        "representation_mismatch",
                        "dimension_mismatch",
                        "duplicate_canonical_target",
                        "duplicate_embedding",
                    )
                ):
                    raise SnapshotValidationError(counts)

                row = await connection.fetchrow(
                    """
                    INSERT INTO taxonomy_runs (
                        source_cutoff, source_snapshot_sha256, configuration,
                        configuration_sha256, embedding_model,
                        embedding_representation, clustering_model, topic_model,
                        theme_model, topic_prompt_version, theme_prompt_version,
                        idempotency_key, snapshot_evidence_count,
                        embedding_dimension
                    ) VALUES (
                        $1, $2, $3::jsonb, $4, $5, $6, $7, $8, $9, $10, $11,
                        $12, $13, $14
                    )
                    ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL
                    DO NOTHING
                    RETURNING id, status, source_cutoff, snapshot_evidence_count,
                              embedding_dimension, configuration, embedding_model,
                              embedding_representation, clustering_model,
                              topic_model, theme_model, topic_prompt_version,
                              theme_prompt_version
                    """,
                    cutoff,
                    _source_hash(evidence),
                    _canonical_json(request.configuration),
                    _sha256(_canonical_json(request.configuration)),
                    request.embedding_model,
                    request.embedding_representation,
                    request.clustering_model,
                    request.topic_model,
                    request.theme_model,
                    request.topic_prompt_version,
                    request.theme_prompt_version,
                    request.idempotency_key,
                    len(evidence),
                    request.embedding_dimension,
                )
                if row is None:
                    existing = await connection.fetchrow(
                        _IDEMPOTENCY_SQL, request.idempotency_key
                    )
                    if existing is None or not _same_request(existing, request):
                        raise IdempotencyConflictError(
                            "idempotency key was already used for different taxonomy provenance"
                        )
                    result = _result_from_row(existing, queued=False, reused=True)
                else:
                    await connection.executemany(
                        """
                        INSERT INTO taxonomy_run_evidence (
                            taxonomy_run_id, original_input_id, segment_input_id,
                            embedding_id
                        ) VALUES ($1, $2, $3, $4)
                        """,
                        [
                            (
                                row["id"],
                                evidence_row["original_input_id"],
                                evidence_row["segment_input_id"],
                                evidence_row["embedding_id"],
                            )
                            for evidence_row in evidence
                        ],
                    )
                    configuration_hash = _sha256(_canonical_json(request.configuration))
                    stage_rows = [
                        (
                            row["id"], stage, 1 if stage == "snapshot" else 0,
                            "completed" if stage == "snapshot" else "pending",
                            _stage_input_hash(
                                _source_hash(evidence), configuration_hash, stage
                            ),
                            _source_hash(evidence) if stage == "snapshot" else None,
                        )
                        for stage in (
                            "snapshot", "clustering", "topic_naming", "theme_inference",
                            "theme_reconciliation", "quality", "ready_for_publication",
                        )
                    ]
                    await connection.executemany(
                        """
                        INSERT INTO taxonomy_run_stages (
                            taxonomy_run_id, stage, attempt, status,
                            completed_at, stage_input_sha256, stage_output_sha256
                        ) VALUES (
                            $1, $2, $3, $4,
                            CASE WHEN $4 = 'completed' THEN CURRENT_TIMESTAMP ELSE NULL END,
                            $5, $6
                        )
                        """,
                        stage_rows,
                    )
                    result = _result_from_row(row, queued=False, reused=False)
                    created = True

    queued = await _enqueue_if_possible(pool, result.id)
    return SnapshotResult(
        id=result.id,
        status=result.status,
        source_cutoff=result.source_cutoff,
        evidence_count=result.evidence_count,
        embedding_dimension=result.embedding_dimension,
        queued=queued,
        reused=not created,
    )


def _request_from_args(args: argparse.Namespace) -> SnapshotRequest:
    try:
        configuration = json.loads(args.configuration)
    except json.JSONDecodeError as error:
        raise ValueError("--configuration must be a JSON object") from error
    if not isinstance(configuration, dict):
        raise ValueError("--configuration must be a JSON object")
    return SnapshotRequest(
        idempotency_key=args.idempotency_key,
        configuration=configuration,
        embedding_model=args.embedding_model,
        embedding_representation=args.embedding_representation,
        embedding_dimension=args.embedding_dimension,
        clustering_model=args.clustering_model,
        topic_model=args.topic_model,
        theme_model=args.theme_model,
        topic_prompt_version=args.topic_prompt_version,
        theme_prompt_version=args.theme_prompt_version,
    )


async def _main(args: argparse.Namespace) -> None:
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2)
    try:
        result = await create_taxonomy_snapshot(pool, _request_from_args(args))
    finally:
        await pool.close()
    print(json.dumps({
        "id": result.id,
        "status": result.status,
        "source_cutoff": result.source_cutoff.isoformat(),
        "evidence_count": result.evidence_count,
        "embedding_dimension": result.embedding_dimension,
        "queued": result.queued,
        "reused": result.reused,
    }, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description="Create and queue a batch-taxonomy snapshot.")
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument("--configuration", required=True, help="Versioned JSON configuration object")
    parser.add_argument("--embedding-model", required=True)
    parser.add_argument("--embedding-representation", required=True)
    parser.add_argument("--embedding-dimension", required=True, type=int)
    parser.add_argument("--clustering-model", required=True)
    parser.add_argument("--topic-model", required=True)
    parser.add_argument("--theme-model", required=True)
    parser.add_argument("--topic-prompt-version", required=True)
    parser.add_argument("--theme-prompt-version", required=True)
    asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    main()
