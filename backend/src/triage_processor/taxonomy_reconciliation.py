"""Deterministic immutable reconciliation of equivalent theme candidates."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

import asyncpg

from triage_processor.taxonomy_stages import ClaimedStage, require_stage_lease


@dataclass(frozen=True)
class ThemeCandidate:
    id: int
    name: str
    topic_revision_ids: tuple[int, ...]


@dataclass(frozen=True)
class ReconciledTheme:
    canonical_candidate_id: int
    normalized_name: str
    topic_set_sha256: str
    antecedent_candidate_ids: tuple[int, ...]


def _normalised_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def _topic_set_hash(topic_ids: tuple[int, ...]) -> str:
    return sha256(",".join(str(identifier) for identifier in topic_ids).encode("ascii")).hexdigest()


def reconcile_candidates(candidates: list[ThemeCandidate]) -> tuple[ReconciledTheme, ...]:
    """Choose the lowest raw-candidate ID for each exact name/topic-set identity."""
    groups: dict[tuple[str, tuple[int, ...]], list[int]] = {}
    for candidate in sorted(candidates, key=lambda item: item.id):
        name = _normalised_name(candidate.name)
        topics = tuple(sorted(set(candidate.topic_revision_ids)))
        if not name or not topics:
            raise ValueError("theme reconciliation requires a name and topic set")
        groups.setdefault((name, topics), []).append(candidate.id)
    return tuple(
        ReconciledTheme(
            canonical_candidate_id=antecedents[0], normalized_name=name,
            topic_set_sha256=_topic_set_hash(topics),
            antecedent_candidate_ids=tuple(antecedents),
        )
        for (name, topics), antecedents in sorted(groups.items())
    )


async def reconcile_run(pool: asyncpg.Pool, run_id: int, *, stage: ClaimedStage | None = None) -> tuple[ReconciledTheme, ...]:
    async with pool.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT candidate.id, candidate.name,
                   array_agg(link.topic_revision_id ORDER BY link.topic_revision_id) AS topic_revision_ids
            FROM taxonomy_candidate_themes AS candidate
            JOIN taxonomy_candidate_theme_topics AS link
              ON link.taxonomy_run_id = candidate.taxonomy_run_id
             AND link.candidate_theme_id = candidate.id
            WHERE candidate.taxonomy_run_id = $1
            GROUP BY candidate.id
            ORDER BY candidate.id
            """, run_id,
        )
        plan = reconcile_candidates([
            ThemeCandidate(row["id"], row["name"], tuple(row["topic_revision_ids"]))
            for row in rows
        ])
        async with connection.transaction():
            if stage is not None:
                await require_stage_lease(connection, stage)
            existing = await connection.fetchval(
                "SELECT count(*) FROM taxonomy_reconciled_themes WHERE taxonomy_run_id=$1", run_id
            )
            if existing:
                # Reconciliation writes as one transaction.  If a worker dies
                # after commit but before stage completion, the next lease
                # confirms the same deterministic plan without rewriting it.
                return plan
            for theme in plan:
                reconciled_id = await connection.fetchval(
                    """
                    INSERT INTO taxonomy_reconciled_themes(
                        taxonomy_run_id, canonical_candidate_theme_id, normalized_name, topic_set_sha256
                    ) VALUES($1,$2,$3,$4) RETURNING id
                    """, run_id, theme.canonical_candidate_id,
                    theme.normalized_name, theme.topic_set_sha256,
                )
                await connection.executemany(
                    """
                    INSERT INTO taxonomy_reconciled_theme_antecedents(
                        taxonomy_run_id, reconciled_theme_id, candidate_theme_id, relationship
                    ) VALUES($1,$2,$3,$4)
                    """,
                    [
                        (run_id, reconciled_id, candidate_id,
                         "canonical" if candidate_id == theme.canonical_candidate_id else "consolidated_duplicate")
                        for candidate_id in theme.antecedent_candidate_ids
                    ],
                )
    return plan
