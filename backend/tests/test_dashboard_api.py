import unittest
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import Any

import httpx

from triage_processor.api.dashboard_queries import (
    CANONICAL_EVIDENCE_CTE,
    recommendation_query,
    taxonomy_list_query,
)
from triage_processor.api.main import app


class StubDashboardConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.taxonomy_rows: list[dict[str, Any]] = [
            {
                "key": "cost barriers",
                "name": "Cost Barriers",
                "description": None,
                "evidence_count": 12,
                "article_count": 0,
                "approved_article_count": 0,
            }
        ]
        self.detail_row: dict[str, Any] | None = self.taxonomy_rows[0]
        self.evidence_rows: list[dict[str, Any]] = [
            {
                "id": "segment:8",
                "type": "segment",
                "excerpt": "The subscription costs too much.",
                "original_text": (
                    "The subscription costs too much and checkout is slow."
                ),
                "original_input_id": 4,
                "segment_order": 0,
                "topic_key": "cost barriers",
                "topic_name": "Cost Barriers",
                "source": "google-sheets",
                "submission_key": "form-source:2:row:7",
                "source_record_key": "form-source:2:row:7:column:3",
                "created_at": datetime(2026, 8, 24, tzinfo=UTC),
                "form_key": "feedback",
                "form_id": "feedback",
                "question_key": "header-price",
                "question_version": 1,
                "question_text": "What prevents you from subscribing?",
            }
        ]

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        self.calls.append((query, args))
        if "dashboard:summary" in query:
            return {
                "evidence_count": 14,
                "theme_count": 3,
                "topic_count": 5,
                "article_count": 0,
                "awaiting_approval_count": 0,
                "failed_generation_count": 0,
            }
        if "dashboard:taxonomy-detail" in query:
            return self.detail_row
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fetchval(self, query: str, *args: Any) -> int:
        self.calls.append((query, args))
        if "dashboard:taxonomy-count" in query:
            return len(self.taxonomy_rows)
        if "dashboard:evidence-count" in query:
            return len(self.evidence_rows)
        raise AssertionError(f"unexpected fetchval query: {query}")

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        self.calls.append((query, args))
        if "dashboard:taxonomy-list" in query:
            return self.taxonomy_rows
        if "dashboard:evidence-list" in query:
            return self.evidence_rows
        if "dashboard:recommendations" in query:
            return self.taxonomy_rows
        raise AssertionError(f"unexpected fetch query: {query}")


class StubAcquire(AbstractAsyncContextManager[StubDashboardConnection]):
    def __init__(self, connection: StubDashboardConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> StubDashboardConnection:
        return self.connection

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        return None


class StubDashboardPool:
    def __init__(self, connection: StubDashboardConnection) -> None:
        self.connection = connection

    def acquire(self) -> StubAcquire:
        return StubAcquire(self.connection)


class DashboardApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.connection = StubDashboardConnection()
        app.state.db_pool = StubDashboardPool(self.connection)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    async def test_dashboard_routes_are_registered(self) -> None:
        paths = app.openapi()["paths"]
        self.assertIn("/dashboard/summary", paths)
        self.assertIn("/taxonomy", paths)
        self.assertIn("/taxonomy/{taxonomy_type}/{taxonomy_key}", paths)
        self.assertIn(
            "/taxonomy/{taxonomy_type}/{taxonomy_key}/evidence",
            paths,
        )
        self.assertIn("/recommendations/articles", paths)

    async def test_summary_returns_taxonomy_and_article_counts(
        self,
    ) -> None:
        response = await self.client.get("/dashboard/summary")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "evidence_count": 14,
                "theme_count": 3,
                "topic_count": 5,
                "article_count": 0,
                "awaiting_approval_count": 0,
                "failed_generation_count": 0,
            },
        )

    async def test_taxonomy_list_normalizes_search_and_returns_coverage(self) -> None:
        response = await self.client.get(
            "/taxonomy",
            params={
                "type": "topic",
                "search": "  cost  ",
                "page": 2,
                "page_size": 10,
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["page"], 2)
        self.assertEqual(body["page_size"], 10)
        self.assertEqual(body["items"][0]["coverage_state"], "uncovered")
        self.assertTrue(body["items"][0]["generation_eligible"])
        count_call = next(
            call for call in self.connection.calls
            if "dashboard:taxonomy-count" in call[0]
        )
        list_call = next(
            call for call in self.connection.calls
            if "dashboard:taxonomy-list" in call[0]
        )
        self.assertEqual(count_call[1], ("cost",))
        self.assertEqual(list_call[1], ("cost", 10, 10))

    async def test_taxonomy_query_parameters_are_bounded(self) -> None:
        invalid_queries = (
            {"type": "unknown"},
            {"type": "topic", "sort": "unknown"},
            {"type": "topic", "direction": "sideways"},
            {"type": "topic", "page": 0},
            {"type": "topic", "page_size": 101},
            {"type": "topic", "page": 5000, "page_size": 25},
        )
        for params in invalid_queries:
            with self.subTest(params=params):
                response = await self.client.get("/taxonomy", params=params)
                self.assertEqual(response.status_code, 422)

    async def test_taxonomy_detail_validates_theme_key_and_returns_404(self) -> None:
        invalid = await self.client.get("/taxonomy/theme/not-a-number")
        self.assertEqual(invalid.status_code, 422)

        self.connection.detail_row = None
        missing = await self.client.get("/taxonomy/theme/99")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["detail"], "theme not found")

    async def test_url_encoded_topic_key_may_contain_a_slash(self) -> None:
        response = await self.client.get("/taxonomy/topic/cost%2Fbenefit")

        self.assertEqual(response.status_code, 200)
        detail_call = next(
            call for call in self.connection.calls
            if "dashboard:taxonomy-detail:topic" in call[0]
        )
        self.assertEqual(detail_call[1], ("cost/benefit",))

    async def test_evidence_exposes_segment_and_untouched_original(self) -> None:
        response = await self.client.get(
            "/taxonomy/topic/cost%20barriers/evidence",
        )

        self.assertEqual(response.status_code, 200)
        item = response.json()["items"][0]
        self.assertEqual(item["id"], "segment:8")
        self.assertEqual(item["type"], "segment")
        self.assertNotEqual(item["excerpt"], item["original_text"])
        self.assertEqual(item["question_context"]["form_id"], "feedback")

    async def test_recommendation_contains_explanation(self) -> None:
        response = await self.client.get(
            "/recommendations/articles",
            params={"type": "topic", "strategy": "least-covered"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["strategy"], "least-covered")
        self.assertEqual(
            body["items"][0]["explanation"],
            "Recommended because it has 0 approved articles for 12 evidence "
            "items.",
        )


class DashboardQueryContractTests(unittest.TestCase):
    def test_canonical_evidence_excludes_split_originals(self) -> None:
        self.assertIn("FROM segment_inputs AS segments", CANONICAL_EVIDENCE_CTE)
        self.assertIn("AND NOT EXISTS", CANONICAL_EVIDENCE_CTE)
        self.assertIn("inputs.status = 'completed'", CANONICAL_EVIDENCE_CTE)
        self.assertIn("'segment:' || segments.id::text", CANONICAL_EVIDENCE_CTE)
        self.assertIn("'original:' || inputs.id::text", CANONICAL_EVIDENCE_CTE)

    def test_taxonomy_order_uses_fixed_deterministic_tie_breakers(self) -> None:
        query = taxonomy_list_query(
            "topic",
            sort="evidence",
            direction="desc",
        )
        self.assertIn(
            "ORDER BY evidence_count DESC, lower(name) ASC, key ASC",
            query,
        )

    def test_recommendation_orders_match_product_contract(self) -> None:
        most = recommendation_query("topic", "most-evidence")
        least = recommendation_query("theme", "least-covered")
        self.assertIn(
            "evidence_count DESC, approved_article_count ASC, article_count ASC",
            most,
        )
        self.assertIn(
            "approved_article_count ASC, article_count ASC, evidence_count DESC",
            least,
        )
        self.assertIn("WHERE evidence_count > 0", most)


if __name__ == "__main__":
    unittest.main()
