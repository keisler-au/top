import json
import unittest

from triage_processor.workers.eligibility_segmentation import (
    LocalLLMClient,
    SYSTEM_PROMPT,
    SegmentationDecision,
    process_next_input,
)


class AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeConnection:
    def __init__(self, row):
        self.row = row
        self.inserted_segments = []
        self.executed = []
        self.fetchrow_queries = []
        self.fetchrow_values = []

    def transaction(self):
        return AsyncContext(None)

    async def fetchrow(self, query, *values):
        self.fetchrow_queries.append(query)
        self.fetchrow_values.append(values)
        return self.row

    async def executemany(self, query, values):
        self.inserted_segments.extend(values)

    async def execute(self, query, *values):
        self.executed.append(values)


class FakePool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return AsyncContext(self.connection)


class FakeSegmenter:
    def __init__(self, decision=None, error=None):
        self.decision = decision
        self.error = error
        self.received_text = None
        self.received_question_text = None

    async def classify(self, answer_text, question_text=None):
        self.received_text = answer_text
        self.received_question_text = question_text
        if self.error:
            raise self.error
        return self.decision


class FakeStructuredClient:
    def __init__(self, result):
        self.result = result
        self.system_prompt = None
        self.user_content = None
        self.closed = False

    async def complete(self, *, system_prompt, user_content):
        self.system_prompt = system_prompt
        self.user_content = user_content
        return self.result

    async def close(self):
        self.closed = True


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_llm_client_constructs(self):
        client = LocalLLMClient(
            base_url="http://localhost:11434/v1",
            model="test-model",
            timeout_seconds=1,
        )
        await client.close()

    async def test_local_llm_client_sends_structured_context(self):
        client = LocalLLMClient(
            base_url="http://localhost:11434/v1",
            model="test-model",
            timeout_seconds=1,
        )
        structured_client = FakeStructuredClient(
            {"eligible": True, "segments": []}
        )
        await client._client.close()
        client._client = structured_client

        decision = await client.classify(
            "Price",
            "What is the biggest barrier to purchasing?",
        )
        await client.close()

        self.assertTrue(decision.eligible)
        self.assertEqual(
            json.loads(structured_client.user_content),
            {
                "answer_text": "Price",
                "question_text": (
                    "What is the biggest barrier to purchasing?"
                ),
            },
        )
        self.assertEqual(structured_client.system_prompt, SYSTEM_PROMPT)
        self.assertTrue(structured_client.closed)

    async def test_generic_llm_payload_omits_question_text(self):
        client = LocalLLMClient(
            base_url="http://localhost:11434/v1",
            model="test-model",
            timeout_seconds=1,
        )
        structured_client = FakeStructuredClient(
            {"eligible": True, "segments": []}
        )
        await client._client.close()
        client._client = structured_client

        await client.classify("A useful generic comment")
        await client.close()

        self.assertEqual(
            json.loads(structured_client.user_content),
            {"answer_text": "A useful generic comment"},
        )

    async def test_eligible_input_saves_ordered_segments(self):
        connection = FakeConnection({"id": 42, "original_text": "Two topics"})
        segmenter = FakeSegmenter(
            SegmentationDecision(
                eligible=True,
                segments=["First topic", "Second topic"],
            )
        )

        processed = await process_next_input(
            FakePool(connection),
            segmenter,
            input_id=42,
        )

        self.assertTrue(processed)
        self.assertEqual(connection.fetchrow_values, [(42,)])
        self.assertEqual(segmenter.received_text, "Two topics")
        self.assertEqual(
            connection.inserted_segments,
            [(42, 0, "First topic"), (42, 1, "Second topic")],
        )
        self.assertEqual(connection.executed[-1], (42, "ready_for_embedding"))

    async def test_short_answer_is_processed_with_question_context(self):
        connection = FakeConnection(
            {
                "id": 43,
                "original_text": "No",
                "question_text": "Would you recommend this product?",
            }
        )
        segmenter = FakeSegmenter(
            SegmentationDecision(eligible=True, segments=[])
        )

        processed = await process_next_input(
            FakePool(connection),
            segmenter,
            input_id=43,
        )

        self.assertTrue(processed)
        self.assertEqual(segmenter.received_text, "No")
        self.assertEqual(
            segmenter.received_question_text,
            "Would you recommend this product?",
        )
        self.assertEqual(
            connection.executed[-1],
            (43, "ready_for_embedding"),
        )
        self.assertIn("LEFT JOIN questions", connection.fetchrow_queries[0])

    async def test_contextual_segments_contain_only_answer_content(self):
        connection = FakeConnection(
            {
                "id": 44,
                "original_text": "Price and delivery times",
                "question_text": "What prevented your purchase?",
            }
        )
        segmenter = FakeSegmenter(
            SegmentationDecision(
                eligible=True,
                segments=["Price", "Delivery times"],
            )
        )

        await process_next_input(FakePool(connection), segmenter, input_id=44)

        self.assertEqual(
            connection.inserted_segments,
            [(44, 0, "Price"), (44, 1, "Delivery times")],
        )
        self.assertNotIn(
            connection.row["question_text"],
            [segment[2] for segment in connection.inserted_segments],
        )

    async def test_context_does_not_make_spam_eligible(self):
        connection = FakeConnection(
            {
                "id": 45,
                "original_text": "asdf qwer spam",
                "question_text": "What is your purchase barrier?",
            }
        )
        segmenter = FakeSegmenter(
            SegmentationDecision(eligible=False, segments=[])
        )

        await process_next_input(FakePool(connection), segmenter, input_id=45)

        self.assertEqual(
            segmenter.received_question_text,
            connection.row["question_text"],
        )
        self.assertEqual(connection.inserted_segments, [])
        self.assertEqual(connection.executed[-1], (45, "ineligible"))

    async def test_ineligible_input_does_not_save_segments(self):
        connection = FakeConnection({"id": 7, "original_text": "Spam"})
        segmenter = FakeSegmenter(
            SegmentationDecision(eligible=False, segments=[])
        )

        processed = await process_next_input(FakePool(connection), segmenter)

        self.assertTrue(processed)
        self.assertEqual(connection.inserted_segments, [])
        self.assertEqual(connection.executed[-1], (7, "ineligible"))

    async def test_no_new_input_does_nothing(self):
        connection = FakeConnection(None)
        segmenter = FakeSegmenter(error=AssertionError("should not be called"))

        processed = await process_next_input(FakePool(connection), segmenter)

        self.assertFalse(processed)
        self.assertEqual(connection.executed, [])

    async def test_llm_failure_does_not_update_status(self):
        connection = FakeConnection({"id": 9, "original_text": "Text"})
        segmenter = FakeSegmenter(error=RuntimeError("LLM unavailable"))

        with self.assertRaises(RuntimeError):
            await process_next_input(FakePool(connection), segmenter)

        self.assertEqual(connection.inserted_segments, [])
        self.assertEqual(connection.executed, [])

    def test_rejects_a_single_segment(self):
        with self.assertRaises(ValueError):
            SegmentationDecision(eligible=True, segments=["Only segment"])

    def test_rejects_segments_for_ineligible_input(self):
        with self.assertRaises(ValueError):
            SegmentationDecision(eligible=False, segments=["Not allowed", "Also"])


if __name__ == "__main__":
    unittest.main()
