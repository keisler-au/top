"""TAX-WP2 deterministic clustering for one frozen taxonomy run."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence

import asyncpg

from triage_processor.config import DATABASE_URL
from triage_processor.taxonomy_experiment import (
    POLICY_VERSION,
    PROMPT_INPUT_MAX_BYTES,
    ClusterResult,
    EvidenceUnit,
    cluster_diagnostics,
    cluster_passes_policy,
    hdbscan_clusters,
    parse_pgvector,
    select_bounded_packet,
)
from triage_processor.taxonomy_stages import ClaimedStage, require_stage_lease
from triage_processor.taxonomy_snapshots import compatible_representation


@dataclass(frozen=True)
class ClusterEvidence:
    evidence_id: int
    original_input_id: int
    question_id: int
    question_text: str
    answer_text: str
    vector: tuple[float, ...]


@dataclass(frozen=True)
class CandidateCluster:
    question_id: int
    algorithm_label: int
    member_indexes: tuple[int, ...]
    centroid: tuple[float, ...]
    representatives: tuple[tuple[int, str], ...]
    diagnostics: dict[str, object]
    eligible: bool
    failure_reasons: tuple[str, ...]
    packet_serialized_bytes: int
    unique_original_count: int


@dataclass(frozen=True)
class ClusterPlan:
    clusters: tuple[CandidateCluster, ...]
    noise_indexes: tuple[int, ...]
    membership_probabilities: tuple[float, ...]


def _normalise(vector: Sequence[float]) -> tuple[float, ...]:
    length = math.sqrt(sum(value * value for value in vector))
    if length == 0:
        raise ValueError("zero-length embedding cannot be clustered")
    return tuple(value / length for value in vector)


def _similarity(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(_normalise(left), _normalise(right), strict=True))


def make_cluster_plan(
    evidence: Sequence[ClusterEvidence], *, min_cluster_size: int, min_samples: int
) -> ClusterPlan:
    """Pure clustering/representative selection, independently testable from DB and LLM."""
    if not evidence:
        raise ValueError("taxonomy run has no evidence")
    dimensions = {len(item.vector) for item in evidence}
    if len(dimensions) != 1 or 0 in dimensions:
        raise ValueError("taxonomy run has inconsistent vector dimensions")
    if any(not any(value != 0 for value in item.vector) for item in evidence):
        raise ValueError("taxonomy run contains a zero-length embedding")
    clusters: list[CandidateCluster] = []
    noise_indexes: list[int] = []
    probabilities = [0.0] * len(evidence)
    question_scopes: dict[int, list[int]] = defaultdict(list)
    for index, item in enumerate(evidence):
        question_scopes[item.question_id].append(index)

    for question_id, scope_indexes in sorted(question_scopes.items()):
        if len(scope_indexes) < min_cluster_size:
            noise_indexes.extend(scope_indexes)
            continue
        result = hdbscan_clusters(
            [evidence[index].vector for index in scope_indexes],
            min_cluster_size=min_cluster_size,
            min_samples=min_samples,
        )
        scope_probabilities = result.membership_probabilities or tuple(
            0.0 if label == -1 else 1.0 for label in result.labels
        )
        if len(scope_probabilities) != len(scope_indexes) or any(
            not math.isfinite(value) or value < 0 or value > 1
            for value in scope_probabilities
        ):
            raise ValueError("clustering returned invalid membership probabilities")
        for local_index, probability in enumerate(scope_probabilities):
            probabilities[scope_indexes[local_index]] = probability
        scope_diagnostics = cluster_diagnostics(
            [evidence[index].vector for index in scope_indexes],
            result.labels,
            scope_probabilities,
            [result.labels],
            result.cluster_persistence,
        )
        grouped: dict[int, list[int]] = defaultdict(list)
        for local_index, label in enumerate(result.labels):
            grouped[label].append(scope_indexes[local_index])
        for label, indexes in sorted(grouped.items()):
            if label == -1 or len(indexes) < 2:
                noise_indexes.extend(indexes)
                continue
            centroid = _normalise(tuple(
                sum(evidence[index].vector[axis] for index in indexes)
                for axis in range(len(evidence[indexes[0]].vector))
            ))
            packet_evidence = [
                EvidenceUnit(
                    evidence_id=str(item.evidence_id),
                    original_input_id=item.original_input_id,
                    segment_input_id=None,
                    answer_text=item.answer_text,
                    question_text=item.question_text,
                    created_at="",
                    vectors={"selected": list(item.vector)},
                )
                for item in evidence
            ]
            packet = select_bounded_packet(
                packet_evidence,
                [item.vector for item in evidence],
                indexes,
                maximum_bytes=PROMPT_INPUT_MAX_BYTES,
            )
            by_id = {str(item.evidence_id): index for index, item in enumerate(evidence)}
            representatives = tuple(
                (by_id[evidence_id], kind)
                for evidence_id, kind in zip(
                    packet["evidence_ids"], packet["selection_kinds"], strict=True
                )
            )
            local_metrics = dict(scope_diagnostics[label])
            geometry_ok, geometry_failures = cluster_passes_policy(local_metrics)
            failures = list(geometry_failures)
            if not packet["eligible"]:
                failures.append(str(packet["reason"]))
            diagnostics: dict[str, object] = {
                "policy_version": POLICY_VERSION,
                "algorithm": "hdbscan",
                "metric": "euclidean",
                "vector_dimension": len(centroid),
                **local_metrics,
                "packet_policy": "all<=40-or-30-central+10-diverse",
                "packet_serialized_bytes": packet["serialized_bytes"],
                "unique_original_count": packet["unique_original_count"],
            }
            clusters.append(CandidateCluster(
                question_id=question_id,
                algorithm_label=label,
                member_indexes=tuple(indexes),
                centroid=centroid,
                representatives=representatives,
                diagnostics=diagnostics,
                eligible=geometry_ok and bool(packet["eligible"]),
                failure_reasons=tuple(failures),
                packet_serialized_bytes=int(packet["serialized_bytes"]),
                unique_original_count=int(packet["unique_original_count"]),
            ))
    return ClusterPlan(
        tuple(clusters), tuple(sorted(noise_indexes)), tuple(probabilities)
    )


async def load_run_evidence(connection: asyncpg.Connection, run_id: int) -> tuple[list[ClusterEvidence], dict[str, int]]:
    run = await connection.fetchrow("""
        SELECT status, embedding_model, embedding_representation, embedding_dimension, configuration
        FROM taxonomy_runs WHERE id=$1 FOR UPDATE
    """, run_id)
    if run is None:
        raise ValueError("taxonomy run does not exist")
    if run["status"] not in {"pending", "running", "failed"}:
        raise ValueError("taxonomy run is not available for clustering")
    rows = await connection.fetch("""
        SELECT evidence.id, evidence.original_input_id, inputs.question_id,
               questions.question_text,
               COALESCE(segments.segment_text, inputs.original_text) AS answer_text,
               embeddings.embedding::TEXT AS embedding,
               embeddings.embedding_model, embeddings.embedding_representation
        FROM taxonomy_run_evidence AS evidence
        JOIN input_embeddings AS embeddings ON embeddings.id=evidence.embedding_id
        JOIN original_inputs AS inputs ON inputs.id=evidence.original_input_id
        JOIN questions ON questions.id=inputs.question_id
        LEFT JOIN segment_inputs AS segments ON segments.id=evidence.segment_input_id
        WHERE evidence.taxonomy_run_id=$1 ORDER BY evidence.id
    """, run_id)
    if not rows:
        raise ValueError("taxonomy run has no frozen evidence")
    evidence = []
    for row in rows:
        if row["embedding_model"] != run["embedding_model"] or not compatible_representation(row["embedding_representation"], run["embedding_representation"]):
            raise ValueError("run evidence embedding model or representation does not match run provenance")
        vector = tuple(parse_pgvector(row["embedding"]))
        if len(vector) != run["embedding_dimension"]:
            raise ValueError("run evidence vector dimension does not match run provenance")
        evidence.append(ClusterEvidence(
            row["id"], row["original_input_id"], row["question_id"],
            row["question_text"], row["answer_text"], vector,
        ))
    configuration = run["configuration"]
    if isinstance(configuration, str):
        configuration = json.loads(configuration)
    if not isinstance(configuration, dict):
        raise ValueError("taxonomy run configuration is not an object")
    config = configuration.get("clustering", {})
    if not isinstance(config, dict):
        raise ValueError("taxonomy clustering configuration is not an object")
    if configuration.get("cluster_policy_version") != POLICY_VERSION:
        raise ValueError("taxonomy run does not select partial-topic-policy/v1")
    return evidence, {"min_cluster_size": int(config.get("min_cluster_size", 2)), "min_samples": int(config.get("min_samples", 1))}


def _vector(value: Sequence[float]) -> str:
    return "[" + ",".join(format(item, ".17g") for item in value) + "]"


async def persist_cluster_plan(connection: asyncpg.Connection, run_id: int, evidence: Sequence[ClusterEvidence], plan: ClusterPlan) -> None:
    existing = await connection.fetchval("SELECT count(*) FROM taxonomy_cluster_memberships WHERE taxonomy_run_id=$1", run_id)
    if existing:
        # The entire plan is written in the caller's transaction.  Existing
        # rows therefore mean a prior worker committed the complete immutable
        # plan and died before completing its leased stage; a retry must be a
        # no-op rather than turn that successful work into a terminal failure.
        return
    for cluster in plan.clusters:
        cluster_id = await connection.fetchval("""
            INSERT INTO taxonomy_cluster_candidates(
                taxonomy_run_id,cluster_key,question_id,algorithm_label,
                member_count,centroid,diagnostics,policy_version,eligible,
                failure_reasons,packet_serialized_bytes,unique_original_count
            ) VALUES($1,$2,$3,$4,$5,$6::vector,$7::jsonb,$8,$9,$10,$11,$12)
            RETURNING id
        """, run_id, f"question:{cluster.question_id}:hdbscan:{cluster.algorithm_label}",
             cluster.question_id, cluster.algorithm_label, len(cluster.member_indexes),
             _vector(cluster.centroid), json.dumps(cluster.diagnostics), POLICY_VERSION,
             cluster.eligible, list(cluster.failure_reasons),
             cluster.packet_serialized_bytes, cluster.unique_original_count)
        for index in cluster.member_indexes:
            await connection.execute("""
                INSERT INTO taxonomy_cluster_memberships(taxonomy_run_id,cluster_candidate_id,evidence_id,membership_confidence,decision)
                VALUES($1,$2,$3,$4,'clustered')
            """, run_id, cluster_id, evidence[index].evidence_id, plan.membership_probabilities[index])
        for order, (index, kind) in enumerate(cluster.representatives):
            await connection.execute("""
                INSERT INTO taxonomy_cluster_representatives(taxonomy_run_id,cluster_candidate_id,evidence_id,representative_order,selection_kind)
                VALUES($1,$2,$3,$4,$5)
            """, run_id, cluster_id, evidence[index].evidence_id, order, kind)
    for index in plan.noise_indexes:
        await connection.execute("""
            INSERT INTO taxonomy_cluster_memberships(taxonomy_run_id,evidence_id,membership_confidence,decision)
            VALUES($1,$2,$3,'noise')
            """, run_id, evidence[index].evidence_id, plan.membership_probabilities[index])


async def cluster_run(pool: asyncpg.Pool, run_id: int, *, stage: ClaimedStage | None = None) -> ClusterPlan:
    async with pool.acquire() as connection:
        async with connection.transaction():
            evidence, config = await load_run_evidence(connection, run_id)
            plan = make_cluster_plan(evidence, **config)
            if stage is not None:
                await require_stage_lease(connection, stage)
            await persist_cluster_plan(connection, run_id, evidence, plan)
            return plan


async def _main(run_id: int) -> None:
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=1)
    try:
        await cluster_run(pool, run_id)
    finally:
        await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Cluster one frozen taxonomy run.")
    parser.add_argument("--run-id", type=int, required=True)
    args = parser.parse_args()
    asyncio.run(_main(args.run_id))


if __name__ == "__main__":
    main()
