import unittest

from triage_processor.job_queue import (
    Job,
    QueueSettings,
    claim_job,
    complete_job,
    fail_job,
    retry_delay_seconds,
    run_job_loop,
)


class AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeConnection:
    def __init__(self, *, claimed=None, returned_value=None):
        self.claimed = claimed
        self.returned_value = returned_value
        self.fetchrow_calls = []
        self.fetchval_calls = []

    async def fetchrow(self, query, *values):
        self.fetchrow_calls.append((query, values))
        return self.claimed

    async def fetchval(self, query, *values):
        self.fetchval_calls.append((query, values))
        return self.returned_value


class FakePool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return AsyncContext(self.connection)


class JobQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_claims_available_job_with_lease_owner(self):
        connection = FakeConnection(
            claimed={
                "id": 7,
                "job_type": "embeddings",
                "original_input_id": 42,
                "attempts": 2,
                "locked_by": "worker-1",
            }
        )

        job = await claim_job(
            FakePool(connection),
            job_type="embeddings",
            locked_by="worker-1",
            lease_seconds=300,
        )

        self.assertEqual(
            job,
            Job(
                id=7,
                job_type="embeddings",
                original_input_id=42,
                attempts=2,
                locked_by="worker-1",
            ),
        )
        self.assertEqual(
            connection.fetchrow_calls[0][1],
            ("embeddings", 300, "worker-1"),
        )
        self.assertIn("FOR UPDATE SKIP LOCKED", connection.fetchrow_calls[0][0])

    async def test_completes_only_job_owned_by_worker(self):
        job = Job(7, "topics", 42, 1, "worker-1")
        connection = FakeConnection(returned_value=7)

        completed = await complete_job(FakePool(connection), job)

        self.assertTrue(completed)
        self.assertEqual(connection.fetchval_calls[0][1], (7, "worker-1"))
        self.assertIn("status = 'completed'", connection.fetchval_calls[0][0])

    async def test_job_loop_routes_claimed_input_to_handler(self):
        connection = FakeConnection(
            claimed={
                "id": 7,
                "job_type": "eligibility_segmentation",
                "original_input_id": 42,
                "attempts": 1,
                "locked_by": "generated-worker-id",
            },
            returned_value=7,
        )
        handled = []

        async def handler(input_id):
            handled.append(input_id)

        await run_job_loop(
            FakePool(connection),
            job_type="eligibility_segmentation",
            handler=handler,
            once=True,
            poll_interval=2,
            settings=QueueSettings(),
        )

        self.assertEqual(handled, [42])
        self.assertIn("status = 'completed'", connection.fetchval_calls[0][0])

    async def test_failure_is_retried_with_exponential_backoff(self):
        job = Job(7, "topics", 42, 3, "worker-1")
        settings = QueueSettings(
            lease_seconds=300,
            max_attempts=5,
            retry_base_seconds=5,
            retry_max_seconds=300,
        )
        connection = FakeConnection(returned_value="pending")

        status = await fail_job(
            FakePool(connection),
            job,
            RuntimeError("temporary failure"),
            settings,
        )

        self.assertEqual(status, "pending")
        self.assertEqual(retry_delay_seconds(job, settings), 20)
        self.assertEqual(
            connection.fetchval_calls[0][1],
            (7, "worker-1", "pending", 20, "temporary failure"),
        )

    async def test_failure_moves_job_to_dead_letter_state(self):
        job = Job(7, "topics", 42, 5, "worker-1")
        settings = QueueSettings(max_attempts=5)
        connection = FakeConnection(returned_value="failed")

        status = await fail_job(
            FakePool(connection),
            job,
            ValueError("invalid response"),
            settings,
        )

        self.assertEqual(status, "failed")
        self.assertEqual(connection.fetchval_calls[0][1][2], "failed")

    def test_rejects_invalid_queue_settings(self):
        with self.assertRaisesRegex(ValueError, "MAX_ATTEMPTS"):
            QueueSettings(max_attempts=0).validate()


if __name__ == "__main__":
    unittest.main()
