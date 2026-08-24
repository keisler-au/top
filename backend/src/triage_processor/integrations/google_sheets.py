import argparse
import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote

import asyncpg
import httpx
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account

from triage_processor.config import DATABASE_URL

LOGGER = logging.getLogger(__name__)
SHEETS_READONLY_SCOPE = (
    "https://www.googleapis.com/auth/spreadsheets.readonly"
)


@dataclass(frozen=True)
class FormSource:
    id: int
    source: str
    form_id: str
    spreadsheet_id: str
    sheet_name: str
    ignored_headers: tuple[str, ...]
    last_read_row: int


class SheetsReader(Protocol):
    async def get_values(
        self,
        spreadsheet_id: str,
        range_name: str,
    ) -> list[list[object]]: ...


class InputSink(Protocol):
    async def create_input(self, payload: dict[str, object]) -> None: ...


class GoogleSheetsReader:
    def __init__(
        self,
        credentials: service_account.Credentials,
        *,
        timeout_seconds: float = 30,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._credentials = credentials
        self._refresh_request = GoogleAuthRequest()
        self._refresh_lock = asyncio.Lock()
        self._client = httpx.AsyncClient(
            base_url="https://sheets.googleapis.com",
            timeout=timeout_seconds,
            transport=transport,
        )

    @classmethod
    def from_service_account_file(
        cls,
        path: str,
        *,
        timeout_seconds: float = 30,
    ) -> "GoogleSheetsReader":
        credentials = service_account.Credentials.from_service_account_file(
            path,
            scopes=[SHEETS_READONLY_SCOPE],
        )
        return cls(credentials, timeout_seconds=timeout_seconds)

    async def _access_token(self) -> str:
        async with self._refresh_lock:
            if not self._credentials.valid:
                await asyncio.to_thread(
                    self._credentials.refresh,
                    self._refresh_request,
                )
            token = self._credentials.token
        if not token:
            raise RuntimeError("Google credentials did not provide an access token")
        return token

    async def get_values(
        self,
        spreadsheet_id: str,
        range_name: str,
    ) -> list[list[object]]:
        token = await self._access_token()
        response = await self._client.get(
            f"/v4/spreadsheets/{quote(spreadsheet_id, safe='')}/values/"
            f"{quote(range_name, safe='')}",
            params={
                "majorDimension": "ROWS",
                "valueRenderOption": "FORMATTED_VALUE",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        values = response.json().get("values", [])
        if not isinstance(values, list) or any(
            not isinstance(row, list) for row in values
        ):
            raise ValueError("Google Sheets response contained invalid values")
        return values

    async def close(self) -> None:
        await self._client.aclose()


class ApiInputSink:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 30,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            transport=transport,
        )

    async def create_input(self, payload: dict[str, object]) -> None:
        response = await self._client.post("/inputs", json=payload)
        if response.status_code != 201:
            raise RuntimeError(
                "input API rejected a sheet cell: "
                f"status={response.status_code} body={response.text[:2000]}"
            )

    async def close(self) -> None:
        await self._client.aclose()


def _a1_sheet_name(sheet_name: str) -> str:
    return "'" + sheet_name.replace("'", "''") + "'"


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value).strip()
    return str(value).strip()


def _normalized_header(value: object) -> str:
    return _cell_text(value).casefold()


def question_key_for_header(header: str) -> str:
    digest = hashlib.sha256(header.strip().casefold().encode()).hexdigest()
    return f"header-{digest[:16]}"


def build_row_payloads(
    source: FormSource,
    headers: list[object],
    row: list[object],
    *,
    row_number: int,
) -> list[dict[str, object]]:
    ignored = {header.strip().casefold() for header in source.ignored_headers}
    active_headers: dict[str, int] = {}
    for index, raw_header in enumerate(headers):
        header = _cell_text(raw_header)
        normalized = header.casefold()
        if not header or normalized in ignored:
            continue
        if normalized in active_headers:
            first_column = active_headers[normalized] + 1
            raise ValueError(
                f"duplicate header {header!r} in columns "
                f"{first_column} and {index + 1}"
            )
        active_headers[normalized] = index

    submission_key = f"form-source:{source.id}:row:{row_number}"
    payloads: list[dict[str, object]] = []
    for index, raw_value in enumerate(row):
        answer = _cell_text(raw_value)
        if not answer:
            continue
        if index >= len(headers):
            raise ValueError(
                f"row {row_number} has a value in column {index + 1} "
                "but the header row does not"
            )

        header = _cell_text(headers[index])
        normalized = header.casefold()
        if normalized in ignored:
            continue
        if not header:
            raise ValueError(
                f"row {row_number} has a value under a blank header in "
                f"column {index + 1}"
            )

        payloads.append(
            {
                "original_text": answer,
                "source": source.source,
                "submission_key": submission_key,
                "source_record_key": (
                    f"form-source:{source.id}:row:{row_number}:"
                    f"column:{index + 1}"
                ),
                "question_context": {
                    "form_key": source.form_id,
                    "form_id": source.form_id,
                    "question_key": question_key_for_header(header),
                    "question_version": 1,
                    "question_text": header,
                },
            }
        )
    return payloads


async def claim_form_source(pool: asyncpg.Pool) -> FormSource | None:
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            WITH due_source AS (
                SELECT id
                FROM form_sources
                WHERE enabled AND next_poll_at <= CURRENT_TIMESTAMP
                ORDER BY next_poll_at, id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE form_sources AS sources
            SET
                next_poll_at = CURRENT_TIMESTAMP
                    + (sources.poll_interval_seconds * INTERVAL '1 second'),
                updated_at = CURRENT_TIMESTAMP
            FROM due_source
            WHERE sources.id = due_source.id
            RETURNING
                sources.id,
                sources.source,
                sources.form_id,
                sources.spreadsheet_id,
                sources.sheet_name,
                sources.ignored_headers,
                sources.last_read_row
            """
        )
    if row is None:
        return None
    return FormSource(
        id=row["id"],
        source=row["source"],
        form_id=row["form_id"],
        spreadsheet_id=row["spreadsheet_id"],
        sheet_name=row["sheet_name"],
        ignored_headers=tuple(row["ignored_headers"]),
        last_read_row=row["last_read_row"],
    )


async def _record_success(
    pool: asyncpg.Pool,
    source_id: int,
    last_read_row: int,
) -> None:
    async with pool.acquire() as connection:
        await connection.execute(
            """
            UPDATE form_sources
            SET
                last_read_row = GREATEST(last_read_row, $2),
                last_polled_at = CURRENT_TIMESTAMP,
                last_error = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $1
            """,
            source_id,
            last_read_row,
        )


async def _record_failure(
    pool: asyncpg.Pool,
    source_id: int,
    error: Exception,
) -> None:
    async with pool.acquire() as connection:
        await connection.execute(
            """
            UPDATE form_sources
            SET
                last_polled_at = CURRENT_TIMESTAMP,
                last_error = $2,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $1
            """,
            source_id,
            str(error)[:4000],
        )


async def process_form_source(
    pool: asyncpg.Pool,
    sheets: SheetsReader,
    sink: InputSink,
    source: FormSource,
    *,
    batch_size: int,
) -> int:
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    sheet = _a1_sheet_name(source.sheet_name)
    header_rows = await sheets.get_values(
        source.spreadsheet_id,
        f"{sheet}!1:1",
    )
    if not header_rows or not any(_cell_text(value) for value in header_rows[0]):
        raise ValueError("sheet does not contain a usable header row")
    headers = header_rows[0]

    start_row = source.last_read_row + 1
    end_row = start_row + batch_size - 1
    rows = await sheets.get_values(
        source.spreadsheet_id,
        f"{sheet}!{start_row}:{end_row}",
    )

    processed = 0
    last_read_row = source.last_read_row
    for row_number, row in enumerate(rows, start=start_row):
        payloads = build_row_payloads(
            source,
            headers,
            row,
            row_number=row_number,
        )
        for payload in payloads:
            await sink.create_input(payload)
        last_read_row = row_number
        await _record_success(pool, source.id, last_read_row)
        processed += 1

    if not rows:
        await _record_success(pool, source.id, last_read_row)
    return processed


async def run_poller(
    *,
    once: bool,
    poll_interval: float,
    batch_size: int,
) -> None:
    if poll_interval <= 0:
        raise ValueError("poll_interval must be positive")
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    credentials_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_file:
        raise ValueError("GOOGLE_APPLICATION_CREDENTIALS is required")

    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2)
    sheets = GoogleSheetsReader.from_service_account_file(
        credentials_file,
        timeout_seconds=float(os.getenv("GOOGLE_SHEETS_TIMEOUT_SECONDS", "30")),
    )
    sink = ApiInputSink(
        os.getenv("API_BASE_URL", "http://localhost:8000"),
        timeout_seconds=float(os.getenv("API_TIMEOUT_SECONDS", "30")),
    )
    try:
        while True:
            source = await claim_form_source(pool)
            if source is None:
                if once:
                    return
                await asyncio.sleep(poll_interval)
                continue

            try:
                processed = await process_form_source(
                    pool,
                    sheets,
                    sink,
                    source,
                    batch_size=batch_size,
                )
                LOGGER.info(
                    "Polled form %s from sheet %s: rows=%s",
                    source.form_id,
                    source.spreadsheet_id,
                    processed,
                )
            except Exception as error:
                await _record_failure(pool, source.id, error)
                LOGGER.exception("Could not poll form %s", source.form_id)
                if once:
                    raise

            if once:
                return
    finally:
        await sink.close()
        await sheets.close()
        await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Poll registered Google Form response spreadsheets."
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=float(os.getenv("GOOGLE_SHEETS_POLL_INTERVAL", "5")),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.getenv("GOOGLE_SHEETS_BATCH_SIZE", "100")),
    )
    args = parser.parse_args()
    if args.poll_interval <= 0 or args.batch_size < 1:
        parser.error("poll interval and batch size must be positive")

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(
        run_poller(
            once=args.once,
            poll_interval=args.poll_interval,
            batch_size=args.batch_size,
        )
    )


if __name__ == "__main__":
    main()
