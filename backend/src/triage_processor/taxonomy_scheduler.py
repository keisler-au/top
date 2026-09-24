"""Leased worker for supported durable batch-taxonomy stages."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import suppress
import logging
import os
from dataclasses import dataclass
from typing import Awaitable, Callable

import asyncpg

from triage_processor.config import DATABASE_URL
from triage_processor.job_queue import worker_id
from triage_processor.taxonomy_clustering import cluster_run
from triage_processor.taxonomy_reconciliation import reconcile_run
from triage_processor.taxonomy_stage_quality import compute_run_quality
from triage_processor.taxonomy_stages import ClaimedStage, bounded_error_class, cancel_stage, claim_next_stage, complete_ready_for_review_stage, complete_stage, fail_stage, renew_stage, retry_stage
from triage_processor.taxonomy_themes import infer_run
from triage_processor.taxonomy_topics import materialize_run
from triage_processor.taxonomy_automation import (
    AutomationPolicy, automation_evaluation_due, clear_evaluation_failures,
    evaluate_automation, record_evaluation_failure, record_scheduler_heartbeat,
)


LOGGER = logging.getLogger(__name__)
StageHandler = Callable[[asyncpg.Pool, ClaimedStage], Awaitable[object]]


@dataclass(frozen=True)
class SchedulerSettings:
    poll_interval: float = 10
    lease_seconds: float = 900
    max_attempts: int = 3
    retry_base_seconds: float = 5
    retry_max_seconds: float = 300
    configuration_version: str = "taxonomy-scheduler-v1"

    @classmethod
    def from_env(cls) -> "SchedulerSettings":
        settings = cls(
            poll_interval=float(os.getenv("TAXONOMY_POLL_INTERVAL", "10")),
            lease_seconds=float(os.getenv("TAXONOMY_LEASE_SECONDS", "900")),
            max_attempts=int(os.getenv("TAXONOMY_MAX_ATTEMPTS", "3")),
            retry_base_seconds=float(os.getenv("TAXONOMY_RETRY_BASE_SECONDS", "5")),
            retry_max_seconds=float(os.getenv("TAXONOMY_RETRY_MAX_SECONDS", "300")),
            configuration_version=os.getenv(
                "TAXONOMY_SCHEDULER_CONFIGURATION_VERSION",
                "taxonomy-scheduler-v1",
            ).strip(),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.poll_interval <= 0:
            raise ValueError("TAXONOMY_POLL_INTERVAL must be positive")
        if self.lease_seconds <= 0:
            raise ValueError("TAXONOMY_LEASE_SECONDS must be positive")
        if self.max_attempts < 1:
            raise ValueError("TAXONOMY_MAX_ATTEMPTS must be at least 1")
        if self.retry_base_seconds <= 0:
            raise ValueError("TAXONOMY_RETRY_BASE_SECONDS must be positive")
        if self.retry_max_seconds < self.retry_base_seconds:
            raise ValueError("TAXONOMY_RETRY_MAX_SECONDS must be at least TAXONOMY_RETRY_BASE_SECONDS")
        if not self.configuration_version:
            raise ValueError("TAXONOMY_SCHEDULER_CONFIGURATION_VERSION must be non-empty")


async def _cluster(pool: asyncpg.Pool, stage: ClaimedStage) -> object:
    return await cluster_run(pool, stage.run_id, stage=stage)


async def _name_topics(pool: asyncpg.Pool, stage: ClaimedStage) -> object:
    return await materialize_run(
        pool, run_id=stage.run_id, stage=stage,
        base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
        model=os.getenv("LLM_MODEL", "qwen3:4b-instruct"),
        api_key=os.getenv("LLM_API_KEY"),
    )


async def _infer_themes(pool: asyncpg.Pool, stage: ClaimedStage) -> object:
    return await infer_run(
        pool, stage.run_id, os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
        os.getenv("LLM_MODEL", "qwen3:4b-instruct"), stage=stage,
    )


async def _reconcile_themes(pool: asyncpg.Pool, stage: ClaimedStage) -> object:
    return await reconcile_run(pool, stage.run_id, stage=stage)


async def _compute_quality(pool: asyncpg.Pool, stage: ClaimedStage) -> object:
    return await compute_run_quality(pool, stage.run_id, stage=stage)


async def _ready_for_review(pool: asyncpg.Pool, stage: ClaimedStage) -> object:
    return {"run_id": stage.run_id, "quality_attested": True}


# The final stage makes a candidate reviewable; automation subsequently
# promotes it through the database publication gate.
HANDLERS: dict[str, StageHandler] = {
    "clustering": _cluster,
    "topic_naming": _name_topics,
    "theme_inference": _infer_themes,
    "theme_reconciliation": _reconcile_themes,
    "quality": _compute_quality,
    "ready_for_publication": _ready_for_review,
}

# Health must fail closed if a deployment has not applied the current durable
# stage contract.
def required_migration_filenames() -> tuple[str, ...]:
    # The migration runner is mounted separately from the worker image. This
    # explicit durable-stage contract marker must be advanced with every
    # scheduler schema change.
    return ("042_taxonomy_automation_replay.sql",)


async def _heartbeat(pool: asyncpg.Pool, stage: ClaimedStage, lease_seconds: float) -> None:
    interval = max(1.0, min(30.0, lease_seconds / 3))
    while True:
        await asyncio.sleep(interval)
        try:
            if not await renew_stage(pool, stage, lease_seconds=lease_seconds):
                LOGGER.warning("Lost lease for taxonomy stage %s", stage.id)
                return
        except Exception:
            LOGGER.exception("Could not renew taxonomy stage lease %s", stage.id)
            return


async def _mark_run_started(pool: asyncpg.Pool, stage: ClaimedStage) -> None:
    async with pool.acquire() as connection:
        await connection.execute(
            """
            UPDATE taxonomy_runs AS run
            SET status = 'running', started_at = COALESCE(run.started_at, CURRENT_TIMESTAMP),
                error_summary = NULL
            FROM taxonomy_run_stages AS stages
            WHERE run.id = stages.taxonomy_run_id
              AND stages.id = $1 AND stages.lease_owner = $2
              AND stages.status = 'running' AND stages.lease_expires_at >= CURRENT_TIMESTAMP
              AND run.status IN ('pending', 'failed')
            """,
            stage.id, stage.lease_owner,
        )


async def process_stage(
    pool: asyncpg.Pool,
    stage: ClaimedStage,
    *,
    lease_seconds: float,
    max_attempts: int,
    retry_base_seconds: float,
    retry_max_seconds: float,
) -> None:
    """Run one stage under a renewable lease and durably record its outcome."""
    await _mark_run_started(pool, stage)
    heartbeat = asyncio.create_task(_heartbeat(pool, stage, lease_seconds))
    try:
        result = await HANDLERS[stage.stage](pool, stage)
        complete = (
            complete_ready_for_review_stage
            if stage.stage == "ready_for_publication" else complete_stage
        )
        if not await complete(pool, stage, output_material=repr(result)):
            LOGGER.warning("Could not complete taxonomy stage %s because its lease was lost", stage.id)
    except Exception as error:
        result = await fail_stage(
            pool, stage, error, max_attempts=max_attempts,
            retry_base_seconds=retry_base_seconds, retry_max_seconds=retry_max_seconds,
        )
        LOGGER.error(
            "Taxonomy stage %s (%s) failed on attempt %s; status=%s; error_class=%s",
            stage.id, stage.stage, stage.attempt, result or "lease_lost",
            bounded_error_class(error),
        )
    finally:
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat


async def run_worker(
    *, once: bool, poll_interval: float, lease_seconds: float, max_attempts: int,
    retry_base_seconds: float = 5, retry_max_seconds: float = 300,
    automation_policy: AutomationPolicy | None = None,
) -> None:
    SchedulerSettings(
        poll_interval=poll_interval, lease_seconds=lease_seconds,
        max_attempts=max_attempts, retry_base_seconds=retry_base_seconds,
        retry_max_seconds=retry_max_seconds,
    ).validate()
    identity = worker_id()
    automation_policy = automation_policy or AutomationPolicy.from_env()
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2)
    try:
        while True:
            try:
                await record_scheduler_heartbeat(pool, automation_policy)
                if await automation_evaluation_due(pool):
                    await evaluate_automation(pool, automation_policy)
                    await clear_evaluation_failures(pool)
            except Exception:
                # Continue already-queued stages, but stop automatic evaluation
                # after three bounded attempts for one policy version.
                attempts = await record_evaluation_failure(pool)
                LOGGER.error("Taxonomy automation evaluation failed; attempt=%s", attempts)
            stage = await claim_next_stage(
                pool, lease_owner=identity, lease_seconds=lease_seconds,
                allowed_stages=tuple(HANDLERS),
            )
            if stage is None:
                if once:
                    return
                await asyncio.sleep(poll_interval)
                continue
            await process_stage(
                pool, stage, lease_seconds=lease_seconds, max_attempts=max_attempts,
                retry_base_seconds=retry_base_seconds, retry_max_seconds=retry_max_seconds,
            )
            if once:
                return
    finally:
        await pool.close()


async def check_health() -> None:
    """Fail closed unless this worker can safely claim durable candidate work."""
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=1)
    try:
        async with pool.acquire() as connection:
            applied = {
                row["filename"]
                for row in await connection.fetch("SELECT filename FROM schema_migrations")
            }
            missing = set(required_migration_filenames()) - applied
            if missing:
                raise RuntimeError("taxonomy scheduler migrations are not current")
            vector_ready = await connection.fetchval(
                "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')"
            )
            if not vector_ready:
                raise RuntimeError("pgvector extension is unavailable")
            claim_ready = await connection.fetchval(
                """
                SELECT
                    to_regclass('taxonomy_run_stages') IS NOT NULL
                    AND to_regclass('taxonomy_run_jobs') IS NOT NULL
                    AND has_table_privilege(
                        current_user, 'taxonomy_run_stages', 'SELECT,UPDATE'
                    )
                    AND has_table_privilege(
                        current_user, 'taxonomy_run_jobs', 'SELECT,UPDATE'
                    )
                """
            )
            if not claim_ready:
                raise RuntimeError("taxonomy scheduler cannot claim scheduled work")
    finally:
        await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run leased batch-taxonomy stages.")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--once", action="store_true")
    action.add_argument("--retry-stage-id", type=int)
    action.add_argument("--cancel-stage-id", type=int)
    action.add_argument("--healthcheck", action="store_true")
    settings = SchedulerSettings.from_env()
    automation_policy = AutomationPolicy.from_env()
    parser.add_argument("--poll-interval", type=float, default=settings.poll_interval)
    parser.add_argument("--lease-seconds", type=float, default=settings.lease_seconds)
    parser.add_argument("--max-attempts", type=int, default=settings.max_attempts)
    parser.add_argument("--retry-base-seconds", type=float, default=settings.retry_base_seconds)
    parser.add_argument("--retry-max-seconds", type=float, default=settings.retry_max_seconds)
    args = parser.parse_args()

    async def command() -> None:
        if args.healthcheck:
            await check_health()
            return
        if args.retry_stage_id is None and args.cancel_stage_id is None:
            await run_worker(
                once=args.once, poll_interval=args.poll_interval,
                lease_seconds=args.lease_seconds, max_attempts=args.max_attempts,
                retry_base_seconds=args.retry_base_seconds,
                retry_max_seconds=args.retry_max_seconds,
                automation_policy=automation_policy,
            )
            return
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=1)
        try:
            changed = await (
                retry_stage(pool, args.retry_stage_id)
                if args.retry_stage_id is not None
                else cancel_stage(pool, args.cancel_stage_id)
            )
        finally:
            await pool.close()
        if not changed:
            raise SystemExit("stage is not in a state that permits the requested operation")

    asyncio.run(command())


if __name__ == "__main__":
    main()
