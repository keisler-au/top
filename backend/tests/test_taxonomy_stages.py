import json
import unittest

from triage_processor.taxonomy_stages import (
    ClaimedStage,
    bounded_audit_object,
    bounded_error_class,
    cancel_stage,
    complete_ready_for_review_stage,
    claim_next_stage,
    complete_stage,
    fail_stage,
    record_model_failure,
    record_model_request,
    record_model_response,
    require_stage_lease,
    retry_stage,
    retry_delay_seconds,
)


class AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeConnection:
    def __init__(self, *, row=None, value=None):
        self.row = row
        self.value = value
        self.fetchrow_calls = []
        self.fetchval_calls = []

    async def fetchrow(self, query, *values):
        self.fetchrow_calls.append((query, values))
        return self.row

    async def fetchval(self, query, *values):
        self.fetchval_calls.append((query, values))
        return self.value

    def transaction(self):
        return AsyncContext(self)


class FakePool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return AsyncContext(self.connection)


class TaxonomyStageTests(unittest.IsolatedAsyncioTestCase):
    def test_audit_payloads_are_bounded_with_a_stable_correlation_hash(self):
        payload = {"response": "é" * 1_000}
        bounded = bounded_audit_object(payload, max_bytes=256)
        self.assertTrue(bounded["_audit_truncated"])
        self.assertEqual(bounded["original_bytes"], len(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")))
        self.assertRegex(bounded["original_sha256"], "^[0-9a-f]{64}$")
        self.assertLessEqual(len(json.dumps(bounded, ensure_ascii=False, separators=(",", ":")).encode("utf-8")), 256)

    def test_small_audit_payload_is_unchanged(self):
        payload = {"name": "literal response"}
        self.assertEqual(bounded_audit_object(payload), payload)

    async def test_model_request_and_response_use_immutable_identities(self):
        request_connection = FakeConnection(value=12)
        request_id = await record_model_request(
            FakePool(request_connection), run_id=9, stage="topic_naming",
            request_key="cluster:4", model="fixture", prompt_version="v1",
            prompt_sha256="a" * 64, request_context={"evidence": "literal"},
        )
        self.assertEqual(request_id, 12)
        request_query, request_values = request_connection.fetchval_calls[0]
        self.assertIn("taxonomy_model_requests", request_query)
        self.assertIn("ON CONFLICT (taxonomy_run_id, stage, request_key)", request_query)
        self.assertRegex(request_values[-1], "^[0-9a-f]{64}$")

        response_connection = FakeConnection(value=21)
        stored = await record_model_response(
            response_connection, run_id=9, request_id=12,
            raw_response={"name": "literal"}, validation_errors=(), accepted=True,
        )
        self.assertTrue(stored)
        response_query, response_values = response_connection.fetchval_calls[0]
        self.assertIn("taxonomy_model_responses", response_query)
        self.assertIn("ON CONFLICT (taxonomy_model_request_id) DO NOTHING", response_query)
        self.assertEqual(response_values[:2], (9, 12))

    async def test_model_failure_stores_only_a_bounded_error_class(self):
        connection = FakeConnection(value=21)
        await record_model_failure(
            FakePool(connection), run_id=9, request_id=12,
            error=RuntimeError("provider details must not be persisted"),
        )
        query, values = connection.fetchval_calls[0]
        self.assertIn("taxonomy_model_responses", query)
        self.assertIn("runtimeerror", values[2])
        self.assertNotIn("provider details", values[2])

    async def test_model_request_rejects_a_worker_that_lost_its_stage_lease(self):
        connection = FakeConnection(value=False)
        with self.assertRaisesRegex(RuntimeError, "no longer owned"):
            await record_model_request(
                FakePool(connection), run_id=9, stage="topic_naming", claimed_stage=ClaimedStage(
                    4, 9, "topic_naming", 1, "worker-a"
                ), request_key="cluster:4", model="fixture", prompt_version="v1",
                prompt_sha256="a" * 64, request_context={"evidence": "literal"},
            )
        self.assertEqual(len(connection.fetchval_calls), 1)
        self.assertIn("taxonomy_run_stages", connection.fetchval_calls[0][0])

    async def test_claim_requires_predecessors_and_returns_owned_lease(self):
        connection = FakeConnection(row={
            "id": 4, "taxonomy_run_id": 9, "stage": "clustering",
            "attempt": 1, "lease_owner": "worker-a",
        })
        claimed = await claim_next_stage(
            FakePool(connection), lease_owner="worker-a", lease_seconds=120
        )
        self.assertEqual(claimed, ClaimedStage(4, 9, "clustering", 1, "worker-a"))
        query, values = connection.fetchrow_calls[0]
        self.assertIn("FOR UPDATE SKIP LOCKED", query)
        self.assertIn("predecessor.status <> 'completed'", query)
        self.assertEqual(values[1:3], ("worker-a", 120))
        self.assertEqual(values[3], ["clustering", "topic_naming", "theme_inference", "theme_reconciliation", "quality", "ready_for_publication"])

    async def test_completion_and_failure_are_bound_to_current_owner(self):
        stage = ClaimedStage(4, 9, "clustering", 2, "worker-a")
        completed_connection = FakeConnection(value=4)
        self.assertTrue(await complete_stage(
            FakePool(completed_connection), stage, output_material="cluster-output"
        ))
        complete_query, complete_values = completed_connection.fetchval_calls[0]
        self.assertIn("lease_owner = $2", complete_query)
        self.assertEqual(complete_values[:2], (4, "worker-a"))
        self.assertRegex(complete_values[2], "^[0-9a-f]{64}$")

        failed_connection = FakeConnection(value="pending")
        status = await fail_stage(
            FakePool(failed_connection), stage, ValueError("model response"),
            max_attempts=3, retry_base_seconds=5, retry_max_seconds=60,
        )
        self.assertEqual(status, "pending")
        failure_query, failure_values = failed_connection.fetchval_calls[0]
        self.assertIn("lease_expires_at >= CURRENT_TIMESTAMP", failure_query)
        self.assertEqual(failure_values, (4, "worker-a", "pending", "valueerror", 10))

    def test_failure_categories_and_backoff_are_bounded(self):
        self.assertEqual(bounded_error_class(RuntimeError()), "runtimeerror")
        self.assertEqual(retry_delay_seconds(1, base_seconds=5, max_seconds=60), 5)
        self.assertEqual(retry_delay_seconds(8, base_seconds=5, max_seconds=60), 60)
        with self.assertRaisesRegex(ValueError, "positive"):
            retry_delay_seconds(0, base_seconds=5, max_seconds=60)

    async def test_require_stage_lease_rejects_a_lost_owner(self):
        connection = FakeConnection(value=False)
        with self.assertRaisesRegex(RuntimeError, "no longer owned"):
            await require_stage_lease(connection, ClaimedStage(4, 9, "clustering", 1, "worker-a"))

    async def test_retry_and_cancellation_use_guarded_stage_transitions(self):
        retry_connection = FakeConnection(value=4)
        self.assertTrue(await retry_stage(FakePool(retry_connection), 4))
        retry_query, retry_values = retry_connection.fetchval_calls[0]
        self.assertIn("status = 'failed'", retry_query)
        self.assertEqual(retry_values, (4,))

        cancel_connection = FakeConnection(value=4)
        self.assertTrue(await cancel_stage(FakePool(cancel_connection), 4))
        cancel_query, cancel_values = cancel_connection.fetchval_calls[0]
        self.assertIn("status IN ('pending', 'running', 'failed')", cancel_query)
        self.assertEqual(cancel_values, (4,))

    async def test_ready_completion_only_accepts_the_final_stage(self):
        with self.assertRaisesRegex(ValueError, "only the readiness"):
            await complete_ready_for_review_stage(
                FakePool(FakeConnection()), ClaimedStage(4, 9, "clustering", 1, "worker-a"),
                output_material="output",
            )
