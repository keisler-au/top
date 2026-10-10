"""PTR-1 transaction and ownership checks against disposable PostgreSQL."""

from __future__ import annotations

import asyncio
import os
import unittest
from uuid import uuid4

import asyncpg

from triage_processor.job_queue import Job, claim_job
from triage_processor.workers.eligibility_segmentation import (
    SegmentationDecision,
    process_next_input as prepare_input,
)
from triage_processor.workers.embeddings import process_next_input as embed_input


DSN = os.environ.get("TRIAGE_TEST_DATABASE_URL")


class BlockingSegmenter:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def classify(self, answer_text: str, question_text: str | None = None):
        self.started.set()
        await self.release.wait()
        return SegmentationDecision(
            eligible=True, segments=["First idea", "because the second idea matters"]
        )


class ImmediateSegmenter:
    async def classify(self, answer_text: str, question_text: str | None = None):
        return SegmentationDecision(
            eligible=True, segments=["First idea", "because the second idea matters"]
        )


class BlockingEmbedder:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def embed(self, texts):
        self.started.set()
        await self.release.wait()
        return [[1.0, float(index + 1)] for index, _ in enumerate(texts)]


class ImmediateEmbedder:
    async def embed(self, texts):
        return [[1.0, float(index + 1)] for index, _ in enumerate(texts)]


@unittest.skipUnless(DSN, "Set TRIAGE_TEST_DATABASE_URL or use compose.test.yaml")
class EvidenceWorkersPostgresTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4)
        self.addAsyncCleanup(self.pool.close)
        identity = uuid4().hex
        async with self.pool.acquire() as connection:
            self.question_id = await connection.fetchval(
                """INSERT INTO questions(source,form_key,question_key,question_text)
                   VALUES('ptr1-test',$1,$2,'What should change?') RETURNING id""",
                f"form-{identity}",
                f"question-{identity}",
            )

    async def _input(self, *, status: str = "new") -> int:
        async with self.pool.acquire() as connection:
            return await connection.fetchval(
                """INSERT INTO original_inputs(original_text,source,status,question_id)
                   VALUES('First idea because the second idea matters','ptr1-test',$1,$2)
                   RETURNING id""",
                status,
                self.question_id,
            )

    async def _replace_owner(self, job: Job, owner: str) -> Job:
        async with self.pool.acquire() as connection:
            await connection.execute(
                """UPDATE worker_jobs SET locked_by=$2,locked_at=CURRENT_TIMESTAMP
                   WHERE id=$1 AND status='processing'""",
                job.id,
                owner,
            )
        return Job(job.id, job.job_type, job.original_input_id, job.attempts, owner)

    async def _assert_input_lock_available(self, input_id: int) -> None:
        async with self.pool.acquire() as connection:
            transaction = connection.transaction()
            await transaction.start()
            try:
                await connection.fetchval(
                    "SELECT id FROM original_inputs WHERE id=$1 FOR UPDATE NOWAIT",
                    input_id,
                )
            finally:
                await transaction.rollback()

    async def test_segmentation_call_holds_no_row_lock_and_stale_owner_cannot_save(self):
        input_id = await self._input()
        job = await claim_job(
            self.pool,
            job_type="eligibility_segmentation",
            locked_by="ptr1-old-preparer",
            lease_seconds=300,
        )
        self.assertIsNotNone(job)
        blocker = BlockingSegmenter()
        task = asyncio.create_task(
            prepare_input(
                self.pool,
                blocker,
                input_id=input_id,
                job=job,
                model="fixture-chat",
            )
        )
        await blocker.started.wait()
        await self._assert_input_lock_available(input_id)
        replacement = await self._replace_owner(job, "ptr1-new-preparer")
        blocker.release.set()
        with self.assertRaisesRegex(RuntimeError, "no longer owned"):
            await task

        async with self.pool.acquire() as connection:
            self.assertEqual(await connection.fetchval(
                "SELECT count(*) FROM input_preparation_decisions WHERE original_input_id=$1",
                input_id,
            ), 0)
            self.assertEqual(await connection.fetchval(
                "SELECT status FROM original_inputs WHERE id=$1", input_id
            ), "new")

        self.assertTrue(await prepare_input(
            self.pool,
            ImmediateSegmenter(),
            input_id=input_id,
            job=replacement,
            model="fixture-chat",
        ))
        async with self.pool.acquire() as connection:
            self.assertEqual(await connection.fetchval(
                "SELECT count(*) FROM input_preparation_decisions WHERE original_input_id=$1",
                input_id,
            ), 1)
            self.assertEqual(await connection.fetchval(
                "SELECT count(*) FROM segment_inputs WHERE original_input_id=$1",
                input_id,
            ), 2)
            self.assertEqual(await connection.fetchval(
                "SELECT status FROM worker_jobs WHERE id=$1", job.id
            ), "completed")

    async def test_embedding_call_holds_no_row_lock_and_retry_writes_once(self):
        input_id = await self._input(status="ready_for_embedding")
        job = await claim_job(
            self.pool,
            job_type="embeddings",
            locked_by="ptr1-old-embedder",
            lease_seconds=300,
        )
        self.assertIsNotNone(job)
        blocker = BlockingEmbedder()
        task = asyncio.create_task(
            embed_input(
                self.pool,
                blocker,
                batch_size=16,
                embedding_model="fixture-embedding",
                input_id=input_id,
                job=job,
            )
        )
        await blocker.started.wait()
        await self._assert_input_lock_available(input_id)
        replacement = await self._replace_owner(job, "ptr1-new-embedder")
        blocker.release.set()
        with self.assertRaisesRegex(RuntimeError, "no longer owned"):
            await task

        self.assertTrue(await embed_input(
            self.pool,
            ImmediateEmbedder(),
            batch_size=16,
            embedding_model="fixture-embedding",
            input_id=input_id,
            job=replacement,
        ))
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """SELECT count(*) AS amount,min(embedding_representation) AS representation
                   FROM input_embeddings WHERE original_input_id=$1""",
                input_id,
            )
            self.assertEqual(row["amount"], 1)
            self.assertEqual(row["representation"], "question-answer")
            self.assertEqual(await connection.fetchval(
                "SELECT status FROM worker_jobs WHERE id=$1", job.id
            ), "completed")
            self.assertEqual(await connection.fetchval(
                "SELECT status FROM original_inputs WHERE id=$1", input_id
            ), "ready_for_analysis")

