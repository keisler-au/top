import unittest

from app.workers.topics import (
    SegmentTopicAssignment,
    TopicChoice,
    TopicDecision,
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
    def __init__(
        self,
        *,
        original,
        segments=None,
        evidence=None,
        topics=None,
    ):
        self.original = original
        self.segments = segments or []
        self.evidence = evidence or {}
        self.topics = topics or []
        self.executed = []
        self.segment_updates = []

    def transaction(self):
        return AsyncContext(None)

    async def fetchrow(self, query):
        return self.original

    async def fetch(self, query, *values):
        if "COUNT(*) AS usage_count" in query:
            return self.topics
        if "embeddings.embedding <=>" in query:
            return self.evidence.get(values[0], [])
        return self.segments

    async def execute(self, query, *values):
        self.executed.append((query, values))

    async def executemany(self, query, values):
        self.segment_updates.extend(values)


class FakePool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return AsyncContext(self.connection)


class FakeAssigner:
    def __init__(self, decision=None, error=None):
        self.decision = decision
        self.error = error
        self.context = None

    async def assign(self, context):
        self.context = context
        if self.error:
            raise self.error
        return self.decision


class TopicWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_assigns_topics_using_similar_evidence(self):
        connection = FakeConnection(
            original={
                "id": 10,
                "original_text": "Housing and buses",
                "embedding": "[1,0]",
                "embedding_model": "embeddinggemma",
            },
            segments=[
                {
                    "id": 20,
                    "segment_text": "More buses",
                    "embedding": "[0,1]",
                    "embedding_model": "embeddinggemma",
                }
            ],
            evidence={
                "[1,0]": [
                    {
                        "id": 30,
                        "segment_text": "Affordable homes",
                        "topic": "Housing",
                        "distance": 0.1,
                    }
                ],
                "[0,1]": [
                    {
                        "id": 31,
                        "segment_text": "Bus routes",
                        "topic": "Transport",
                        "distance": 0.2,
                    }
                ],
            },
            topics=[
                {"topic": "Housing", "usage_count": 5},
                {"topic": "Transport", "usage_count": 3},
            ],
        )
        assigner = FakeAssigner(
            TopicDecision(
                original_topic=TopicChoice(
                    name="housing",
                    reused_existing=True,
                ),
                segment_topics=[
                    SegmentTopicAssignment(
                        segment_id=20,
                        topic=TopicChoice(
                            name="Public transport",
                            reused_existing=False,
                        ),
                    )
                ],
            )
        )

        processed = await process_next_input(
            FakePool(connection),
            assigner,
            similar_limit=5,
            topic_limit=50,
        )

        self.assertTrue(processed)
        self.assertEqual(
            assigner.context["existing_topics"],
            ["Housing", "Transport"],
        )
        self.assertNotIn("embedding", assigner.context["targets"][0])
        self.assertEqual(connection.executed[0][1], (10, "Housing"))
        self.assertEqual(
            connection.segment_updates,
            [(20, "Public transport")],
        )
        self.assertEqual(connection.executed[-1][1], (10,))

    async def test_input_without_segments_gets_original_topic(self):
        connection = FakeConnection(
            original={
                "id": 11,
                "original_text": "Libraries",
                "embedding": "[1,1]",
                "embedding_model": "embeddinggemma",
            }
        )
        assigner = FakeAssigner(
            TopicDecision(
                original_topic=TopicChoice(
                    name="Libraries",
                    reused_existing=False,
                )
            )
        )

        processed = await process_next_input(
            FakePool(connection),
            assigner,
            similar_limit=5,
            topic_limit=50,
        )

        self.assertTrue(processed)
        self.assertEqual(connection.segment_updates, [])
        self.assertEqual(connection.executed[0][1], (11, "Libraries"))

    async def test_missing_original_embedding_stops_processing(self):
        connection = FakeConnection(
            original={
                "id": 12,
                "original_text": "Text",
                "embedding": None,
                "embedding_model": None,
            }
        )
        assigner = FakeAssigner(error=AssertionError("should not be called"))

        with self.assertRaisesRegex(ValueError, "without an embedding"):
            await process_next_input(
                FakePool(connection),
                assigner,
                similar_limit=5,
                topic_limit=50,
            )

        self.assertEqual(connection.executed, [])

    async def test_mismatched_segment_embedding_model_stops_processing(self):
        connection = FakeConnection(
            original={
                "id": 15,
                "original_text": "Text",
                "embedding": "[1,0]",
                "embedding_model": "embeddinggemma",
            },
            segments=[
                {
                    "id": 25,
                    "segment_text": "Segment",
                    "embedding": "[1,0]",
                    "embedding_model": "other-model",
                }
            ],
        )
        assigner = FakeAssigner(error=AssertionError("should not be called"))

        with self.assertRaisesRegex(ValueError, "different models"):
            await process_next_input(
                FakePool(connection),
                assigner,
                similar_limit=5,
                topic_limit=50,
            )

        self.assertEqual(connection.executed, [])

    async def test_incomplete_segment_assignments_are_rejected(self):
        connection = FakeConnection(
            original={
                "id": 13,
                "original_text": "Two topics",
                "embedding": "[1,0]",
                "embedding_model": "embeddinggemma",
            },
            segments=[
                {
                    "id": 21,
                    "segment_text": "One",
                    "embedding": "[1,0]",
                    "embedding_model": "embeddinggemma",
                },
                {
                    "id": 22,
                    "segment_text": "Two",
                    "embedding": "[0,1]",
                    "embedding_model": "embeddinggemma",
                },
            ],
        )
        assigner = FakeAssigner(
            TopicDecision(
                original_topic=TopicChoice(
                    name="General",
                    reused_existing=False,
                ),
                segment_topics=[
                    SegmentTopicAssignment(
                        segment_id=21,
                        topic=TopicChoice(
                            name="One",
                            reused_existing=False,
                        ),
                    )
                ],
            )
        )

        with self.assertRaisesRegex(ValueError, "do not match"):
            await process_next_input(
                FakePool(connection),
                assigner,
                similar_limit=5,
                topic_limit=50,
            )

        self.assertEqual(connection.executed, [])
        self.assertEqual(connection.segment_updates, [])

    async def test_unknown_reused_topic_is_rejected(self):
        connection = FakeConnection(
            original={
                "id": 14,
                "original_text": "Text",
                "embedding": "[1,0]",
                "embedding_model": "embeddinggemma",
            },
            topics=[{"topic": "Known", "usage_count": 1}],
        )
        assigner = FakeAssigner(
            TopicDecision(
                original_topic=TopicChoice(
                    name="Unknown",
                    reused_existing=True,
                )
            )
        )

        with self.assertRaisesRegex(ValueError, "unknown topic"):
            await process_next_input(
                FakePool(connection),
                assigner,
                similar_limit=5,
                topic_limit=50,
            )

        self.assertEqual(connection.executed, [])

    async def test_no_ready_input_does_nothing(self):
        connection = FakeConnection(original=None)
        assigner = FakeAssigner(error=AssertionError("should not be called"))

        processed = await process_next_input(
            FakePool(connection),
            assigner,
            similar_limit=5,
            topic_limit=50,
        )

        self.assertFalse(processed)
        self.assertEqual(connection.executed, [])


if __name__ == "__main__":
    unittest.main()
