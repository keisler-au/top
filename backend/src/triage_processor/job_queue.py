import asyncio
import logging
import os
import socket
import uuid
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Literal

import asyncpg

LOGGER = logging.getLogger(__name__)

JobType = Literal[
    "eligibility_segmentation",
    "embeddings",
    "topics",
    "themes",
]


@dataclass(frozen=True)
class Job:
    id: int
    job_type: JobType
    original_input_id: int
    attempts: int
    locked_by: str


@dataclass(frozen=True)
class QueueSettings:
    lease_seconds: float = 300
    max_attempts: int = 5
    retry_base_seconds: float = 5
    retry_max_seconds: float = 300

    @classmethod
    def from_env(cls) -> "QueueSettings":
        settings = cls(
            lease_seconds=float(os.getenv("QUEUE_LEASE_SECONDS", "300")),
            max_attempts=int(os.getenv("QUEUE_MAX_ATTEMPTS", "5")),
            retry_base_seconds=float(
                os.getenv("QUEUE_RETRY_BASE_SECONDS", "5")
            ),
            retry_max_seconds=float(
                os.getenv("QUEUE_RETRY_MAX_SECONDS", "300")
            ),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.lease_seconds <= 0:
            raise ValueError("QUEUE_LEASE_SECONDS must be positive")
        if self.max_attempts < 1:
            raise ValueError("QUEUE_MAX_ATTEMPTS must be at least 1")
        if self.retry_base_seconds <= 0:
            raise ValueError("QUEUE_RETRY_BASE_SECONDS must be positive")
        if self.retry_max_seconds < self.retry_base_seconds:
            raise ValueError(
                "QUEUE_RETRY_MAX_SECONDS must be at least "
                "QUEUE_RETRY_BASE_SECONDS"
            )


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex}"


def retry_delay_seconds(job: Job, settings: QueueSettings) -> float:
    exponent = max(job.attempts - 1, 0)
    return min(
        settings.retry_base_seconds * (2**exponent),
        settings.retry_max_seconds,
    )


async def claim_job(
    pool: asyncpg.Pool,
    *,
    job_type: JobType,
    locked_by: str,
    lease_seconds: float,
) -> Job | None:
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            WITH next_job AS (
                SELECT id
                FROM worker_jobs
                WHERE
                    job_type = $1
                    AND available_at <= CURRENT_TIMESTAMP
                    AND (
                        status = 'pending'
                        OR (
                            status = 'processing'
                            AND locked_at
                                < CURRENT_TIMESTAMP
                                    - ($2 * INTERVAL '1 second')
                        )
                    )
                ORDER BY available_at, id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE worker_jobs AS jobs
            SET
                status = 'processing',
                attempts = jobs.attempts + 1,
                locked_at = CURRENT_TIMESTAMP,
                locked_by = $3,
                last_error = NULL,
                updated_at = CURRENT_TIMESTAMP
            FROM next_job
            WHERE jobs.id = next_job.id
            RETURNING
                jobs.id,
                jobs.job_type,
                jobs.original_input_id,
                jobs.attempts,
                jobs.locked_by
            """,
            job_type,
            lease_seconds,
            locked_by,
        )
    if row is None:
        return None
    return Job(
        id=row["id"],
        job_type=row["job_type"],
        original_input_id=row["original_input_id"],
        attempts=row["attempts"],
        locked_by=row["locked_by"],
    )


async def renew_job(pool: asyncpg.Pool, job: Job) -> bool:
    async with pool.acquire() as connection:
        renewed_id = await connection.fetchval(
            """
            UPDATE worker_jobs
            SET
                locked_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE
                id = $1
                AND status = 'processing'
                AND locked_by = $2
            RETURNING id
            """,
            job.id,
            job.locked_by,
        )
    return renewed_id is not None


async def complete_job(pool: asyncpg.Pool, job: Job) -> bool:
    async with pool.acquire() as connection:
        completed_id = await connection.fetchval(
            """
            UPDATE worker_jobs
            SET
                status = 'completed',
                locked_at = NULL,
                locked_by = NULL,
                completed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE
                id = $1
                AND status = 'processing'
                AND locked_by = $2
            RETURNING id
            """,
            job.id,
            job.locked_by,
        )
    return completed_id is not None


async def fail_job(
    pool: asyncpg.Pool,
    job: Job,
    error: Exception,
    settings: QueueSettings,
) -> str | None:
    terminal = job.attempts >= settings.max_attempts
    delay_seconds = retry_delay_seconds(job, settings)
    next_status = "failed" if terminal else "pending"
    async with pool.acquire() as connection:
        return await connection.fetchval(
            """
            UPDATE worker_jobs
            SET
                status = $3,
                available_at = CASE
                    WHEN $3 = 'pending'
                    THEN CURRENT_TIMESTAMP + ($4 * INTERVAL '1 second')
                    ELSE available_at
                END,
                locked_at = NULL,
                locked_by = NULL,
                last_error = $5,
                updated_at = CURRENT_TIMESTAMP
            WHERE
                id = $1
                AND status = 'processing'
                AND locked_by = $2
            RETURNING status
            """,
            job.id,
            job.locked_by,
            next_status,
            delay_seconds,
            str(error)[:4000],
        )


async def _heartbeat(
    pool: asyncpg.Pool,
    job: Job,
    lease_seconds: float,
) -> None:
    interval = max(1.0, min(30.0, lease_seconds / 3))
    while True:
        await asyncio.sleep(interval)
        try:
            renewed = await renew_job(pool, job)
        except Exception:
            LOGGER.exception("Could not renew lease for job %s", job.id)
            return
        if not renewed:
            LOGGER.warning("Lost lease for job %s", job.id)
            return


async def run_job_loop(
    pool: asyncpg.Pool,
    *,
    job_type: JobType,
    handler: Callable[[int], Awaitable[object]],
    once: bool,
    poll_interval: float,
    settings: QueueSettings,
) -> None:
    settings.validate()
    if poll_interval <= 0:
        raise ValueError("poll_interval must be positive")

    identity = worker_id()
    while True:
        try:
            job = await claim_job(
                pool,
                job_type=job_type,
                locked_by=identity,
                lease_seconds=settings.lease_seconds,
            )
        except Exception:
            LOGGER.exception("Could not claim a %s job", job_type)
            if once:
                raise
            await asyncio.sleep(poll_interval)
            continue
        if job is None:
            if once:
                return
            await asyncio.sleep(poll_interval)
            continue

        heartbeat = asyncio.create_task(
            _heartbeat(pool, job, settings.lease_seconds)
        )
        error: Exception | None = None
        try:
            await handler(job.original_input_id)
        except Exception as exc:
            error = exc
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat

        if error is None:
            completed = await complete_job(pool, job)
            if completed:
                LOGGER.info(
                    "Completed %s job %s for input %s",
                    job.job_type,
                    job.id,
                    job.original_input_id,
                )
            else:
                LOGGER.warning(
                    "Could not complete job %s because its lease was lost",
                    job.id,
                )
        else:
            next_status = await fail_job(pool, job, error, settings)
            LOGGER.error(
                "%s job %s failed on attempt %s; status=%s",
                job.job_type,
                job.id,
                job.attempts,
                next_status or "lease_lost",
                exc_info=(type(error), error, error.__traceback__),
            )
            if once:
                raise error

        if once:
            return
