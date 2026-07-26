#!/usr/bin/env python3
"""Interactive black-box test runner for the triage processing pipeline."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

SINGLE_TOPIC_INPUT = (
    "The checkout page becomes very slow when applying a discount code."
)
MULTI_TOPIC_INPUT = (
    "The checkout page is slow when applying discounts. "
    "I would also like invoices to be downloadable as PDF files."
)
INELIGIBLE_INPUT = "asdf qwer 123 spam spam"
THEME_INPUTS = (
    "Applying a coupon makes checkout take nearly thirty seconds.",
    (
        "Customers experience long delays on the payment page when using "
        "promotional codes."
    ),
)


def sql_literal(value: str) -> str:
    """Return a PostgreSQL string literal for a locally supplied value."""
    return "'" + value.replace("'", "''") + "'"


class ManualTestRunner:
    def __init__(self, *, api_url: str, source: str) -> None:
        self.api_url = api_url.rstrip("/")
        self.source = source

    def submit_input(
        self,
        original_text: str,
        *,
        source: str | None = None,
        expected_status: int = 201,
    ) -> None:
        payload = {
            "source": source or self.source,
            "original_text": original_text,
        }
        request = Request(
            f"{self.api_url}/inputs",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        print(f"\nPOST {request.full_url}")
        print(json.dumps(payload, indent=2))

        try:
            with urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
                self._print_http_result(response.status, body, expected_status)
        except HTTPError as error:
            body = error.read().decode("utf-8")
            self._print_http_result(error.code, body, expected_status)
        except URLError as error:
            print(
                f"\nCould not reach the API at {self.api_url}: {error.reason}\n"
                "Start the stack with: docker compose up --build -d",
                file=sys.stderr,
            )

    @staticmethod
    def _print_http_result(status: int, body: str, expected_status: int) -> None:
        outcome = "PASS" if status == expected_status else "FAIL"
        print(f"\n[{outcome}] HTTP {status} (expected {expected_status})")
        try:
            print(json.dumps(json.loads(body), indent=2))
        except json.JSONDecodeError:
            print(body)

    def submit_single_topic(self) -> None:
        self.submit_input(SINGLE_TOPIC_INPUT)

    def submit_multi_topic(self) -> None:
        self.submit_input(MULTI_TOPIC_INPUT)

    def submit_ineligible(self) -> None:
        self.submit_input(INELIGIBLE_INPUT)

    def submit_theme_pair(self) -> None:
        for original_text in THEME_INPUTS:
            self.submit_input(original_text)

    def submit_invalid(self) -> None:
        self.submit_input(
            "   ",
            source=f"{self.source}-invalid",
            expected_status=422,
        )

    def submit_all_valid(self) -> None:
        self.submit_single_topic()
        self.submit_multi_topic()
        self.submit_ineligible()
        self.submit_theme_pair()

    def run_sql(self, query: str) -> None:
        command = [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "postgres",
            "-d",
            "triage",
            "-P",
            "pager=off",
            "-c",
            query,
        ]
        print(f"\nQuerying rows with source = {self.source!r}\n")
        try:
            result = subprocess.run(
                command,
                cwd=REPOSITORY_ROOT,
                check=False,
            )
        except FileNotFoundError:
            print(
                "The docker command was not found. Enable Docker Desktop's "
                "WSL integration or install Docker.",
                file=sys.stderr,
            )
            return

        if result.returncode != 0:
            print(
                f"\nSQL command failed with exit code {result.returncode}. "
                "Check that the Compose stack is running.",
                file=sys.stderr,
            )

    def query_results(self) -> None:
        source = sql_literal(self.source)
        self.run_sql(
            f"""
SELECT
    inputs.id,
    inputs.status,
    inputs.topic,
    COUNT(DISTINCT segments.id) AS segments,
    COUNT(DISTINCT embeddings.id) AS embeddings,
    inputs.original_text
FROM original_inputs AS inputs
LEFT JOIN segment_inputs AS segments
    ON segments.original_input_id = inputs.id
LEFT JOIN input_embeddings AS embeddings
    ON embeddings.original_input_id = inputs.id
    OR embeddings.segment_input_id = segments.id
WHERE inputs.source = {source}
GROUP BY inputs.id
ORDER BY inputs.id;
""".strip()
        )

    def query_segments(self) -> None:
        source = sql_literal(self.source)
        self.run_sql(
            f"""
SELECT
    inputs.id AS original_input_id,
    segments.segment_order,
    segments.topic,
    segments.segment_text
FROM original_inputs AS inputs
JOIN segment_inputs AS segments
    ON segments.original_input_id = inputs.id
WHERE inputs.source = {source}
ORDER BY inputs.id, segments.segment_order;
""".strip()
        )

    def query_worker_jobs(self) -> None:
        source = sql_literal(self.source)
        self.run_sql(
            f"""
SELECT
    inputs.id AS original_input_id,
    jobs.job_type,
    jobs.status,
    jobs.attempts,
    jobs.last_error
FROM original_inputs AS inputs
JOIN worker_jobs AS jobs
    ON jobs.original_input_id = inputs.id
WHERE inputs.source = {source}
ORDER BY inputs.id, jobs.id;
""".strip()
        )

    def query_theme_suggestions(self) -> None:
        source = sql_literal(self.source)
        self.run_sql(
            f"""
SELECT
    suggestions.id,
    suggestions.action,
    suggestions.proposed_name,
    suggestions.proposed_description,
    suggestions.rationale
FROM theme_suggestions AS suggestions
WHERE EXISTS (
    SELECT 1
    FROM theme_suggestion_evidence AS evidence
    LEFT JOIN segment_inputs AS segments
        ON segments.id = evidence.segment_input_id
    JOIN original_inputs AS inputs
        ON inputs.id = COALESCE(
            evidence.original_input_id,
            segments.original_input_id
        )
    WHERE
        evidence.suggestion_id = suggestions.id
        AND inputs.source = {source}
)
ORDER BY suggestions.id DESC;
""".strip()
        )

    def query_all(self) -> None:
        self.query_results()
        self.query_segments()
        self.query_worker_jobs()
        self.query_theme_suggestions()


def print_menu(source: str) -> None:
    print(
        f"""
Triage processor manual tests
Current source: {source}

  1. Submit single-topic input
  2. Submit multi-topic input
  3. Submit ineligible input
  4. Submit related pair for theme detection
  5. Submit invalid input (expects HTTP 422)
  6. Submit all valid sample inputs
  7. Query input status, topics, segments, and embedding counts
  8. Query generated segments
  9. Query worker jobs
 10. Query theme suggestions
 11. Run all SQL queries
  0. Exit
""".strip()
    )


def default_source() -> str:
    return f"manual-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Interactively submit manual test inputs and inspect results.",
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="Base URL of the API (default: %(default)s)",
    )
    parser.add_argument(
        "--source",
        default=default_source(),
        help=(
            "Source tag used to group this run. Pass a previous value to query "
            "an earlier run."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runner = ManualTestRunner(api_url=args.api_url, source=args.source)
    actions = {
        "1": runner.submit_single_topic,
        "2": runner.submit_multi_topic,
        "3": runner.submit_ineligible,
        "4": runner.submit_theme_pair,
        "5": runner.submit_invalid,
        "6": runner.submit_all_valid,
        "7": runner.query_results,
        "8": runner.query_segments,
        "9": runner.query_worker_jobs,
        "10": runner.query_theme_suggestions,
        "11": runner.query_all,
    }

    while True:
        print_menu(runner.source)
        try:
            choice = input("\nEnter a number: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            return

        if choice == "0":
            print("Exiting.")
            return

        action = actions.get(choice)
        if action is None:
            print(f"\nUnknown option {choice!r}. Enter a number from 0 to 11.\n")
            continue

        action()
        input("\nPress Enter to return to the menu...")
        print()


if __name__ == "__main__":
    main()
