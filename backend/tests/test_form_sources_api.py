import copy
import unittest
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import Any

import httpx

from triage_processor.api.form_source_schemas import normalize_spreadsheet_id
from triage_processor.api.main import app


class FakeFormSourceConnection:
    def __init__(self) -> None:
        self.sources: list[dict[str, Any]] = []
        self.next_id = 1

    async def fetchval(self, query: str, *args: Any) -> int:
        if "count(*)::bigint FROM form_sources" not in query:
            raise AssertionError(f"unexpected fetchval query: {query}")
        return len(self.sources)

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        if "FROM form_sources" not in query or "OFFSET $1" not in query:
            raise AssertionError(f"unexpected fetch query: {query}")
        offset, limit = args
        return copy.deepcopy(self.sources[offset : offset + limit])

    async def fetchrow(
        self,
        query: str,
        *args: Any,
    ) -> dict[str, Any] | None:
        statement = " ".join(query.split())
        if "AND ($4::bigint IS NULL OR id <> $4)" in statement:
            form_id, spreadsheet_id, sheet_name, exclude_id = args
            return copy.deepcopy(
                next(
                    (
                        source
                        for source in self.sources
                        if source["id"] != exclude_id
                        and (
                            source["form_id"] == form_id
                            or (
                                source["spreadsheet_id"] == spreadsheet_id
                                and source["sheet_name"] == sheet_name
                            )
                        )
                    ),
                    None,
                )
            )

        if statement.startswith("INSERT INTO form_sources"):
            now = datetime.now(UTC)
            row = {
                "id": self.next_id,
                "source": "google-sheets",
                "form_id": args[0],
                "spreadsheet_id": args[1],
                "sheet_name": args[2],
                "ignored_headers": list(args[3]),
                "poll_interval_seconds": args[4],
                "enabled": args[5],
                "last_read_row": 1,
                "next_poll_at": now,
                "last_polled_at": None,
                "last_error": None,
                "created_at": now,
                "updated_at": now,
            }
            self.next_id += 1
            self.sources.append(row)
            return copy.deepcopy(row)

        if (
            statement.startswith("SELECT id, form_id, spreadsheet_id")
            and "WHERE id = $1" in statement
        ):
            return copy.deepcopy(self._find(args[0]))

        if statement.startswith("SELECT") and "WHERE id = $1" in statement:
            return copy.deepcopy(self._find(args[0]))

        if statement.startswith("UPDATE form_sources"):
            row = self._find(args[0])
            if row is None:
                return None
            if "spreadsheet_id = COALESCE" in statement:
                if args[1] is not None:
                    row["spreadsheet_id"] = args[1]
                if args[2] is not None:
                    row["sheet_name"] = args[2]
                if args[3] is not None:
                    row["ignored_headers"] = list(args[3])
                if args[4] is not None:
                    row["poll_interval_seconds"] = args[4]
            else:
                row["enabled"] = args[1]
                if args[1]:
                    row["next_poll_at"] = datetime.now(UTC)
            row["updated_at"] = datetime.now(UTC)
            return copy.deepcopy(row)

        raise AssertionError(f"unexpected fetchrow query: {statement}")

    def _find(self, source_id: int) -> dict[str, Any] | None:
        return next(
            (source for source in self.sources if source["id"] == source_id),
            None,
        )


class FakeAcquire(AbstractAsyncContextManager[FakeFormSourceConnection]):
    def __init__(self, connection: FakeFormSourceConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeFormSourceConnection:
        return self.connection

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        return None


class FakePool:
    def __init__(self, connection: FakeFormSourceConnection) -> None:
        self.connection = connection

    def acquire(self) -> FakeAcquire:
        return FakeAcquire(self.connection)


class FormSourceApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.connection = FakeFormSourceConnection()
        app.state.db_pool = FakePool(self.connection)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    @staticmethod
    def payload(**overrides: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "form_id": "customer-feedback",
            "spreadsheet_id": (
                "https://docs.google.com/spreadsheets/d/sheet_123-abc/edit"
            ),
            "sheet_name": "Form Responses 1",
            "ignored_headers": [" Timestamp ", "Email", "timestamp"],
            "poll_interval_seconds": 60,
        }
        payload.update(overrides)
        return payload

    async def test_routes_are_registered_without_credential_fields(self) -> None:
        paths = app.openapi()["paths"]
        self.assertIn("/form-sources", paths)
        self.assertIn("/form-sources/{form_source_id}", paths)
        self.assertIn("/form-sources/{form_source_id}/enable", paths)
        schemas = str(app.openapi()["components"]["schemas"])
        self.assertNotIn("service_account", schemas)
        self.assertNotIn("credentials", schemas)

    async def test_create_normalizes_url_and_ignored_headers(self) -> None:
        response = await self.client.post("/form-sources", json=self.payload())

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["spreadsheet_id"], "sheet_123-abc")
        self.assertEqual(body["ignored_headers"], ["Timestamp", "Email"])
        self.assertTrue(body["enabled"])
        self.assertEqual(body["last_read_row"], 1)

    async def test_list_get_update_disable_and_enable(self) -> None:
        created = await self.client.post("/form-sources", json=self.payload())
        source_id = created.json()["id"]

        listed = await self.client.get(
            "/form-sources",
            params={"page": 1, "page_size": 100},
        )
        fetched = await self.client.get(f"/form-sources/{source_id}")
        updated = await self.client.patch(
            f"/form-sources/{source_id}",
            json={
                "sheet_name": "Responses",
                "poll_interval_seconds": 120,
            },
        )
        disabled = await self.client.post(
            f"/form-sources/{source_id}/disable"
        )
        enabled = await self.client.post(f"/form-sources/{source_id}/enable")

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["total"], 1)
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(updated.json()["sheet_name"], "Responses")
        self.assertEqual(updated.json()["poll_interval_seconds"], 120)
        self.assertFalse(disabled.json()["enabled"])
        self.assertTrue(enabled.json()["enabled"])

    async def test_duplicate_registration_returns_conflict(self) -> None:
        first = await self.client.post("/form-sources", json=self.payload())
        duplicate = await self.client.post(
            "/form-sources",
            json=self.payload(spreadsheet_id="different-sheet"),
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()["detail"], "form_id is already registered")

    async def test_rejects_invalid_or_server_owned_fields(self) -> None:
        invalid_payloads = (
            self.payload(spreadsheet_id="http://example.com/not-google"),
            self.payload(ignored_headers=["Timestamp", "  "]),
            self.payload(poll_interval_seconds=0),
            self.payload(credentials={"private_key": "secret"}),
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = await self.client.post(
                    "/form-sources",
                    json=payload,
                )
                self.assertEqual(response.status_code, 422)

        created = await self.client.post("/form-sources", json=self.payload())
        response = await self.client.patch(
            f"/form-sources/{created.json()['id']}",
            json={"form_id": "renamed"},
        )
        self.assertEqual(response.status_code, 422)

    def test_spreadsheet_id_helper_accepts_id_and_google_url(self) -> None:
        self.assertEqual(normalize_spreadsheet_id("sheet_123"), "sheet_123")
        self.assertEqual(
            normalize_spreadsheet_id(
                "https://docs.google.com/spreadsheets/d/sheet-456/edit#gid=0"
            ),
            "sheet-456",
        )


if __name__ == "__main__":
    unittest.main()

