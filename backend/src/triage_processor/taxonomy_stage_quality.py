"""Durable, server-computed candidate quality facts for a taxonomy run."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
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
    canonical_topic_count: int = 0
    evidence_with_topic_count: int = 0
    evidence_without_topic_count: int = 0
    question_count: int = 0
    submission_count: int = 0
    rejected_topic_count: int = 0
    integrity_failures: tuple[str, ...] = ()

    def signals(self) -> dict[str, object]:
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


THRESHOLD_VERSION = "taxonomy-release-gate-v3"
THRESHOLDS = {"minimum_canonical_topic_count": 1, "require_internal_consistency": True}


def evaluate_computed_gate(metrics: dict) -> tuple[bool, tuple[str, ...]]:
    failures = list(metrics.get("integrity_failures", ()))
    counts = [metrics.get(key) for key in (
        "evidence_count", "canonical_topic_count", "evidence_with_topic_count",
        "evidence_without_topic_count",
    )]
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in counts):
        failures.append("coverage_inconsistent")
    if metrics.get("evidence_count", 0) == 0:
        failures.append("snapshot_empty")
    if isinstance(metrics.get("canonical_topic_count"), int) and metrics["canonical_topic_count"] < 1:
        failures.append("canonical_topics_missing")
    if all(isinstance(value, int) for value in counts) and counts[0] != counts[2] + counts[3]:
        failures.append("coverage_inconsistent")
    failures = list(dict.fromkeys(failures))
    return not failures, tuple(failures)


def attestation_input_sha256(metrics: dict) -> str:
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
                if stage.run_id != run_id or stage.stage != "quality":
                    raise ValueError("claimed stage does not match quality run")
                await require_stage_lease(connection, stage)
            existing = await connection.fetchval(
                "SELECT metrics FROM taxonomy_release_attestations WHERE taxonomy_run_id=$1", run_id
            )
            if existing is not None:
                metrics = json.loads(existing) if isinstance(existing, str) else dict(existing)
                stored = {field.name: metrics[field.name] for field in fields(QualityFacts)
                          if field.name in metrics}
                stored["integrity_failures"] = tuple(stored.get("integrity_failures", ()))
                return QualityFacts(**stored)
            raw = await connection.fetchval("SELECT taxonomy_publication_facts($1)", run_id)
            row = json.loads(raw) if isinstance(raw, str) else dict(raw)
            row["integrity_failures"] = tuple(row["integrity_failures"])
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
