import asyncio
import copy
import unittest
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import Any

import httpx

from triage_processor.api.main import app


class ApiStructureTests(unittest.TestCase):
    def test_inputs_route_is_registered(self):
        self.assertIn("/inputs", app.openapi()["paths"])


class FakeDatabase:
    def __init__(self) -> None:
        self.questions: dict[tuple[Any, ...], dict[str, Any]] = {}
        self.inputs: list[dict[str, Any]] = []
        self.next_question_id = 1
        self.next_input_id = 1
        self.segments: list[dict[str, Any]] = []
        self.themes: dict[int, dict[str, Any]] = {}
        self.theme_topics: set[tuple[int, str]] = set()
        self.last_list_query: str | None = None
        self.last_list_args: tuple[Any, ...] | None = None
        self.transaction_entries = 0
        self.fail_input_insert = False
        self.simulate_question_insert_race = False
        self._lock = asyncio.Lock()


class FakeTransaction(AbstractAsyncContextManager[None]):
    def __init__(self, database: FakeDatabase) -> None:
        self.database = database
        self.snapshot: tuple[Any, ...] | None = None

    async def __aenter__(self) -> None:
        await self.database._lock.acquire()
        self.database.transaction_entries += 1
        self.snapshot = (
            copy.deepcopy(self.database.questions),
            copy.deepcopy(self.database.inputs),
            self.database.next_question_id,
            self.database.next_input_id,
        )

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        if exc_type is not None:
            assert self.snapshot is not None
            (
                self.database.questions,
                self.database.inputs,
                self.database.next_question_id,
                self.database.next_input_id,
            ) = self.snapshot
        self.database._lock.release()


class FakeConnection:
    def __init__(self, database: FakeDatabase) -> None:
        self.database = database

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self.database)

    def _question_for_input(
        self,
        input_row: dict[str, Any],
    ) -> tuple[str, dict[str, Any]] | None:
        for identity, question in self.database.questions.items():
            if question["id"] == input_row["question_id"]:
                return identity[0], question
        return None

    def _canonical_theme_id(self, theme_id: int) -> int:
        seen: set[int] = set()
        while self.database.themes[theme_id]["merged_into_id"] is not None:
            if theme_id in seen:
                raise AssertionError("theme merge cycle in fake database")
            seen.add(theme_id)
            theme_id = self.database.themes[theme_id]["merged_into_id"]
        return theme_id

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        statement = " ".join(query.split())
        if not statement.startswith("WITH RECURSIVE theme_paths"):
            raise AssertionError(f"Unexpected SQL: {statement}")

        self.database.last_list_query = statement
        self.database.last_list_args = args
        (
            source,
            form_key,
            question_key,
            question_version,
            submission_key,
            offset,
            limit,
        ) = args
        matches: list[dict[str, Any]] = []
        for input_row in sorted(
            self.database.inputs,
            key=lambda item: item["id"],
        ):
            resolved = self._question_for_input(input_row)
            question_source = resolved[0] if resolved is not None else None
            question = resolved[1] if resolved is not None else None
            if source is not None and question_source != source:
                continue
            if (
                form_key is not None
                and (
                    question is None
                    or question["form_key"] != form_key
                )
            ):
                continue
            if (
                question_key is not None
                and (
                    question is None
                    or question["question_key"] != question_key
                )
            ):
                continue
            if (
                question_version is not None
                and (
                    question is None
                    or question["question_version"] != question_version
                )
            ):
                continue
            if (
                submission_key is not None
                and input_row["submission_key"] != submission_key
            ):
                continue

            topics = {
                input_row["topic"]
            } if input_row["topic"] is not None else set()
            topics.update(
                segment["topic"]
                for segment in self.database.segments
                if segment["original_input_id"] == input_row["id"]
                and segment["topic"] is not None
            )
            canonical_ids = {
                self._canonical_theme_id(theme_id)
                for theme_id, topic in self.database.theme_topics
                if any(topic.casefold() == item.casefold() for item in topics)
            }
            themes = [
                {
                    "id": theme_id,
                    "name": self.database.themes[theme_id]["name"],
                    "description": self.database.themes[theme_id][
                        "description"
                    ],
                }
                for theme_id in sorted(
                    canonical_ids,
                    key=lambda item: (
                        self.database.themes[item]["name"].casefold(),
                        item,
                    ),
                )
            ]
            matches.append(
                {
                    **copy.deepcopy(input_row),
                    "form_key": (
                        question["form_key"] if question is not None else None
                    ),
                    "question_key": (
                        question["question_key"]
                        if question is not None
                        else None
                    ),
                    "question_version": (
                        question["question_version"]
                        if question is not None
                        else None
                    ),
                    "question_text": (
                        question["question_text"]
                        if question is not None
                        else None
                    ),
                    "themes": themes,
                }
            )
        return matches[offset : offset + limit]

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        statement = " ".join(query.split())

        if statement.startswith("SELECT") and "FROM questions" in statement:
            identity = tuple(args[:4])
            row = self.database.questions.get(identity)
            return copy.deepcopy(row)

        if statement.startswith("INSERT INTO questions"):
            identity = tuple(args[:4])
            existing = self.database.questions.get(identity)
            if existing is not None:
                return None

            row = {
                "id": self.database.next_question_id,
                "form_key": args[1],
                "question_key": args[2],
                "question_version": args[3],
                "question_text": args[4],
            }
            self.database.next_question_id += 1
            self.database.questions[identity] = row

            if self.database.simulate_question_insert_race:
                self.database.simulate_question_insert_race = False
                return None
            return copy.deepcopy(row)

        if statement.startswith("INSERT INTO original_inputs"):
            if self.database.fail_input_insert:
                raise RuntimeError("simulated original_inputs constraint failure")

            row = {
                "id": self.database.next_input_id,
                "original_text": args[0],
                "source": args[1],
                "status": "new",
                "topic": None,
                "question_id": args[2],
                "submission_key": args[3],
                "created_at": datetime.now(UTC),
            }
            self.database.next_input_id += 1
            self.database.inputs.append(row)
            return copy.deepcopy(row)

        raise AssertionError(f"Unexpected SQL: {statement}")


class FakeAcquire(AbstractAsyncContextManager[FakeConnection]):
    def __init__(self, database: FakeDatabase) -> None:
        self.connection = FakeConnection(database)

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        return None


class FakePool:
    def __init__(self, database: FakeDatabase) -> None:
        self.database = database

    def acquire(self) -> FakeAcquire:
        return FakeAcquire(self.database)


class InputApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = FakeDatabase()
        app.state.db_pool = FakePool(self.database)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    @staticmethod
    def contextual_payload(**overrides: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "original_text": "Price",
            "source": "customer-survey",
            "submission_key": "response-4832",
            "question_context": {
                "form_key": "quarterly-survey",
                "question_key": "purchase-barrier",
                "question_text": (
                    "What is the biggest barrier preventing you from "
                    "purchasing?"
                ),
            },
        }
        payload.update(overrides)
        return payload

    async def test_generic_payload_remains_supported(self) -> None:
        response = await self.client.post(
            "/inputs",
            json={"original_text": "A generic comment", "source": "manual"},
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["original_text"], "A generic comment")
        self.assertEqual(body["status"], "new")
        self.assertIsNone(body["question_id"])
        self.assertIsNone(body["question_context"])
        self.assertIsNone(body["submission_key"])
        self.assertEqual(body["themes"], [])
        self.assertEqual(self.database.transaction_entries, 1)

    async def test_contextual_payload_creates_and_reuses_question(self) -> None:
        first_response = await self.client.post(
            "/inputs",
            json=self.contextual_payload(),
        )
        second_response = await self.client.post(
            "/inputs",
            json=self.contextual_payload(original_text="Too expensive"),
        )

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 201)
        first_body = first_response.json()
        second_body = second_response.json()
        self.assertEqual(first_body["question_id"], second_body["question_id"])
        self.assertEqual(first_body["question_context"]["question_version"], 1)
        self.assertEqual(
            first_body["question_context"],
            second_body["question_context"],
        )
        self.assertEqual(len(self.database.questions), 1)
        self.assertEqual(len(self.database.inputs), 2)

    async def test_conflicting_question_text_returns_409(self) -> None:
        first_response = await self.client.post(
            "/inputs",
            json=self.contextual_payload(),
        )
        conflicting = self.contextual_payload()
        conflicting["question_context"]["question_text"] = "Different text"
        second_response = await self.client.post("/inputs", json=conflicting)

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 409)
        self.assertIn("question_version", second_response.json()["detail"])
        self.assertEqual(len(self.database.questions), 1)
        self.assertEqual(len(self.database.inputs), 1)

    async def test_insert_conflict_falls_back_to_existing_question(self) -> None:
        self.database.simulate_question_insert_race = True

        response = await self.client.post(
            "/inputs",
            json=self.contextual_payload(),
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["question_id"], 1)
        self.assertEqual(len(self.database.questions), 1)

    async def test_simultaneous_submissions_create_one_question(self) -> None:
        responses = await asyncio.gather(
            *[
                self.client.post(
                    "/inputs",
                    json=self.contextual_payload(
                        original_text=f"Answer {index}",
                    ),
                )
                for index in range(20)
            ]
        )

        self.assertTrue(
            all(response.status_code == 201 for response in responses)
        )
        self.assertEqual(len(self.database.questions), 1)
        self.assertEqual(len(self.database.inputs), 20)
        self.assertEqual(
            {response.json()["question_id"] for response in responses},
            {1},
        )

    async def test_input_failure_rolls_back_new_question(self) -> None:
        self.database.fail_input_insert = True
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=app,
                raise_app_exceptions=False,
            ),
            base_url="http://test",
        )
        self.addAsyncCleanup(client.aclose)

        response = await client.post(
            "/inputs",
            json=self.contextual_payload(),
        )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.database.questions, {})
        self.assertEqual(self.database.inputs, [])

    async def test_submission_key_without_context_returns_422(self) -> None:
        response = await self.client.post(
            "/inputs",
            json={
                "original_text": "Price",
                "source": "customer-survey",
                "submission_key": "response-4832",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.database.transaction_entries, 0)

    async def test_partial_question_context_returns_422(self) -> None:
        response = await self.client.post(
            "/inputs",
            json={
                "original_text": "Price",
                "source": "customer-survey",
                "question_context": {
                    "form_key": "quarterly-survey",
                    "question_key": "purchase-barrier",
                },
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.database.transaction_entries, 0)

    async def test_lists_all_answers_for_form_and_submission(self) -> None:
        first = self.contextual_payload(original_text="Price")
        second = self.contextual_payload(original_text="Availability")
        second["question_context"] = {
            "form_key": "quarterly-survey",
            "question_key": "stock-barrier",
            "question_text": "What else prevented your purchase?",
        }
        other_form = self.contextual_payload(original_text="Other form")
        other_form["question_context"] = {
            "form_key": "annual-survey",
            "question_key": "purchase-barrier",
            "question_text": "What prevented your annual purchase?",
        }
        for payload in (first, second, other_form):
            response = await self.client.post("/inputs", json=payload)
            self.assertEqual(response.status_code, 201)

        response = await self.client.get(
            "/inputs",
            params={
                "source": "customer-survey",
                "form_key": "quarterly-survey",
                "submission_key": "response-4832",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["original_text"] for item in response.json()],
            ["Price", "Availability"],
        )
        self.assertEqual(
            {
                item["question_context"]["question_key"]
                for item in response.json()
            },
            {"purchase-barrier", "stock-barrier"},
        )

    async def test_question_filter_matches_all_versions_or_one_version(
        self,
    ) -> None:
        version_one = self.contextual_payload(original_text="Version one")
        version_two = self.contextual_payload(original_text="Version two")
        version_two["question_context"] = {
            **version_two["question_context"],
            "question_version": 2,
            "question_text": "Updated purchasing barrier question?",
        }
        for payload in (version_one, version_two):
            response = await self.client.post("/inputs", json=payload)
            self.assertEqual(response.status_code, 201)

        base_params = {
            "source": "customer-survey",
            "form_key": "quarterly-survey",
            "question_key": "purchase-barrier",
        }
        all_versions = await self.client.get(
            "/inputs",
            params=base_params,
        )
        version_two_only = await self.client.get(
            "/inputs",
            params={**base_params, "question_version": 2},
        )

        self.assertEqual(all_versions.status_code, 200)
        self.assertEqual(len(all_versions.json()), 2)
        self.assertEqual(
            [
                item["question_context"]["question_version"]
                for item in version_two_only.json()
            ],
            [2],
        )

    async def test_returns_all_deduplicated_canonical_themes(self) -> None:
        created = await self.client.post(
            "/inputs",
            json=self.contextual_payload(),
        )
        input_id = created.json()["id"]
        self.database.inputs[0]["status"] = "completed"
        self.database.segments.extend(
            [
                {
                    "original_input_id": input_id,
                    "topic": "Cost Barriers",
                },
                {
                    "original_input_id": input_id,
                    "topic": "Checkout Friction",
                },
            ]
        )
        self.database.themes = {
            1: {
                "name": "Purchasing",
                "description": "Purchasing concerns.",
                "merged_into_id": None,
            },
            2: {
                "name": "Old Purchasing",
                "description": "Merged alias.",
                "merged_into_id": 1,
            },
            3: {
                "name": "Digital Experience",
                "description": "Digital journey concerns.",
                "merged_into_id": None,
            },
        }
        self.database.theme_topics = {
            (1, "Cost Barriers"),
            (2, "Cost Barriers"),
            (3, "Checkout Friction"),
        }

        response = await self.client.get(
            "/inputs",
            params={
                "source": "customer-survey",
                "form_key": "quarterly-survey",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()[0]
        self.assertEqual(body["status"], "completed")
        self.assertEqual(
            [(theme["id"], theme["name"]) for theme in body["themes"]],
            [
                (3, "Digital Experience"),
                (1, "Purchasing"),
            ],
        )
        self.assertIn(
            "FROM segment_inputs AS segments",
            self.database.last_list_query,
        )
        self.assertIn(
            "SELECT DISTINCT canonical.id",
            self.database.last_list_query,
        )

    async def test_retrieval_scope_parameters_require_source_and_form(
        self,
    ) -> None:
        invalid_params = [
            {"question_key": "purchase-barrier"},
            {"submission_key": "response-4832"},
            {
                "source": "customer-survey",
                "question_key": "purchase-barrier",
            },
            {
                "form_key": "quarterly-survey",
                "submission_key": "response-4832",
            },
            {"question_version": 1},
        ]

        for params in invalid_params:
            with self.subTest(params=params):
                response = await self.client.get(
                    "/inputs",
                    params=params,
                )
                self.assertEqual(response.status_code, 422)

    async def test_offset_limit_pagination_is_validated_and_bounded(
        self,
    ) -> None:
        for index in range(3):
            response = await self.client.post(
                "/inputs",
                json={
                    "original_text": f"Generic {index}",
                    "source": "manual",
                },
            )
            self.assertEqual(response.status_code, 201)

        page = await self.client.get(
            "/inputs",
            params={"offset": 1, "limit": 1},
        )

        self.assertEqual(page.status_code, 200)
        self.assertEqual(
            [item["original_text"] for item in page.json()],
            ["Generic 1"],
        )
        self.assertEqual(self.database.last_list_args[-2:], (1, 1))

        for params in (
            {"offset": -1},
            {"offset": 100_001},
            {"limit": 0},
            {"limit": 101},
        ):
            with self.subTest(params=params):
                response = await self.client.get(
                    "/inputs",
                    params=params,
                )
                self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
