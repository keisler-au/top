import unittest

from triage_processor.workers.themes import (
    AnalysisUnit,
    LocalThemeLLMClient,
    StoredThemeSuggestion,
    ThemeDecision,
    _materialize_suggestion,
    build_topic_clusters,
    is_cluster_eligible,
    materialize_pending_suggestions,
    process_cycle,
    sample_cluster_evidence,
    topic_cluster_fingerprint,
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
        locked=True,
        candidates=None,
        themes=None,
        existing_fingerprints=None,
    ):
        self.locked = locked
        self.candidates = candidates or []
        self.themes = themes or []
        self.existing_fingerprints = existing_fingerprints or set()
        self.suggestion_inserts = []
        self.bulk_writes = []
        self.executed = []
        self.candidate_query_values = None

    def transaction(self):
        return AsyncContext(None)

    async def fetchval(self, query, *values):
        if "pg_try_advisory_lock" in query:
            return self.locked
        if "SELECT EXISTS" in query:
            return values[0] in self.existing_fingerprints
        if "SELECT id" in query and "FROM themes" in query:
            return None
        raise AssertionError(f"unexpected query: {query}")

    async def fetch(self, query, *values):
        if (
            "SELECT id" in query
            and "FROM theme_suggestions" in query
            and "ORDER BY id" in query
        ):
            return []
        if "WITH analysis_units" in query:
            self.candidate_query_values = values
            return self.candidates
        if "WITH RECURSIVE theme_paths" in query:
            return [
                {"starting_id": theme_id, "root_id": theme_id}
                for theme_id in values[0]
            ]
        if "FROM themes" in query:
            return self.themes
        raise AssertionError(f"unexpected query: {query}")

    async def fetchrow(self, query, *values):
        if "INSERT INTO theme_suggestions" in query:
            self.suggestion_inserts.append(values)
            return {"id": 99}
        if "INSERT INTO themes" in query:
            self.themes.append(
                {
                    "id": 199,
                    "name": values[0],
                    "description": values[1],
                    "topics": [],
                }
            )
            return {"id": 199}
        raise AssertionError(f"unexpected query: {query}")

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


class SequencedSuggester:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.contexts = []

    async def suggest(self, context):
        self.contexts.append(context)
        return self.decisions.pop(0)


class MaterializationConnection:
    def __init__(self, *, themes=None, topics=None, suggestions=None):
        self.themes = {
            theme["id"]: {
                "id": theme["id"],
                "name": theme["name"],
                "description": theme.get("description"),
                "merged_into_id": theme.get("merged_into_id"),
            }
            for theme in (themes or [])
        }
        self.topics = set(topics or [])
        self.suggestions = {
            suggestion["id"]: dict(suggestion)
            for suggestion in (suggestions or [])
        }
        self.next_theme_id = max(self.themes, default=0) + 1

    def transaction(self):
        return AsyncContext(None)

    def _root(self, theme_id):
        seen = set()
        while self.themes[theme_id]["merged_into_id"] is not None:
            if theme_id in seen:
                raise AssertionError("theme merge cycle")
            seen.add(theme_id)
            theme_id = self.themes[theme_id]["merged_into_id"]
        return theme_id

    async def fetch(self, query, *values):
        if "WITH RECURSIVE theme_paths" in query:
            return [
                {
                    "starting_id": theme_id,
                    "root_id": self._root(theme_id),
                }
                for theme_id in values[0]
                if theme_id in self.themes
            ]
        if (
            "FROM theme_suggestions" in query
            and "WHERE materialized_at IS NULL" in query
        ):
            return [
                {"id": suggestion_id}
                for suggestion_id, suggestion in sorted(
                    self.suggestions.items()
                )
                if suggestion.get("materialized_at") is None
            ]
        if "FROM theme_suggestion_existing_themes" in query:
            return [
                {"theme_id": theme_id}
                for theme_id in sorted(
                    self.suggestions[values[0]]["existing_theme_ids"]
                )
            ]
        if "FROM theme_suggestion_topics" in query:
            return [
                {"topic": topic}
                for topic in sorted(
                    self.suggestions[values[0]]["topics"],
                    key=str.casefold,
                )
            ]
        raise AssertionError(f"unexpected query: {query}")

    async def fetchrow(self, query, *values):
        if "FROM theme_suggestions" in query and "FOR UPDATE" in query:
            suggestion = self.suggestions.get(values[0])
            if suggestion is None or suggestion.get("materialized_at") is not None:
                return None
            return suggestion
        if "INSERT INTO themes" in query:
            if any(
                theme["name"].casefold() == values[0].casefold()
                for theme in self.themes.values()
            ):
                return None
            theme_id = self.next_theme_id
            self.next_theme_id += 1
            self.themes[theme_id] = {
                "id": theme_id,
                "name": values[0],
                "description": values[1],
                "merged_into_id": None,
            }
            return {"id": theme_id}
        raise AssertionError(f"unexpected query: {query}")

    async def fetchval(self, query, *values):
        if "NOT (id = ANY" in query:
            allowed = set(values[1])
            return next(
                (
                    theme_id
                    for theme_id, theme in self.themes.items()
                    if theme["merged_into_id"] is None
                    and theme_id not in allowed
                    and theme["name"].casefold() == values[0].casefold()
                ),
                None,
            )
        if "id = ANY($2::bigint[])" in query:
            return next(
                (
                    theme_id
                    for theme_id in values[1]
                    if self.themes[theme_id]["name"].casefold()
                    == values[0].casefold()
                ),
                None,
            )
        if "lower(name) = lower($1)" in query:
            return next(
                (
                    theme_id
                    for theme_id, theme in self.themes.items()
                    if theme["merged_into_id"] is None
                    and theme["name"].casefold() == values[0].casefold()
                ),
                None,
            )
        raise AssertionError(f"unexpected query: {query}")

    async def executemany(self, query, values):
        if "INSERT INTO theme_topics" not in query:
            raise AssertionError(f"unexpected query: {query}")
        self.topics.update(values)

    async def execute(self, query, *values):
        if "INSERT INTO theme_topics" in query and "SELECT $1" in query:
            canonical_id, losing_id = values
            self.topics.update(
                (canonical_id, topic)
                for theme_id, topic in list(self.topics)
                if theme_id == losing_id
            )
            return
        if "DELETE FROM theme_topics" in query:
            self.topics = {
                item for item in self.topics if item[0] != values[0]
            }
            return
        if "WHERE merged_into_id = ANY" in query:
            canonical_id, losing_ids = values
            for theme in self.themes.values():
                if theme["merged_into_id"] in losing_ids:
                    theme["merged_into_id"] = canonical_id
            return
        if "WHERE id = ANY" in query:
            canonical_id, losing_ids = values
            for losing_id in losing_ids:
                self.themes[losing_id]["merged_into_id"] = canonical_id
            return
        if "name = left(name, 80)" in query:
            theme_id = values[0]
            old_name = self.themes[theme_id]["name"]
            self.themes[theme_id]["name"] = (
                f"{old_name[:80]} [merged #{theme_id}]"
            )
            return
        if "UPDATE themes" in query and "name = $2" in query:
            theme_id, name, description = values
            self.themes[theme_id]["name"] = name
            self.themes[theme_id]["description"] = description
            return
        if "UPDATE themes" in query:
            return
        if "UPDATE theme_suggestions" in query:
            suggestion_id, theme_id = values
            suggestion = self.suggestions.setdefault(
                suggestion_id,
                {"id": suggestion_id},
            )
            suggestion["materialized_theme_id"] = theme_id
            suggestion["materialized_at"] = "now"
            return
        raise AssertionError(f"unexpected query: {query}")


def unit(
    entity_id,
    topic,
    text,
    *,
    entity_type="segment",
    original_input_id=None,
    question_id=None,
    question_text=None,
):
    return AnalysisUnit(
        entity_type=entity_type,
        entity_id=entity_id,
        original_input_id=original_input_id or entity_id,
        text=text,
        topic=topic,
        question_id=question_id,
        question_text=question_text,
    )


def row(
    entity_id,
    topic,
    text,
    *,
    entity_type="segment",
    original_input_id=None,
    question_id=None,
    question_text=None,
):
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "original_input_id": original_input_id or entity_id,
        "text": text,
        "topic": topic,
        "question_id": question_id,
        "question_text": question_text,
    }


def new_decision(topic, name="Purchasing"):
    return ThemeDecision(
        action="new",
        proposed_name=name,
        proposed_description="Recurring purchasing concerns.",
        rationale="The topic consistently concerns purchasing.",
        topics=[topic],
    )


class ThemeWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_theme_llm_client_constructs(self):
        client = LocalThemeLLMClient(
            base_url="http://localhost:11434/v1",
            model="test-model",
            timeout_seconds=1,
        )
        await client.close()

    def test_groups_complete_membership_by_canonical_topic(self):
        clusters = build_topic_clusters(
            [
                unit(3, "Housing", "Rent keeps increasing"),
                unit(1, "housing", "Homes are unaffordable"),
                unit(2, "Transport", "More frequent bus services"),
            ]
        )

        self.assertEqual(
            [cluster.topic_name for cluster in clusters],
            ["Housing", "Transport"],
        )
        self.assertEqual(
            [member.entity_id for member in clusters[0].member_units],
            [1, 3],
        )
        self.assertEqual(clusters[0].rich_member_count, 2)

    def test_low_information_cluster_needs_three_distinct_questions(self):
        members = [
            unit(
                index,
                "Recommendation",
                "No",
                question_id=1 if index < 4 else 2,
                question_text=f"Question {1 if index < 4 else 2}",
            )
            for index in range(1, 6)
        ]
        cluster = build_topic_clusters(members)[0]

        self.assertFalse(
            is_cluster_eligible(
                cluster,
                min_rich_units=2,
                min_distinct_questions_low_info=3,
            )
        )

        members.append(
            unit(
                6,
                "Recommendation",
                "No",
                question_id=3,
                question_text="Question 3",
            )
        )
        cluster = build_topic_clusters(members)[0]
        self.assertTrue(
            is_cluster_eligible(
                cluster,
                min_rich_units=2,
                min_distinct_questions_low_info=3,
            )
        )

    def test_two_rich_members_make_cluster_eligible(self):
        cluster = build_topic_clusters(
            [
                unit(1, "Checkout", "No"),
                unit(2, "Checkout", "The payment form was confusing"),
                unit(3, "Checkout", "Checkout repeatedly lost my basket"),
            ]
        )[0]

        self.assertEqual(cluster.rich_member_count, 2)
        self.assertTrue(
            is_cluster_eligible(
                cluster,
                min_rich_units=2,
                min_distinct_questions_low_info=3,
            )
        )

    def test_full_membership_fingerprint_is_stable_and_changes_for_new_member(self):
        older_and_newer = [
            unit(1, "Cost Barriers", "The subscription costs too much"),
            unit(900, "Cost Barriers", "The price exceeds the value"),
        ]
        forward = build_topic_clusters(older_and_newer)[0]
        reverse = build_topic_clusters(list(reversed(older_and_newer)))[0]

        self.assertEqual(len(forward.member_units), 2)
        self.assertEqual(
            topic_cluster_fingerprint(forward),
            topic_cluster_fingerprint(reverse),
        )

        expanded = build_topic_clusters(
            [
                *older_and_newer,
                unit(450, "Cost Barriers", "Fees prevent me from purchasing"),
            ]
        )[0]
        self.assertNotEqual(
            topic_cluster_fingerprint(forward),
            topic_cluster_fingerprint(expanded),
        )

    def test_sample_evidence_prefers_distinct_questions_and_is_capped(self):
        cluster = build_topic_clusters(
            [
                unit(
                    1,
                    "Cost Barriers",
                    "First answer to question one",
                    question_id=1,
                    question_text="Question one",
                ),
                unit(
                    2,
                    "Cost Barriers",
                    "Second answer to question one",
                    question_id=1,
                    question_text="Question one",
                ),
                unit(
                    3,
                    "Cost Barriers",
                    "Answer to question two",
                    question_id=2,
                    question_text="Question two",
                ),
            ]
        )[0]

        self.assertEqual(
            sample_cluster_evidence(cluster, 2),
            [
                "First answer to question one",
                "Answer to question two",
            ],
        )

    async def test_cost_barriers_proposes_new_purchasing_theme(self):
        question_text = "What prevents you from purchasing?"
        connection = FakeConnection(
            candidates=[
                row(
                    20,
                    "Cost Barriers",
                    "The price is too high",
                    question_id=1,
                    question_text=question_text,
                ),
                row(
                    21,
                    "Cost Barriers",
                    "It is too expensive for the value",
                    question_id=1,
                    question_text=question_text,
                ),
                row(
                    22,
                    "Cost Barriers",
                    "Price",
                    question_id=1,
                    question_text=question_text,
                ),
            ]
        )
        suggester = FakeSuggester(new_decision("Cost Barriers"))

        saved = await process_cycle(
            FakePool(connection),
            suggester,
            sample_evidence_limit=2,
            theme_limit=20,
            min_rich_units=2,
            min_distinct_questions_low_info=3,
        )

        self.assertEqual(saved, 1)
        self.assertEqual(connection.candidate_query_values, ())
        self.assertEqual(
            suggester.contexts,
            [
                {
                    "topic": "Cost Barriers",
                    "questions": [{"question_text": question_text}],
                    "sample_evidence": [
                        "The price is too high",
                        "It is too expensive for the value",
                    ],
                    "member_count": 3,
                    "existing_themes": [],
                }
            ],
        )
        self.assertEqual(connection.suggestion_inserts[0][0], "new")
        evidence_write = next(
            values
            for query, values in connection.bulk_writes
            if "theme_suggestion_evidence" in query
        )
        self.assertEqual(len(evidence_write), 3)
        self.assertIn("pg_advisory_unlock", connection.executed[-1][0])

    async def test_checkout_friction_reuses_existing_purchasing_theme(self):
        connection = FakeConnection(
            candidates=[
                row(30, "Checkout Friction", "Checkout is hard to navigate"),
                row(31, "Checkout Friction", "Payment steps are confusing"),
            ],
            themes=[
                {
                    "id": 5,
                    "name": "Purchasing",
                    "description": "The purchasing journey.",
                    "topics": ["Cost Barriers"],
                    "relevance": 0,
                }
            ],
        )
        suggester = FakeSuggester(
            ThemeDecision(
                action="reuse",
                existing_theme_ids=[5],
                proposed_name="Purchasing Journey",
                proposed_description="Checkout concerns fit purchasing.",
                rationale="The topic concerns the purchasing flow.",
                topics=["Checkout Friction"],
            )
        )

        saved = await process_cycle(
            FakePool(connection),
            suggester,
            sample_evidence_limit=5,
            theme_limit=20,
            min_rich_units=2,
            min_distinct_questions_low_info=3,
        )

        self.assertEqual(saved, 1)
        self.assertEqual(
            suggester.contexts[0]["existing_themes"][0]["name"],
            "Purchasing",
        )
        self.assertEqual(connection.suggestion_inserts[0][0], "reuse")
        self.assertEqual(
            connection.suggestion_inserts[0][1],
            "Purchasing Journey",
        )

    async def test_new_theme_is_available_to_next_cluster_in_same_cycle(self):
        connection = FakeConnection(
            candidates=[
                row(60, "Cost Barriers", "The subscription is too expensive"),
                row(61, "Cost Barriers", "Fees stop me from buying"),
                row(62, "Checkout Friction", "Checkout is hard to navigate"),
                row(63, "Checkout Friction", "Payment steps are confusing"),
            ]
        )
        suggester = SequencedSuggester(
            [
                new_decision("Cost Barriers"),
                ThemeDecision(
                    action="reuse",
                    existing_theme_ids=[199],
                    proposed_name="Purchasing",
                    proposed_description="Checkout also concerns purchasing.",
                    rationale="Both topics concern the buying journey.",
                    topics=["Checkout Friction"],
                ),
            ]
        )

        saved = await process_cycle(
            FakePool(connection),
            suggester,
            sample_evidence_limit=5,
            theme_limit=20,
            min_rich_units=2,
            min_distinct_questions_low_info=3,
        )

        self.assertEqual(saved, 2)
        self.assertEqual(suggester.contexts[0]["existing_themes"], [])
        self.assertEqual(
            suggester.contexts[1]["existing_themes"][0]["name"],
            "Purchasing",
        )
        self.assertEqual(connection.suggestion_inserts[1][0], "reuse")

    async def test_merge_inference_uses_two_existing_themes(self):
        themes = [
            {
                "id": 7,
                "name": "Purchase Costs",
                "description": "Cost concerns.",
                "topics": ["Cost Barriers"],
                "relevance": 1,
            },
            {
                "id": 8,
                "name": "Buying Journey",
                "description": "Purchase flow concerns.",
                "topics": ["Checkout Friction"],
                "relevance": 0,
            },
        ]
        connection = FakeConnection(
            candidates=[
                row(40, "Purchasing Problems", "Buying is too expensive"),
                row(41, "Purchasing Problems", "Buying takes too many steps"),
            ],
            themes=themes,
        )
        suggester = FakeSuggester(
            ThemeDecision(
                action="merge",
                existing_theme_ids=[7, 8],
                proposed_name="Purchasing",
                proposed_description="Cost and flow barriers to purchasing.",
                rationale="Both existing themes concern purchasing.",
                topics=["Purchasing Problems"],
            )
        )

        saved = await process_cycle(
            FakePool(connection),
            suggester,
            sample_evidence_limit=5,
            theme_limit=20,
            min_rich_units=2,
            min_distinct_questions_low_info=3,
        )

        self.assertEqual(saved, 1)
        self.assertEqual(
            [theme["id"] for theme in suggester.contexts[0]["existing_themes"]],
            [7, 8],
        )
        self.assertEqual(
            suggester.contexts[0]["topic"],
            "Purchasing Problems",
        )

    async def test_cycle_skips_when_another_instance_holds_lock(self):
        connection = FakeConnection(locked=False)
        suggester = FakeSuggester(new_decision("Unused", "Unused"))

        saved = await process_cycle(
            FakePool(connection),
            suggester,
            sample_evidence_limit=5,
            theme_limit=20,
            min_rich_units=2,
            min_distinct_questions_low_info=3,
        )

        self.assertEqual(saved, 0)
        self.assertEqual(suggester.contexts, [])

    async def test_rejects_topics_outside_cluster(self):
        connection = FakeConnection(
            candidates=[
                row(50, "Housing", "Homes are unaffordable"),
                row(51, "Housing", "Rent increases every year"),
            ]
        )
        suggester = FakeSuggester(new_decision("Transport", "Housing Pressure"))

        with self.assertRaisesRegex(ValueError, "outside the evidence"):
            await process_cycle(
                FakePool(connection),
                suggester,
                sample_evidence_limit=5,
                theme_limit=20,
                min_rich_units=2,
                min_distinct_questions_low_info=3,
            )

        self.assertEqual(connection.suggestion_inserts, [])
        self.assertIn("pg_advisory_unlock", connection.executed[-1][0])

    async def test_new_suggestion_materializes_theme_and_topic_link(self):
        connection = MaterializationConnection(
            suggestions=[
                {
                    "id": 10,
                    "action": "new",
                    "proposed_name": "Purchasing",
                    "proposed_description": "Purchasing concerns.",
                    "existing_theme_ids": [],
                    "topics": ["Cost Barriers"],
                    "materialized_at": None,
                }
            ]
        )

        count = await materialize_pending_suggestions(connection)

        self.assertEqual(count, 1)
        suggestion = connection.suggestions[10]
        theme_id = suggestion["materialized_theme_id"]
        self.assertEqual(connection.themes[theme_id]["name"], "Purchasing")
        self.assertIn((theme_id, "Cost Barriers"), connection.topics)
        self.assertEqual(suggestion["materialized_at"], "now")

    async def test_pending_replay_is_idempotent(self):
        connection = MaterializationConnection(
            suggestions=[
                {
                    "id": 11,
                    "action": "new",
                    "proposed_name": "Service",
                    "proposed_description": "Service concerns.",
                    "existing_theme_ids": [],
                    "topics": ["Staff Helpfulness"],
                    "materialized_at": None,
                }
            ]
        )

        first = await materialize_pending_suggestions(connection)
        second = await materialize_pending_suggestions(connection)

        self.assertEqual((first, second), (1, 0))
        self.assertEqual(len(connection.themes), 1)
        self.assertEqual(
            connection.topics,
            {(1, "Staff Helpfulness")},
        )

    async def test_new_name_collision_becomes_effective_reuse(self):
        connection = MaterializationConnection(
            themes=[
                {
                    "id": 4,
                    "name": "Purchasing",
                    "description": "Existing description.",
                }
            ],
            topics={(4, "Cost Barriers")},
        )

        theme_id = await _materialize_suggestion(
            connection,
            StoredThemeSuggestion(
                id=12,
                action="new",
                proposed_name="purchasing",
                proposed_description="Ignored duplicate description.",
                existing_theme_ids=(),
                topics=("Checkout Friction",),
            ),
        )

        self.assertEqual(theme_id, 4)
        self.assertEqual(
            connection.themes[4]["description"],
            "Existing description.",
        )
        self.assertEqual(
            connection.topics,
            {(4, "Cost Barriers"), (4, "Checkout Friction")},
        )

    async def test_update_changes_live_theme_and_keeps_other_links(self):
        connection = MaterializationConnection(
            themes=[
                {
                    "id": 5,
                    "name": "Buying",
                    "description": "Old description.",
                }
            ],
            topics={(5, "Cost Barriers"), (8, "Cost Barriers")},
        )

        await _materialize_suggestion(
            connection,
            StoredThemeSuggestion(
                id=13,
                action="update",
                proposed_name="Purchasing",
                proposed_description="Updated purchasing concerns.",
                existing_theme_ids=(5,),
                topics=("Checkout Friction",),
            ),
        )

        self.assertEqual(connection.themes[5]["name"], "Purchasing")
        self.assertEqual(
            connection.themes[5]["description"],
            "Updated purchasing concerns.",
        )
        self.assertIn((5, "Checkout Friction"), connection.topics)
        self.assertIn((8, "Cost Barriers"), connection.topics)

    async def test_merge_moves_topics_and_path_compresses_aliases(self):
        connection = MaterializationConnection(
            themes=[
                {
                    "id": 1,
                    "name": "Customer Experience",
                    "description": "Canonical.",
                },
                {
                    "id": 2,
                    "name": "Buying Journey",
                    "description": "To merge.",
                },
                {
                    "id": 3,
                    "name": "Old Buying Alias",
                    "description": "Existing alias.",
                    "merged_into_id": 2,
                },
            ],
            topics={(1, "Service"), (2, "Checkout Friction")},
        )

        theme_id = await _materialize_suggestion(
            connection,
            StoredThemeSuggestion(
                id=14,
                action="merge",
                proposed_name="Buying Journey",
                proposed_description="The complete purchasing experience.",
                existing_theme_ids=(2, 1),
                topics=("Cost Barriers",),
            ),
        )

        self.assertEqual(theme_id, 1)
        self.assertEqual(connection.themes[2]["merged_into_id"], 1)
        self.assertEqual(connection.themes[3]["merged_into_id"], 1)
        self.assertEqual(
            connection.themes[1]["name"],
            "Buying Journey",
        )
        self.assertEqual(
            connection.themes[2]["name"],
            "Buying Journey [merged #2]",
        )
        self.assertEqual(
            connection.topics,
            {
                (1, "Service"),
                (1, "Checkout Friction"),
                (1, "Cost Barriers"),
            },
        )

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
