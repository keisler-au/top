import unittest

from triage_processor.workers.low_information import is_low_information
from triage_processor.workers.topics import (
    LocalTopicLLMClient,
    SegmentTopicAssignment,
    TopicAssignmentResult,
    TopicChoice,
    TopicDecision,
    TopicReviewDecision,
    TopicReviewFinding,
    _review_validation_errors,
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
        self.fetchrow_values = []
        self.evidence_requests = []
        self.evidence_queries = []
        self.topic_attempts = []

    def transaction(self):
        return AsyncContext(None)

    async def fetchrow(self, query, *values):
        self.fetchrow_values.append(values)
        return self.original

    async def fetch(self, query, *values):
        if "COUNT(*) AS usage_count" in query:
            return self.topics
        if "<=> $1::vector" in query:
            if "evidence_inputs.question_id = $4" in query:
                scope = "same_question"
            elif "evidence_inputs.question_id IS DISTINCT FROM $4" in query:
                scope = "other_questions"
            else:
                scope = "global"
            self.evidence_requests.append((values[0], scope, values))
            self.evidence_queries.append(query)
            return self.evidence.get(
                (values[0], scope),
                self.evidence.get(values[0], []),
            )
        return self.segments

    async def execute(self, query, *values):
        if "INSERT INTO topic_assignment_attempts" in query:
            self.topic_attempts.append(values)
            return
        self.executed.append((query, values))

    async def executemany(self, query, values):
        self.segment_updates.extend(values)


class FakePool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return AsyncContext(self.connection)


class FakeAssigner:
    def __init__(self, decision=None, error=None, decisions=None):
        self.decisions = list(decisions or ([decision] if decision else []))
        self.error = error
        self.context = None
        self.corrections = []

    async def assign(self, context, *, correction=None):
        self.context = context
        self.corrections.append(correction)
        if self.error:
            raise self.error
        decision = self.decisions.pop(0) if len(self.decisions) > 1 else self.decisions[0]
        raw_response = decision.model_dump(mode="json")
        return TopicAssignmentResult(
            decision=decision,
            raw_response=raw_response,
            model="fake-model",
            prompt_version="test-prompt",
        )


class TopicWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_topic_llm_client_constructs(self):
        client = LocalTopicLLMClient(
            base_url="http://localhost:11434/v1",
            model="test-model",
            timeout_seconds=1,
        )
        await client.close()

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
                        "evidence_type": "original",
                        "evidence_id": 30,
                        "text": "Affordable homes",
                        "topic": "Housing",
                        "distance": 0.1,
                    }
                ],
                "[0,1]": [
                    {
                        "evidence_type": "segment",
                        "evidence_id": 31,
                        "text": "Bus routes",
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
            input_id=10,
        )

        self.assertTrue(processed)
        self.assertEqual(connection.fetchrow_values, [(10,)])
        self.assertEqual(
            assigner.context["existing_topics"],
            ["Housing", "Transport"],
        )
        self.assertNotIn("embedding", assigner.context["targets"][0])
        self.assertIsNone(assigner.context["targets"][0]["question_text"])
        self.assertEqual(
            assigner.context["targets"][0]["similar_evidence"][0]["scope"],
            "global",
        )
        self.assertEqual(
            assigner.context["targets"][0]["similar_evidence"][0][
                "evidence_type"
            ],
            "original",
        )
        self.assertIn(
            "JOIN original_inputs AS unsegmented_inputs",
            connection.evidence_queries[0],
        )
        self.assertIn("WHERE NOT EXISTS", connection.evidence_queries[0])
        self.assertEqual(connection.executed[0][1], (10, "Housing"))
        self.assertEqual(
            connection.segment_updates,
            [(20, "Public transport")],
        )
        self.assertEqual(connection.executed[-1][1], (10,))

    async def test_contextual_price_can_receive_barrier_topic(self):
        question_text = "What is the biggest barrier to purchasing?"
        connection = FakeConnection(
            original={
                "id": 16,
                "original_text": "Price",
                "question_id": 101,
                "question_text": question_text,
                "embedding": "[1,0]",
                "embedding_model": "embeddinggemma",
            },
            segments=[
                {
                    "id": 26,
                    "segment_text": "Upfront cost",
                    "embedding": "[0,1]",
                    "embedding_model": "embeddinggemma",
                }
            ],
            evidence={
                ("[1,0]", "same_question"): [],
                ("[0,1]", "same_question"): [],
                ("[1,0]", "other_questions"): [
                    {
                        "evidence_type": "original",
                        "evidence_id": 35,
                        "text": "Price",
                        "topic": "Product Pricing",
                        "distance": 0.01,
                    }
                ],
            },
        )
        assigner = FakeAssigner(
            TopicDecision(
                original_topic=TopicChoice(
                    name="Purchase Barriers",
                    reused_existing=False,
                ),
                segment_topics=[
                    SegmentTopicAssignment(
                        segment_id=26,
                        topic=TopicChoice(
                            name="Purchase Barriers",
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
            [
                target["question_text"]
                for target in assigner.context["targets"]
            ],
            [question_text, question_text],
        )
        self.assertEqual(
            assigner.context["targets"][0]["similar_evidence"],
            [],
        )
        self.assertEqual(
            [request[1] for request in connection.evidence_requests],
            ["same_question", "same_question"],
        )
        self.assertEqual(
            connection.executed[0][1],
            (16, "Purchase Barriers"),
        )

    async def test_low_information_context_does_not_use_global_evidence(self):
        connection = FakeConnection(
            original={
                "id": 17,
                "original_text": "No",
                "question_id": 102,
                "question_text": "Would you recommend this product?",
                "embedding": "[0,1]",
                "embedding_model": "embeddinggemma",
            },
            evidence={
                ("[0,1]", "same_question"): [],
                ("[0,1]", "other_questions"): [
                    {
                        "evidence_type": "original",
                        "evidence_id": 36,
                        "text": "No",
                        "topic": "Purchase Intent",
                        "distance": 0.01,
                    }
                ],
            },
        )
        assigner = FakeAssigner(
            TopicDecision(
                original_topic=TopicChoice(
                    name="Recommendations",
                    reused_existing=False,
                )
            )
        )

        await process_next_input(
            FakePool(connection),
            assigner,
            similar_limit=5,
            topic_limit=50,
        )

        self.assertEqual(
            assigner.context["targets"][0]["similar_evidence"],
            [],
        )
        self.assertEqual(len(connection.evidence_requests), 1)
        self.assertEqual(
            connection.evidence_requests[0][1],
            "same_question",
        )

    async def test_rich_context_uses_same_question_then_global_evidence(self):
        connection = FakeConnection(
            original={
                "id": 18,
                "original_text": "The checkout process was confusing",
                "question_id": 103,
                "question_text": "What could we improve?",
                "embedding": "[1,1]",
                "embedding_model": "embeddinggemma",
            },
            evidence={
                ("[1,1]", "same_question"): [
                    {
                        "evidence_type": "original",
                        "evidence_id": 37,
                        "text": "Checkout was difficult",
                        "topic": "Checkout Experience",
                        "distance": 0.05,
                    }
                ],
                ("[1,1]", "other_questions"): [
                    {
                        "evidence_type": "segment",
                        "evidence_id": 38,
                        "text": "Confusing payment flow",
                        "topic": "Payment Experience",
                        "distance": 0.1,
                    }
                ],
            },
        )
        assigner = FakeAssigner(
            TopicDecision(
                original_topic=TopicChoice(
                    name="Checkout Experience",
                    reused_existing=True,
                )
            )
        )

        await process_next_input(
            FakePool(connection),
            assigner,
            similar_limit=2,
            topic_limit=50,
        )

        evidence = assigner.context["targets"][0]["similar_evidence"]
        self.assertEqual(
            [item["scope"] for item in evidence],
            ["same_question", "global"],
        )
        self.assertEqual(
            [request[1] for request in connection.evidence_requests],
            ["same_question", "other_questions"],
        )
        self.assertEqual(connection.evidence_requests[1][2][-1], 1)

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

    async def test_unrequested_segment_assignment_is_rejected(self):
        connection = FakeConnection(
            original={
                "id": 21,
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
                ),
                segment_topics=[
                    SegmentTopicAssignment(
                        segment_id=21,
                        topic=TopicChoice(
                            name="Libraries",
                            reused_existing=False,
                        ),
                    )
                ],
            )
        )

        with self.assertRaisesRegex(ValueError, "when no segments"):
            await process_next_input(
                FakePool(connection),
                assigner,
                similar_limit=5,
                topic_limit=50,
                validation_attempts=1,
            )

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

    async def test_invalid_reuse_is_corrected_and_audited(self):
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
            decisions=[
                TopicDecision(
                    original_topic=TopicChoice(
                        name="Unknown",
                        reused_existing=True,
                    )
                ),
                TopicDecision(
                    original_topic=TopicChoice(
                        name="Unknown Category",
                        reused_existing=False,
                    )
                )
            ]
        )

        await process_next_input(
            FakePool(connection),
            assigner,
            similar_limit=5,
            topic_limit=50,
        )

        self.assertEqual(connection.executed[0][1], (14, "Unknown Category"))
        self.assertEqual(len(connection.topic_attempts), 2)
        self.assertFalse(connection.topic_attempts[0][-1])
        self.assertTrue(connection.topic_attempts[1][-1])
        self.assertIsNone(assigner.corrections[0])
        self.assertIn(
            "claims unknown topic",
            assigner.corrections[1]["validation_errors"][0],
        )

    async def test_verbatim_sentence_topic_is_corrected(self):
        connection = FakeConnection(
            original={
                "id": 19,
                "original_text": "sign up to the newsletter",
                "embedding": "[1,0]",
                "embedding_model": "embeddinggemma",
            }
        )
        assigner = FakeAssigner(
            decisions=[
                TopicDecision(
                    original_topic=TopicChoice(
                        name="sign up to the newsletter",
                        reused_existing=False,
                    )
                ),
                TopicDecision(
                    original_topic=TopicChoice(
                        name="Newsletter Participation",
                        reused_existing=False,
                    )
                ),
            ]
        )

        await process_next_input(
            FakePool(connection),
            assigner,
            similar_limit=5,
            topic_limit=50,
        )

        first_errors = connection.topic_attempts[0][-2]
        self.assertTrue(
            any("copied evidence verbatim" in error for error in first_errors)
        )
        self.assertEqual(
            connection.executed[0][1],
            (19, "Newsletter Participation"),
        )

    async def test_existing_topic_marked_new_is_rejected(self):
        connection = FakeConnection(
            original={
                "id": 20,
                "original_text": "More buses",
                "embedding": "[1,0]",
                "embedding_model": "embeddinggemma",
            },
            topics=[{"topic": "Public Transport", "usage_count": 1}],
        )
        assigner = FakeAssigner(
            TopicDecision(
                original_topic=TopicChoice(
                    name="Public Transport",
                    reused_existing=False,
                )
            )
        )

        with self.assertRaisesRegex(ValueError, "marked existing topic"):
            await process_next_input(
                FakePool(connection),
                assigner,
                similar_limit=5,
                topic_limit=50,
                validation_attempts=1,
            )

        self.assertFalse(connection.topic_attempts[0][-1])

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

    def test_low_information_defaults(self):
        self.assertTrue(is_low_information(" No "))
        self.assertTrue(is_low_information("Price"))
        self.assertFalse(is_low_information("123456789012345"))
        self.assertFalse(is_low_information("A detailed response"))

    def test_review_rejects_unsupported_specificity_and_granularity(self):
        review = TopicReviewDecision(
            original_topic=TopicReviewFinding(
                supported=False,
                appropriate_granularity=False,
                suggested_name="Project updates",
                reason="The target asks for updates but names no newsletter",
            )
        )

        errors = _review_validation_errors(
            review,
            [
                {
                    "kind": "original",
                    "id": 9,
                    "text": "keep up with updates",
                    "question_text": "How would you like to be involved?",
                }
            ],
        )

        self.assertEqual(len(errors), 2)
        self.assertIn("unsupported", errors[0])
        self.assertIn("inappropriate topic granularity", errors[1])
        self.assertIn("Project updates", errors[1])


if __name__ == "__main__":
    unittest.main()
