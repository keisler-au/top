import hashlib
import unittest
from dataclasses import dataclass

from triage_processor.api.schemas import InputCreate
from triage_processor.workers.eligibility_segmentation import (
    SegmentationDecision,
)
from triage_processor.workers.embeddings import build_embedding_input
from triage_processor.workers.themes import (
    AnalysisUnit,
    StoredThemeSuggestion,
    _materialize_suggestion,
    build_topic_clusters,
    is_cluster_eligible,
)
from triage_processor.workers.topics import TopicChoice, TopicDecision


@dataclass(frozen=True)
class PipelineFixture:
    answer: str
    topic: str
    form_key: str | None = None
    question_key: str | None = None
    question_text: str | None = None
    submission_key: str | None = None


FIXTURES = (
    PipelineFixture(
        answer="Price",
        topic="Cost Barriers",
        form_key="purchase-journey",
        question_key="purchase-barrier",
        question_text="What prevents you from purchasing?",
        submission_key="response-4832",
    ),
    PipelineFixture(
        answer=(
            "The subscription costs more than the value it provides, "
            "especially after the latest price increase."
        ),
        topic="Cost Barriers",
        form_key="purchase-journey",
        question_key="purchase-barrier",
        question_text="What prevents you from purchasing?",
        submission_key="response-4833",
    ),
    PipelineFixture(
        answer="The fees are too high for our small organisation.",
        topic="Cost Barriers",
        form_key="purchase-journey",
        question_key="purchase-barrier",
        question_text="What prevents you from purchasing?",
        submission_key="response-4834",
    ),
    PipelineFixture(
        answer="No",
        topic="Recommendations",
        form_key="closed-answers",
        question_key="recommend",
        question_text="Would you recommend this product?",
        submission_key="closed-response-1",
    ),
    PipelineFixture(
        answer="No",
        topic="Marketing Consent",
        form_key="closed-answers",
        question_key="marketing-consent",
        question_text="May we send you marketing messages?",
        submission_key="closed-response-2",
    ),
    PipelineFixture(
        answer="Checkout repeatedly loses the contents of my basket.",
        topic="Checkout Friction",
        form_key="purchase-journey",
        question_key="checkout-improvement",
        question_text="What made completing your order difficult?",
        submission_key="response-4832",
    ),
    PipelineFixture(
        answer="The payment steps are confusing and take too long.",
        topic="Checkout Friction",
        form_key="purchase-journey",
        question_key="checkout-improvement",
        question_text="How could we improve the checkout experience?",
        submission_key="response-4835",
    ),
    PipelineFixture(
        answer="The support team explained the setup clearly.",
        topic="Support Experience",
    ),
)


class ThemeStateConnection:
    def __init__(self) -> None:
        self.themes: dict[int, dict[str, object]] = {}
        self.theme_topics: set[tuple[int, str]] = set()
        self.materialized: dict[int, int] = {}
        self.next_theme_id = 1

    async def fetch(self, query, *values):
        if "WITH RECURSIVE theme_paths" not in query:
            raise AssertionError(f"unexpected query: {query}")
        return [
            {"starting_id": theme_id, "root_id": theme_id}
            for theme_id in values[0]
        ]

    async def fetchrow(self, query, *values):
        if "INSERT INTO themes" not in query:
            raise AssertionError(f"unexpected query: {query}")
        existing_id = next(
            (
                theme_id
                for theme_id, theme in self.themes.items()
                if str(theme["name"]).casefold() == values[0].casefold()
            ),
            None,
        )
        if existing_id is not None:
            return None
        theme_id = self.next_theme_id
        self.next_theme_id += 1
        self.themes[theme_id] = {
            "name": values[0],
            "description": values[1],
            "merged_into_id": None,
        }
        return {"id": theme_id}

    async def fetchval(self, query, *values):
        if "lower(name) = lower($1)" not in query:
            raise AssertionError(f"unexpected query: {query}")
        return next(
            (
                theme_id
                for theme_id, theme in self.themes.items()
                if theme["merged_into_id"] is None
                and str(theme["name"]).casefold() == values[0].casefold()
            ),
            None,
        )

    async def executemany(self, query, values):
        if "INSERT INTO theme_topics" not in query:
            raise AssertionError(f"unexpected query: {query}")
        self.theme_topics.update(values)

    async def execute(self, query, *values):
        if "UPDATE theme_suggestions" in query:
            self.materialized[values[0]] = values[1]
            return
        if "UPDATE themes" in query:
            return
        raise AssertionError(f"unexpected query: {query}")


def deterministic_embedding(text: str) -> tuple[float, ...]:
    digest = hashlib.sha256(text.encode()).digest()
    return tuple(component / 255 for component in digest[:8])


class ContextualPipelineFixtureTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixtures_cross_every_pipeline_stage(self) -> None:
        units: list[AnalysisUnit] = []
        embedded: dict[int, tuple[float, ...]] = {}
        payloads: list[InputCreate] = []

        for input_id, fixture in enumerate(FIXTURES, start=1):
            question_context = (
                {
                    "form_key": fixture.form_key,
                    "question_key": fixture.question_key,
                    "question_text": fixture.question_text,
                }
                if fixture.question_text is not None
                else None
            )
            payload = InputCreate.model_validate(
                {
                    "original_text": fixture.answer,
                    "source": "pipeline-fixtures",
                    "submission_key": fixture.submission_key,
                    "question_context": question_context,
                }
            )
            payloads.append(payload)

            eligibility = SegmentationDecision(
                eligible=True,
                segments=[],
            )
            self.assertTrue(eligibility.eligible)

            embedding_text = build_embedding_input(
                answer_text=payload.original_text,
                question_text=(
                    payload.question_context.question_text
                    if payload.question_context is not None
                    else None
                ),
            )
            embedded[input_id] = deterministic_embedding(embedding_text)

            topic_decision = TopicDecision(
                original_topic=TopicChoice(
                    name=fixture.topic,
                    reused_existing=False,
                )
            )
            units.append(
                AnalysisUnit(
                    entity_type="original",
                    entity_id=input_id,
                    original_input_id=input_id,
                    text=payload.original_text,
                    topic=topic_decision.original_topic.name,
                    question_id=(
                        input_id
                        if payload.question_context is not None
                        else None
                    ),
                    question_text=(
                        payload.question_context.question_text
                        if payload.question_context is not None
                        else None
                    ),
                )
            )

        no_answer_ids = [
            index
            for index, fixture in enumerate(FIXTURES, start=1)
            if fixture.answer == "No"
        ]
        self.assertEqual(len(no_answer_ids), 2)
        self.assertNotEqual(
            embedded[no_answer_ids[0]],
            embedded[no_answer_ids[1]],
        )
        self.assertEqual(
            build_embedding_input(
                answer_text=payloads[-1].original_text,
                question_text=None,
            ),
            payloads[-1].original_text,
        )
        self.assertEqual(
            sum(
                payload.submission_key == "response-4832"
                for payload in payloads
            ),
            2,
        )

        clusters = {
            cluster.topic_name: cluster
            for cluster in build_topic_clusters(units)
        }
        self.assertTrue(
            is_cluster_eligible(
                clusters["Cost Barriers"],
                min_rich_units=2,
                min_distinct_questions_low_info=3,
            )
        )
        self.assertTrue(
            is_cluster_eligible(
                clusters["Checkout Friction"],
                min_rich_units=2,
                min_distinct_questions_low_info=3,
            )
        )
        self.assertIn("Support Experience", clusters)

        connection = ThemeStateConnection()
        purchasing_id = await _materialize_suggestion(
            connection,
            StoredThemeSuggestion(
                id=1,
                action="new",
                proposed_name="Purchasing",
                proposed_description="Barriers across the purchasing journey.",
                existing_theme_ids=(),
                topics=("Cost Barriers",),
            ),
        )
        reused_id = await _materialize_suggestion(
            connection,
            StoredThemeSuggestion(
                id=2,
                action="reuse",
                proposed_name="Purchasing",
                proposed_description="Checkout is part of purchasing.",
                existing_theme_ids=(purchasing_id,),
                topics=("Checkout Friction",),
            ),
        )

        self.assertEqual(reused_id, purchasing_id)
        self.assertEqual(
            connection.theme_topics,
            {
                (purchasing_id, "Cost Barriers"),
                (purchasing_id, "Checkout Friction"),
            },
        )
        self.assertEqual(
            connection.materialized,
            {1: purchasing_id, 2: purchasing_id},
        )
        self.assertEqual(
            connection.themes[purchasing_id]["name"],
            "Purchasing",
        )


if __name__ == "__main__":
    unittest.main()
