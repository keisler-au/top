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
from triage_processor.taxonomy_experiment import hdbscan_clusters, parse_pgvector
from triage_processor.taxonomy_stages import ClaimedStage, require_stage_lease
from triage_processor.taxonomy_snapshots import compatible_representation


@dataclass(frozen=True)
class ClusterEvidence:
    evidence_id: int
    original_input_id: int
    vector: tuple[float, ...]


@dataclass(frozen=True)
class CandidateCluster:
    algorithm_label: int
    member_indexes: tuple[int, ...]
    centroid: tuple[float, ...]
    representatives: tuple[tuple[int, str], ...]


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
    result = hdbscan_clusters(
        [item.vector for item in evidence],
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
    )
    probabilities = result.membership_probabilities or tuple(
        0.0 if label == -1 else 1.0 for label in result.labels
    )
    if len(probabilities) != len(evidence) or any(
        probability < 0 or probability > 1 for probability in probabilities
    ):
        raise ValueError("clustering returned invalid membership probabilities")
    grouped: dict[int, list[int]] = defaultdict(list)
    for index, label in enumerate(result.labels):
        grouped[label].append(index)
    clusters: list[CandidateCluster] = []
    noise_indexes: list[int] = []
    for label, indexes in sorted(grouped.items()):
        # A valid persisted cluster requires at least two members.  HDBSCAN
        # normally guarantees this, but retaining the guard makes malformed
        # or substituted deterministic fixtures safe to persist as noise.
        if label == -1 or len(indexes) < 2:
            noise_indexes.extend(indexes)
            continue
        centroid = _normalise(tuple(
            sum(evidence[index].vector[axis] for index in indexes)
            for axis in range(len(evidence[indexes[0]].vector))
        ))
        ordered = sorted(indexes, key=lambda index: (-_similarity(evidence[index].vector, centroid), evidence[index].evidence_id))
        selected: list[int] = []
        originals: set[int] = set()
        for index in ordered:
            if evidence[index].original_input_id not in originals:
                selected.append(index)
                originals.add(evidence[index].original_input_id)
            if len(selected) == 3:
                break
        remaining = [index for index in indexes if evidence[index].original_input_id not in originals]
        if remaining and selected:
            selected.append(min(remaining, key=lambda index: (max(_similarity(evidence[index].vector, evidence[chosen].vector) for chosen in selected), evidence[index].evidence_id)))
        representatives = tuple((index, "central" if position < min(3, len(selected)) else "diverse") for position, index in enumerate(selected))
        clusters.append(CandidateCluster(label, tuple(indexes), centroid, representatives))
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
        SELECT evidence.id, evidence.original_input_id, embeddings.embedding::TEXT AS embedding,
               embeddings.embedding_model, embeddings.embedding_representation
        FROM taxonomy_run_evidence AS evidence
        JOIN input_embeddings AS embeddings ON embeddings.id=evidence.embedding_id
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
        evidence.append(ClusterEvidence(row["id"], row["original_input_id"], vector))
    configuration = run["configuration"]
    if isinstance(configuration, str):
        configuration = json.loads(configuration)
    if not isinstance(configuration, dict):
        raise ValueError("taxonomy run configuration is not an object")
    config = configuration.get("clustering", {})
    if not isinstance(config, dict):
        raise ValueError("taxonomy clustering configuration is not an object")
    return evidence, {"min_cluster_size": int(config.get("min_cluster_size", 3)), "min_samples": int(config.get("min_samples", 2))}


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
            INSERT INTO taxonomy_cluster_candidates(taxonomy_run_id,cluster_key,algorithm_label,member_count,centroid,diagnostics)
            VALUES($1,$2,$3,$4,$5::vector,$6::jsonb) RETURNING id
        """, run_id, f"hdbscan:{cluster.algorithm_label}", cluster.algorithm_label, len(cluster.member_indexes), _vector(cluster.centroid), json.dumps({"algorithm": "hdbscan", "metric": "euclidean", "vector_dimension": len(cluster.centroid), "representative_policy": {"central_count": 3, "diverse_count": 1}}))
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
