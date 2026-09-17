"""Durable, server-computed candidate quality facts for a taxonomy run."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json

import asyncpg

from triage_processor.taxonomy_stages import ClaimedStage, require_stage_lease


@dataclass(frozen=True)
class QualityFacts:
    evidence_count: int
    clustered_count: int
    noise_count: int
    naming_attempt_count: int
    accepted_topic_count: int
    candidate_theme_count: int
    reconciled_theme_count: int
    duplicate_topic_count: int = 0

    def signals(self) -> dict[str, int | float]:
        return {
            **asdict(self),
            "noise_rate": self.noise_count / self.evidence_count if self.evidence_count else 0.0,
            "topic_acceptance_rate": (
                self.accepted_topic_count / self.naming_attempt_count
                if self.naming_attempt_count else 0.0
            ),
            "duplicate_topic_rate": (
                self.duplicate_topic_count / self.naming_attempt_count
                if self.naming_attempt_count else 0.0
            ),
            "snapshot_completeness": (
                (self.clustered_count + self.noise_count) / self.evidence_count
                if self.evidence_count else 0.0
            ),
        }


THRESHOLD_VERSION = "taxonomy-release-gate-v1"
THRESHOLDS = {
    "minimum_snapshot_completeness": 1.0,
    "maximum_noise_rate": 0.4,
    "minimum_topic_acceptance_rate": 0.8,
    "maximum_duplicate_topic_rate": 0.1,
}


def evaluate_computed_gate(metrics: dict[str, int | float]) -> tuple[bool, tuple[str, ...]]:
    failures: list[str] = []
    if metrics["snapshot_completeness"] < THRESHOLDS["minimum_snapshot_completeness"]:
        failures.append("snapshot_incomplete")
    if metrics["noise_rate"] > THRESHOLDS["maximum_noise_rate"]:
        failures.append("noise_rate_exceeded")
    if metrics["topic_acceptance_rate"] < THRESHOLDS["minimum_topic_acceptance_rate"]:
        failures.append("topic_acceptance_rate_low")
    if metrics["duplicate_topic_rate"] > THRESHOLDS["maximum_duplicate_topic_rate"]:
        failures.append("duplicate_topic_rate_exceeded")
    return not failures, tuple(failures)


def attestation_input_sha256(metrics: dict[str, int | float]) -> str:
    """Hash every machine-evaluated gate input, including its policy version."""
    gate_input = {
        "metrics": metrics,
        "threshold_version": THRESHOLD_VERSION,
        "thresholds": THRESHOLDS,
    }
    encoded = json.dumps(gate_input, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


async def compute_run_quality(
    pool: asyncpg.Pool, run_id: int, *, stage: ClaimedStage | None = None
) -> QualityFacts:
    async with pool.acquire() as connection:
        async with connection.transaction():
            if stage is not None:
                await require_stage_lease(connection, stage)
            row = await connection.fetchrow(
                """
                SELECT
                    (SELECT count(*) FROM taxonomy_run_evidence WHERE taxonomy_run_id = $1)::int AS evidence_count,
                    (SELECT count(*) FROM taxonomy_cluster_memberships WHERE taxonomy_run_id = $1 AND decision = 'clustered')::int AS clustered_count,
                    (SELECT count(*) FROM taxonomy_cluster_memberships WHERE taxonomy_run_id = $1 AND decision = 'noise')::int AS noise_count,
                    (SELECT count(*) FROM taxonomy_topic_naming_attempts WHERE taxonomy_run_id = $1)::int AS naming_attempt_count,
                    (SELECT count(*) FROM taxonomy_topic_naming_attempts WHERE taxonomy_run_id = $1 AND accepted)::int AS accepted_topic_count,
                    (SELECT count(*) FROM taxonomy_topic_naming_attempts WHERE taxonomy_run_id = $1 AND validation_errors @> ARRAY['duplicate_topic'])::int AS duplicate_topic_count,
                    (SELECT count(*) FROM taxonomy_candidate_themes WHERE taxonomy_run_id = $1)::int AS candidate_theme_count,
                    (SELECT count(*) FROM taxonomy_reconciled_themes WHERE taxonomy_run_id = $1)::int AS reconciled_theme_count
                """, run_id,
            )
            facts = QualityFacts(**dict(row))
            metrics = facts.signals()
            gate_passed, failures = evaluate_computed_gate(metrics)
            serialized = json.dumps(metrics, sort_keys=True, separators=(",", ":"))
            await connection.execute(
                """
                INSERT INTO taxonomy_release_attestations(
                    taxonomy_run_id, metrics, thresholds, threshold_version,
                    gate_passed, failures, input_sha256
                ) VALUES($1,$2::jsonb,$3::jsonb,$4,$5,$6,$7)
                ON CONFLICT (taxonomy_run_id) DO NOTHING
                """,
                run_id, serialized, json.dumps(THRESHOLDS, sort_keys=True),
                THRESHOLD_VERSION, gate_passed, list(failures),
                attestation_input_sha256(metrics),
            )
    return facts
