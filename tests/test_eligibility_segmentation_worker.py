import unittest

from app.workers.eligibility_segmentation import (
    LocalLLMClient,
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

    def transaction(self):
        return AsyncContext(None)

    async def fetchrow(self, query):
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

    async def classify(self, original_text):
        self.received_text = original_text
        if self.error:
            raise self.error
        return self.decision


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_llm_client_constructs(self):
        client = LocalLLMClient(
            base_url="http://localhost:11434/v1",
            model="test-model",
            timeout_seconds=1,
        )
        await client._client.close()

    async def test_eligible_input_saves_ordered_segments(self):
        connection = FakeConnection({"id": 42, "original_text": "Two topics"})
        segmenter = FakeSegmenter(
            SegmentationDecision(
                eligible=True,
                segments=["First topic", "Second topic"],
            )
        )

        processed = await process_next_input(FakePool(connection), segmenter)

        self.assertTrue(processed)
        self.assertEqual(segmenter.received_text, "Two topics")
        self.assertEqual(
            connection.inserted_segments,
            [(42, 0, "First topic"), (42, 1, "Second topic")],
        )
        self.assertEqual(connection.executed[-1], (42, "ready_for_embedding"))

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
