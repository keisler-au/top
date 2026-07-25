import unittest

from app.workers.themes import (
    AnalysisUnit,
    ThemeDecision,
    group_related_units,
    process_cycle,
)


class AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeConnection:
    def __init__(self, *, locked=True, candidates=None, themes=None):
        self.locked = locked
        self.candidates = candidates or []
        self.themes = themes or []
        self.suggestion_inserts = []
        self.bulk_writes = []
        self.executed = []

    def transaction(self):
        return AsyncContext(None)

    async def fetchval(self, query, *values):
        if "pg_try_advisory_lock" in query:
            return self.locked
        if "SELECT EXISTS" in query:
            return False
        raise AssertionError(f"unexpected query: {query}")

    async def fetch(self, query, *values):
        if "WITH analysis_units" in query:
            return self.candidates
        if "FROM themes" in query:
            return self.themes
        raise AssertionError(f"unexpected query: {query}")

    async def fetchrow(self, query, *values):
        self.suggestion_inserts.append(values)
        return {"id": 99}

    async def executemany(self, query, values):
        self.bulk_writes.append((query, list(values)))

    async def execute(self, query, *values):
        self.executed.append((query, values))


class FakePool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return AsyncContext(self.connection)


class FakeSuggester:
    def __init__(self, decision):
        self.decision = decision
        self.contexts = []

    async def suggest(self, context):
        self.contexts.append(context)
        return self.decision


def unit(
    entity_id,
    original_input_id,
    topic,
    embedding,
    *,
    entity_type="segment",
):
    return AnalysisUnit(
        entity_type=entity_type,
        entity_id=entity_id,
        original_input_id=original_input_id,
        text=f"Evidence {entity_id}",
        topic=topic,
        embedding_model="embeddinggemma",
        embedding=embedding,
    )


class ThemeWorkerTests(unittest.IsolatedAsyncioTestCase):
    def test_groups_related_units_from_distinct_inputs(self):
        units = [
            unit(1, 10, "Housing", (1.0, 0.0)),
            unit(2, 11, "Housing", (0.8, 0.6)),
            unit(3, 12, "Transport", (0.0, 1.0)),
        ]

        groups = group_related_units(
            units,
            similarity_threshold=0.9,
            topic_similarity_threshold=0.65,
            min_group_size=2,
        )

        self.assertEqual([[item.entity_id for item in group] for group in groups], [[1, 2]])

    def test_does_not_create_recurring_group_from_one_input(self):
        units = [
            unit(1, 10, "Housing", (1.0, 0.0)),
            unit(2, 10, "Housing", (1.0, 0.0)),
        ]

        groups = group_related_units(
            units,
            similarity_threshold=0.9,
            topic_similarity_threshold=0.65,
            min_group_size=2,
        )

        self.assertEqual(groups, [])

    async def test_cycle_saves_review_suggestion_and_evidence(self):
        connection = FakeConnection(
            candidates=[
                {
                    "entity_type": "segment",
                    "entity_id": 20,
                    "original_input_id": 10,
                    "text": "Affordable homes",
                    "topic": "Housing",
                    "embedding_model": "embeddinggemma",
                    "embedding": "[1,0]",
                },
                {
                    "entity_type": "original",
                    "entity_id": 11,
                    "original_input_id": 11,
                    "text": "Rent is rising",
                    "topic": "Housing",
                    "embedding_model": "embeddinggemma",
                    "embedding": "[0.95,0.05]",
                },
            ],
            themes=[
                {
                    "id": 5,
                    "name": "Housing affordability",
                    "description": "Cost pressure",
                    "topics": ["Housing"],
                    "relevance": 1,
                }
            ],
        )
        suggester = FakeSuggester(
            ThemeDecision(
                action="reuse",
                existing_theme_ids=[5],
                proposed_name="Ignored alternative",
                proposed_description="Recurring concern about housing costs.",
                rationale="Both inputs discuss increasing housing costs.",
                topics=["Housing"],
            )
        )

        saved = await process_cycle(
            FakePool(connection),
            suggester,
            candidate_limit=100,
            theme_limit=20,
            similarity_threshold=0.9,
            topic_similarity_threshold=0.65,
            min_group_size=2,
        )

        self.assertEqual(saved, 1)
        self.assertEqual(
            connection.suggestion_inserts[0][1],
            "Housing affordability",
        )
        self.assertNotIn("embedding", suggester.contexts[0]["evidence"][0])
        write_queries = [query for query, _ in connection.bulk_writes]
        self.assertTrue(
            any("theme_suggestion_existing_themes" in query for query in write_queries)
        )
        self.assertTrue(
            any("theme_suggestion_topics" in query for query in write_queries)
        )
        self.assertTrue(
            any("theme_suggestion_evidence" in query for query in write_queries)
        )
        self.assertIn("pg_advisory_unlock", connection.executed[-1][0])

    async def test_cycle_skips_when_another_instance_holds_lock(self):
        connection = FakeConnection(locked=False)
        suggester = FakeSuggester(
            ThemeDecision(
                action="new",
                proposed_name="Unused",
                proposed_description="Unused description",
                rationale="Unused rationale",
                topics=["Unused"],
            )
        )

        saved = await process_cycle(
            FakePool(connection),
            suggester,
            candidate_limit=100,
            theme_limit=20,
            similarity_threshold=0.9,
            topic_similarity_threshold=0.65,
            min_group_size=2,
        )

        self.assertEqual(saved, 0)
        self.assertEqual(suggester.contexts, [])

    async def test_cycle_does_not_group_different_embedding_models(self):
        connection = FakeConnection(
            candidates=[
                {
                    "entity_type": "segment",
                    "entity_id": 30,
                    "original_input_id": 30,
                    "text": "Homes",
                    "topic": "Housing",
                    "embedding_model": "model-a",
                    "embedding": "[1,0]",
                },
                {
                    "entity_type": "segment",
                    "entity_id": 31,
                    "original_input_id": 31,
                    "text": "Rent",
                    "topic": "Housing",
                    "embedding_model": "model-b",
                    "embedding": "[1,0]",
                },
            ]
        )
        suggester = FakeSuggester(
            ThemeDecision(
                action="new",
                proposed_name="Unused",
                proposed_description="Unused description",
                rationale="Unused rationale",
                topics=["Housing"],
            )
        )

        saved = await process_cycle(
            FakePool(connection),
            suggester,
            candidate_limit=100,
            theme_limit=20,
            similarity_threshold=0.9,
            topic_similarity_threshold=0.65,
            min_group_size=2,
        )

        self.assertEqual(saved, 0)
        self.assertEqual(suggester.contexts, [])

    async def test_rejects_topics_outside_evidence(self):
        connection = FakeConnection(
            candidates=[
                {
                    "entity_type": "segment",
                    "entity_id": 20,
                    "original_input_id": 10,
                    "text": "Homes",
                    "topic": "Housing",
                    "embedding_model": "embeddinggemma",
                    "embedding": "[1,0]",
                },
                {
                    "entity_type": "segment",
                    "entity_id": 21,
                    "original_input_id": 11,
                    "text": "Rent",
                    "topic": "Housing",
                    "embedding_model": "embeddinggemma",
                    "embedding": "[1,0]",
                },
            ]
        )
        suggester = FakeSuggester(
            ThemeDecision(
                action="new",
                proposed_name="Housing pressure",
                proposed_description="Recurring housing pressure.",
                rationale="The evidence repeats this message.",
                topics=["Transport"],
            )
        )

        with self.assertRaisesRegex(ValueError, "outside the evidence"):
            await process_cycle(
                FakePool(connection),
                suggester,
                candidate_limit=100,
                theme_limit=20,
                similarity_threshold=0.9,
                topic_similarity_threshold=0.65,
                min_group_size=2,
            )

        self.assertEqual(connection.suggestion_inserts, [])
        self.assertIn("pg_advisory_unlock", connection.executed[-1][0])

    def test_merge_requires_multiple_existing_themes(self):
        with self.assertRaisesRegex(ValueError, "at least two"):
            ThemeDecision(
                action="merge",
                existing_theme_ids=[1],
                proposed_name="Merged",
                proposed_description="Merged description",
                rationale="Merge rationale",
                topics=["Housing"],
            )


if __name__ == "__main__":
    unittest.main()
