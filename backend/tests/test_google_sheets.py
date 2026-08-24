import unittest

from triage_processor.integrations.google_sheets import (
    FormSource,
    build_row_payloads,
    process_form_source,
    question_key_for_header,
)


class AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeConnection:
    def __init__(self):
        self.cursor_updates = []

    async def execute(self, query, *values):
        if "last_read_row = GREATEST(last_read_row, $2)" not in query:
            raise AssertionError(f"unexpected query: {query}")
        self.cursor_updates.append(values)


class FakePool:
    def __init__(self):
        self.connection = FakeConnection()

    def acquire(self):
        return AsyncContext(self.connection)


class FakeSheets:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    async def get_values(self, spreadsheet_id, range_name):
        self.requests.append((spreadsheet_id, range_name))
        return self.responses[range_name]


class FakeSink:
    def __init__(self, *, fail_on_call=None):
        self.payloads = []
        self.fail_on_call = fail_on_call

    async def create_input(self, payload):
        if len(self.payloads) + 1 == self.fail_on_call:
            raise RuntimeError("simulated API failure")
        self.payloads.append(payload)


def form_source(**overrides):
    values = {
        "id": 7,
        "source": "google-sheets",
        "form_id": "customer-feedback",
        "spreadsheet_id": "sheet-123",
        "sheet_name": "Form Responses 1",
        "ignored_headers": ("Timestamp",),
        "last_read_row": 1,
    }
    values.update(overrides)
    return FormSource(**values)


class GoogleSheetsImporterTests(unittest.IsolatedAsyncioTestCase):
    def test_row_becomes_one_input_per_nonblank_answer(self):
        source = form_source()

        payloads = build_row_payloads(
            source,
            ["Timestamp", "Purchase barrier", "Checkout difficulty"],
            ["2026-08-24 12:00", "Too expensive", ""],
            row_number=2,
        )

        self.assertEqual(len(payloads), 1)
        payload = payloads[0]
        self.assertEqual(payload["original_text"], "Too expensive")
        self.assertEqual(payload["submission_key"], "form-source:7:row:2")
        self.assertEqual(
            payload["source_record_key"],
            "form-source:7:row:2:column:2",
        )
        self.assertEqual(
            payload["question_context"],
            {
                "form_key": "customer-feedback",
                "form_id": "customer-feedback",
                "question_key": question_key_for_header("Purchase barrier"),
                "question_version": 1,
                "question_text": "Purchase barrier",
            },
        )

    def test_duplicate_headers_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate header"):
            build_row_payloads(
                form_source(),
                ["Timestamp", "Comments", " comments "],
                ["now", "First", "Second"],
                row_number=2,
            )

    def test_value_under_blank_header_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "blank header"):
            build_row_payloads(
                form_source(),
                ["Timestamp", ""],
                ["now", "Unexpected"],
                row_number=2,
            )

    async def test_processes_unread_rows_and_advances_after_each_row(self):
        source = form_source(sheet_name="O'Brien Responses")
        sheet_name = "'O''Brien Responses'"
        sheets = FakeSheets(
            {
                f"{sheet_name}!1:1": [
                    ["Timestamp", "Question one", "Question two"]
                ],
                f"{sheet_name}!2:3": [
                    ["now", "Answer one", ""],
                    ["later", "", "Answer two"],
                ],
            }
        )
        sink = FakeSink()
        pool = FakePool()

        processed = await process_form_source(
            pool,
            sheets,
            sink,
            source,
            batch_size=2,
        )

        self.assertEqual(processed, 2)
        self.assertEqual(len(sink.payloads), 2)
        self.assertEqual(pool.connection.cursor_updates, [(7, 2), (7, 3)])
        self.assertEqual(
            sheets.requests,
            [
                ("sheet-123", f"{sheet_name}!1:1"),
                ("sheet-123", f"{sheet_name}!2:3"),
            ],
        )

    async def test_failure_does_not_advance_the_failing_row(self):
        source = form_source()
        sheet_name = "'Form Responses 1'"
        sheets = FakeSheets(
            {
                f"{sheet_name}!1:1": [["Timestamp", "Question"]],
                f"{sheet_name}!2:3": [
                    ["now", "First answer"],
                    ["later", "Second answer"],
                ],
            }
        )
        sink = FakeSink(fail_on_call=2)
        pool = FakePool()

        with self.assertRaisesRegex(RuntimeError, "simulated API failure"):
            await process_form_source(
                pool,
                sheets,
                sink,
                source,
                batch_size=2,
            )

        self.assertEqual(pool.connection.cursor_updates, [(7, 2)])


if __name__ == "__main__":
    unittest.main()
