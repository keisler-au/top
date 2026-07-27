#!/usr/bin/env python3
"""Interactive black-box test runner for the complete processing pipeline.

Run the complete suite
----------------------
1. Start the stack and workers:
       docker compose up --build -d
2. Start this runner:
       python3 infrastructure/postgres/manual_test.py
3. Press ``A`` to submit every scenario, including expected 409/422 cases.
4. Give the asynchronous workers time to finish, press ``B`` to run the
   database assertions, then press ``Z`` for all inspection tables. Re-run
   ``J`` first if jobs are still pending.

For a non-interactive submission run:
    python3 infrastructure/postgres/manual_test.py --run A \\
        --source manual-full-suite

Inspect that same run later with:
    python3 infrastructure/postgres/manual_test.py --run Z \\
        --source manual-full-suite

Run one scenario at a time
--------------------------
G  generic inputs (single topic, multi-topic, and ineligible)
C  contextual short and long answers
M  one contextual answer containing many topics (segmentation stress test)
Q  multiple questions answered within one submission
R  related answers to the same question
X  identical answer text under different questions
V  immutable question identity, conflict, and question-version behavior
T  worked Cost Barriers / Checkout Friction theme-materialization fixture
E  invalid and non-responsive payloads
K  retrieval API checks, including required scope validation
A  all submission scenarios above

Inspection keys are B (assert all fixture outcomes), I (inputs), S (segments),
J (jobs), H (questions), U (submissions), P (pending/materialized
suggestions), L (answer → topic → canonical themes), and Z (all inspection
tables). Press ``?`` to show the menu and ``0`` to exit.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

SINGLE_TOPIC_INPUT = (
    "The checkout page becomes very slow when applying a discount code."
)
MULTI_TOPIC_INPUT = (
    "The checkout page is slow when applying discounts. "
    "I would also like invoices to be downloadable as PDF files."
)
INELIGIBLE_INPUT = "asdf qwer 123 spam spam"
CONTEXTUAL_SHORT_LONG = (
    {
        "original_text": "Price",
        "submission_key": "context-response-1",
        "question_context": {
            "form_key": "context-basics",
            "question_key": "purchase-barrier",
            "question_text": "What prevents you from purchasing?",
        },
    },
    {
        "original_text": (
            "The subscription costs more than the value it provides, "
            "especially after the latest price increase. We compared it "
            "with several alternatives and could not justify the annual "
            "commitment for a small team."
        ),
        "submission_key": "context-response-2",
        "question_context": {
            "form_key": "context-basics",
            "question_key": "purchase-barrier",
            "question_text": "What prevents you from purchasing?",
        },
    },
)
MANY_TOPICS_ANSWER = {
    "original_text": (
        "The subscription price is too high for a small organisation. "
        "Checkout loses my basket whenever I apply a discount code. "
        "Delivery estimates are vague and orders often arrive late. "
        "Invoices should be downloadable as PDF files for our accounts team. "
        "The mobile navigation hides important settings, and support takes "
        "several days to answer technical questions."
    ),
    "submission_key": "many-topics-response-1",
    "question_context": {
        "form_key": "broad-feedback",
        "question_key": "everything-to-improve",
        "question_text": (
            "Tell us everything that made buying or using the service "
            "difficult."
        ),
    },
}
MULTI_QUESTION_SUBMISSION = (
    {
        "original_text": "The monthly cost is beyond our budget.",
        "submission_key": "multi-question-response-1",
        "question_context": {
            "form_key": "multi-question-survey",
            "question_key": "purchase-barrier",
            "question_text": "What prevents you from purchasing?",
        },
    },
    {
        "original_text": "The card form rejected a valid company card.",
        "submission_key": "multi-question-response-1",
        "question_context": {
            "form_key": "multi-question-survey",
            "question_key": "checkout-problem",
            "question_text": "What went wrong while placing your order?",
        },
    },
    {
        "original_text": "An emailed PDF invoice with tax details.",
        "submission_key": "multi-question-response-1",
        "question_context": {
            "form_key": "multi-question-survey",
            "question_key": "invoice-format",
            "question_text": "How would you prefer to receive invoices?",
        },
    },
    {
        "original_text": "No",
        "submission_key": "multi-question-response-1",
        "question_context": {
            "form_key": "multi-question-survey",
            "question_key": "recommend",
            "question_text": "Would you recommend this product?",
        },
    },
)
RELATED_SAME_QUESTION = (
    {
        "original_text": "The setup guide skips the authentication steps.",
        "submission_key": "related-response-1",
        "question_context": {
            "form_key": "onboarding-survey",
            "question_key": "setup-problem",
            "question_text": "What made initial setup difficult?",
        },
    },
    {
        "original_text": "Setup failed because the login instructions were unclear.",
        "submission_key": "related-response-2",
        "question_context": {
            "form_key": "onboarding-survey",
            "question_key": "setup-problem",
            "question_text": "What made initial setup difficult?",
        },
    },
    {
        "original_text": "The onboarding documentation omitted SSO configuration.",
        "submission_key": "related-response-3",
        "question_context": {
            "form_key": "onboarding-survey",
            "question_key": "setup-problem",
            "question_text": "What made initial setup difficult?",
        },
    },
)
IDENTICAL_ANSWER_CONTEXTS = (
    {
        "original_text": "No",
        "submission_key": "identical-response-1",
        "question_context": {
            "form_key": "identical-answers",
            "question_key": "recommend",
            "question_text": "Would you recommend this product?",
        },
    },
    {
        "original_text": "No",
        "submission_key": "identical-response-2",
        "question_context": {
            "form_key": "identical-answers",
            "question_key": "marketing-consent",
            "question_text": "May we send you marketing messages?",
        },
    },
)
THEME_MATERIALIZATION_FIXTURES = (
    {
        "original_text": "The subscription is too expensive for our budget.",
        "submission_key": "theme-response-1",
        "question_context": {
            "form_key": "purchase-theme",
            "question_key": "purchase-barrier",
            "question_text": "What prevents you from purchasing?",
        },
    },
    {
        "original_text": "The fees exceed the value offered to a small team.",
        "submission_key": "theme-response-2",
        "question_context": {
            "form_key": "purchase-theme",
            "question_key": "purchase-barrier",
            "question_text": "What prevents you from purchasing?",
        },
    },
    {
        "original_text": "Checkout repeatedly loses the contents of my basket.",
        "submission_key": "theme-response-1",
        "question_context": {
            "form_key": "purchase-theme",
            "question_key": "checkout-improvement",
            "question_text": "What made completing your order difficult?",
        },
    },
    {
        "original_text": "The payment steps are confusing and take too long.",
        "submission_key": "theme-response-2",
        "question_context": {
            "form_key": "purchase-theme",
            "question_key": "checkout-improvement",
            "question_text": "How could we improve the checkout experience?",
        },
    },
)


def sql_literal(value: str) -> str:
    """Return a PostgreSQL string literal for a locally supplied value."""
    return "'" + value.replace("'", "''") + "'"


class ManualTestRunner:
    def __init__(self, *, api_url: str, source: str) -> None:
        self.api_url = api_url.rstrip("/")
        self.source = source
        self.checks = 0
        self.failures = 0

    def submit_input(
        self,
        original_text: str,
        *,
        source: str | None = None,
        submission_key: str | None = None,
        question_context: dict[str, object] | None = None,
        expected_status: int = 201,
    ) -> bool:
        payload: dict[str, object] = {
            "source": source or self.source,
            "original_text": original_text,
        }
        if submission_key is not None:
            payload["submission_key"] = submission_key
        if question_context is not None:
            payload["question_context"] = question_context
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
                passed = self._print_http_result(
                    response.status,
                    body,
                    expected_status,
                )
        except HTTPError as error:
            body = error.read().decode("utf-8")
            passed = self._print_http_result(
                error.code,
                body,
                expected_status,
            )
        except URLError as error:
            print(
                f"\nCould not reach the API at {self.api_url}: {error.reason}\n"
                "Start the stack with: docker compose up --build -d",
                file=sys.stderr,
            )
            passed = False
        self.checks += 1
        if not passed:
            self.failures += 1
        return passed

    @staticmethod
    def _print_http_result(
        status: int,
        body: str,
        expected_status: int,
    ) -> bool:
        outcome = "PASS" if status == expected_status else "FAIL"
        print(f"\n[{outcome}] HTTP {status} (expected {expected_status})")
        try:
            print(json.dumps(json.loads(body), indent=2))
        except json.JSONDecodeError:
            print(body)
        return status == expected_status

    def get_inputs(
        self,
        parameters: dict[str, object],
        *,
        expected_status: int = 200,
        expected_count: int | None = None,
    ) -> bool:
        url = f"{self.api_url}/inputs?{urlencode(parameters)}"
        request = Request(url, method="GET")
        print(f"\nGET {url}")
        try:
            with urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
                status_code = response.status
        except HTTPError as error:
            body = error.read().decode("utf-8")
            status_code = error.code
        except URLError as error:
            print(
                f"\nCould not reach the API at {self.api_url}: {error.reason}",
                file=sys.stderr,
            )
            self.checks += 1
            self.failures += 1
            return False

        passed = self._print_http_result(
            status_code,
            body,
            expected_status,
        )
        if passed and expected_count is not None:
            try:
                result = json.loads(body)
                count_matches = (
                    isinstance(result, list)
                    and len(result) == expected_count
                )
            except json.JSONDecodeError:
                count_matches = False
            outcome = "PASS" if count_matches else "FAIL"
            print(
                f"[{outcome}] result count "
                f"(expected {expected_count})"
            )
            passed = count_matches
        self.checks += 1
        if not passed:
            self.failures += 1
        return passed

    def print_summary(self) -> None:
        passed = self.checks - self.failures
        outcome = "PASS" if self.failures == 0 else "FAIL"
        print(
            f"\n[{outcome}] {passed}/{self.checks} checks passed "
            f"for source {self.source!r}."
        )

    def submit_generic_inputs(self) -> None:
        self.submit_input(SINGLE_TOPIC_INPUT)
        self.submit_input(MULTI_TOPIC_INPUT)
        self.submit_input(INELIGIBLE_INPUT)

    def submit_contextual_short_long(self) -> None:
        for fixture in CONTEXTUAL_SHORT_LONG:
            self.submit_input(**fixture)

    def submit_many_topics_answer(self) -> None:
        self.submit_input(**MANY_TOPICS_ANSWER)

    def submit_multi_question_submission(self) -> None:
        for fixture in MULTI_QUESTION_SUBMISSION:
            self.submit_input(**fixture)

    def submit_related_same_question(self) -> None:
        for fixture in RELATED_SAME_QUESTION:
            self.submit_input(**fixture)

    def submit_identical_answer_contexts(self) -> None:
        for fixture in IDENTICAL_ANSWER_CONTEXTS:
            self.submit_input(**fixture)

    def submit_question_version_checks(self) -> None:
        context = {
            "form_key": "versioned-survey",
            "question_key": "service-improvement",
            "question_text": "What should we improve about the service?",
        }
        self.submit_input(
            "Response time",
            submission_key="version-response-1",
            question_context=context,
        )
        self.submit_input(
            "Support hours",
            submission_key="version-response-conflict",
            question_context={
                **context,
                "question_text": "What should we change about the service?",
            },
            expected_status=409,
        )
        self.submit_input(
            "Support hours",
            submission_key="version-response-2",
            question_context={
                **context,
                "question_version": 2,
                "question_text": "What should we change about the service?",
            },
        )

    def submit_theme_materialization_fixture(self) -> None:
        for fixture in THEME_MATERIALIZATION_FIXTURES:
            self.submit_input(**fixture)

    def submit_error_cases(self) -> None:
        self.submit_input(
            "   ",
            source=f"{self.source}-invalid",
            expected_status=422,
        )
        self.submit_input(
            "Price",
            submission_key="missing-question-context",
            expected_status=422,
        )
        self.submit_input(
            "Price",
            question_context={
                "form_key": "partial-context",
                "question_key": "missing-text",
            },
            expected_status=422,
        )
        self.submit_input(
            "asdf qwer spam",
            submission_key="non-responsive-context",
            question_context={
                "form_key": "error-cases",
                "question_key": "purchase-barrier",
                "question_text": "What prevents you from purchasing?",
            },
        )

    def test_retrieval_api(self) -> None:
        fixtures = (
            {
                "original_text": "Cost",
                "submission_key": "retrieval-response-1",
                "question_context": {
                    "form_key": "retrieval-survey",
                    "question_key": "cost",
                    "question_text": "What affected your purchase decision?",
                },
            },
            {
                "original_text": "Checkout",
                "submission_key": "retrieval-response-1",
                "question_context": {
                    "form_key": "retrieval-survey",
                    "question_key": "checkout",
                    "question_text": "What happened during checkout?",
                },
            },
        )
        for fixture in fixtures:
            self.submit_input(**fixture)

        scope = {
            "source": self.source,
            "form_key": "retrieval-survey",
        }
        self.get_inputs(scope, expected_count=2)
        self.get_inputs(
            {**scope, "submission_key": "retrieval-response-1"},
            expected_count=2,
        )
        self.get_inputs(
            {**scope, "question_key": "cost"},
            expected_count=1,
        )
        self.get_inputs(
            {"submission_key": "retrieval-response-1"},
            expected_status=422,
        )
        self.get_inputs(
            {**scope, "limit": 101},
            expected_status=422,
        )

    def submit_all_scenarios(self) -> None:
        self.submit_generic_inputs()
        self.submit_contextual_short_long()
        self.submit_many_topics_answer()
        self.submit_multi_question_submission()
        self.submit_related_same_question()
        self.submit_identical_answer_contexts()
        self.submit_question_version_checks()
        self.submit_theme_materialization_fixture()
        self.submit_error_cases()
        self.test_retrieval_api()

    def run_sql(self, query: str) -> bool:
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
            return False

        if result.returncode != 0:
            print(
                f"\nSQL command failed with exit code {result.returncode}. "
                "Check that the Compose stack is running.",
                file=sys.stderr,
            )
            return False
        return True

    def query_results(self) -> None:
        source = sql_literal(self.source)
        self.run_sql(
            f"""
SELECT
    inputs.id,
    questions.form_key,
    questions.question_key,
    inputs.submission_key,
    inputs.status,
    inputs.topic,
    COUNT(DISTINCT segments.id) AS segments,
    COUNT(DISTINCT embeddings.id) AS embeddings,
    array_agg(DISTINCT embeddings.embedding_representation)
        FILTER (WHERE embeddings.id IS NOT NULL)
        AS embedding_representations,
    inputs.original_text
FROM original_inputs AS inputs
LEFT JOIN questions
    ON questions.id = inputs.question_id
LEFT JOIN segment_inputs AS segments
    ON segments.original_input_id = inputs.id
LEFT JOIN input_embeddings AS embeddings
    ON embeddings.original_input_id = inputs.id
    OR embeddings.segment_input_id = segments.id
WHERE inputs.source = {source}
GROUP BY
    inputs.id,
    questions.form_key,
    questions.question_key
ORDER BY inputs.id;
""".strip()
        )

    def query_segments(self) -> None:
        source = sql_literal(self.source)
        self.run_sql(
            f"""
SELECT
    inputs.id AS original_input_id,
    questions.form_key,
    questions.question_key,
    segments.segment_order,
    segments.topic,
    segments.segment_text
FROM original_inputs AS inputs
LEFT JOIN questions
    ON questions.id = inputs.question_id
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
    suggestions.rationale,
    suggestions.materialized_theme_id,
    suggestions.materialized_at,
    CASE
        WHEN suggestions.materialized_at IS NULL THEN 'pending'
        ELSE 'materialized'
    END AS materialization_status
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

    def query_answers_by_question(self) -> None:
        source = sql_literal(self.source)
        self.run_sql(
            f"""
SELECT
    questions.form_key,
    questions.question_key,
    questions.question_version,
    questions.question_text,
    inputs.submission_key,
    inputs.id AS answer_id,
    inputs.original_text,
    inputs.topic,
    inputs.status
FROM questions
JOIN original_inputs AS inputs
    ON inputs.question_id = questions.id
WHERE questions.source = {source}
ORDER BY
    questions.form_key,
    questions.question_key,
    questions.question_version,
    inputs.id;
""".strip()
        )

    def query_answers_by_submission(self) -> None:
        source = sql_literal(self.source)
        self.run_sql(
            f"""
SELECT
    questions.form_key,
    inputs.submission_key,
    questions.question_key,
    questions.question_text,
    inputs.id AS answer_id,
    inputs.original_text,
    inputs.topic,
    inputs.status
FROM questions
JOIN original_inputs AS inputs
    ON inputs.question_id = questions.id
WHERE
    questions.source = {source}
    AND inputs.submission_key IS NOT NULL
ORDER BY questions.form_key, inputs.submission_key, inputs.id;
""".strip()
        )

    def query_answer_topic_themes(self) -> None:
        source = sql_literal(self.source)
        self.run_sql(
            f"""
WITH RECURSIVE theme_paths AS (
    SELECT
        themes.id AS starting_id,
        themes.id,
        themes.merged_into_id,
        ARRAY[themes.id]::bigint[] AS path
    FROM themes

    UNION ALL

    SELECT
        theme_paths.starting_id,
        parent.id,
        parent.merged_into_id,
        theme_paths.path || parent.id
    FROM theme_paths
    JOIN themes AS parent
        ON parent.id = theme_paths.merged_into_id
    WHERE NOT parent.id = ANY(theme_paths.path)
),
canonical_themes AS (
    SELECT starting_id, id AS canonical_id
    FROM theme_paths
    WHERE merged_into_id IS NULL
),
answer_topics AS (
    SELECT id AS answer_id, topic
    FROM original_inputs
    WHERE topic IS NOT NULL

    UNION

    SELECT original_input_id, topic
    FROM segment_inputs
    WHERE topic IS NOT NULL
)
SELECT
    questions.form_key,
    questions.question_key,
    inputs.submission_key,
    inputs.id AS answer_id,
    inputs.original_text,
    answer_topics.topic,
    canonical.id AS theme_id,
    canonical.name AS theme_name
FROM original_inputs AS inputs
LEFT JOIN questions
    ON questions.id = inputs.question_id
LEFT JOIN answer_topics
    ON answer_topics.answer_id = inputs.id
LEFT JOIN theme_topics
    ON lower(theme_topics.topic) = lower(answer_topics.topic)
LEFT JOIN canonical_themes
    ON canonical_themes.starting_id = theme_topics.theme_id
LEFT JOIN themes AS canonical
    ON canonical.id = canonical_themes.canonical_id
WHERE inputs.source = {source}
ORDER BY inputs.id, answer_topics.topic, canonical.name;
""".strip()
        )

    def assert_fixture_outcomes(self) -> None:
        source = sql_literal(self.source)
        passed = self.run_sql(
            f"""
DO $$
DECLARE
    actual_count INTEGER;
BEGIN
    IF EXISTS (
        SELECT 1
        FROM original_inputs
        WHERE
            source = {source}
            AND status NOT IN ('completed', 'ineligible')
    ) THEN
        RAISE EXCEPTION
            'one or more submitted inputs have not reached a terminal status';
    END IF;

    SELECT count(*) INTO actual_count
    FROM original_inputs
    WHERE source = {source} AND status = 'ineligible';
    IF actual_count <> 2 THEN
        RAISE EXCEPTION
            'eligibility: expected 2 ineligible inputs, found %',
            actual_count;
    END IF;

    SELECT count(*) INTO actual_count
    FROM original_inputs AS inputs
    JOIN questions
        ON questions.id = inputs.question_id
    WHERE
        questions.source = {source}
        AND questions.form_key = 'multi-question-survey'
        AND inputs.submission_key = 'multi-question-response-1';
    IF actual_count <> 4 THEN
        RAISE EXCEPTION
            'multi-question submission: expected 4 answers, found %',
            actual_count;
    END IF;

    SELECT count(*) INTO actual_count
    FROM segment_inputs AS segments
    JOIN original_inputs AS inputs
        ON inputs.id = segments.original_input_id
    JOIN questions
        ON questions.id = inputs.question_id
    WHERE
        questions.source = {source}
        AND questions.form_key = 'broad-feedback'
        AND questions.question_key = 'everything-to-improve';
    IF actual_count < 2 THEN
        RAISE EXCEPTION
            'many-topic answer: expected at least 2 segments, found %',
            actual_count;
    END IF;

    SELECT count(DISTINCT inputs.question_id) INTO actual_count
    FROM original_inputs AS inputs
    JOIN questions
        ON questions.id = inputs.question_id
    WHERE
        questions.source = {source}
        AND questions.form_key = 'identical-answers'
        AND inputs.original_text = 'No';
    IF actual_count <> 2 THEN
        RAISE EXCEPTION
            'identical answers: expected 2 question contexts, found %',
            actual_count;
    END IF;

    SELECT count(*) INTO actual_count
    FROM questions
    WHERE
        source = {source}
        AND form_key = 'versioned-survey'
        AND question_key = 'service-improvement';
    IF actual_count <> 2 THEN
        RAISE EXCEPTION
            'question versions: expected 2 immutable versions, found %',
            actual_count;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM original_inputs
        WHERE
            source = {source}
            AND submission_key = 'version-response-conflict'
    ) THEN
        RAISE EXCEPTION
            'conflicting question text unexpectedly created an answer';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM input_embeddings AS embeddings
        JOIN original_inputs AS inputs
            ON inputs.id = embeddings.original_input_id
        WHERE
            inputs.source = {source}
            AND inputs.question_id IS NOT NULL
            AND embeddings.embedding_representation <> 'question-answer'
    ) THEN
        RAISE EXCEPTION
            'contextual original input has a non-contextual embedding';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM input_embeddings AS embeddings
        JOIN original_inputs AS inputs
            ON inputs.id = embeddings.original_input_id
        WHERE
            inputs.source = {source}
            AND inputs.question_id IS NULL
            AND embeddings.embedding_representation <> 'answer-only'
    ) THEN
        RAISE EXCEPTION
            'generic original input has a contextual embedding';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM input_embeddings AS embeddings
        JOIN original_inputs AS inputs
            ON inputs.id = embeddings.original_input_id
        WHERE
            inputs.source = {source}
            AND inputs.question_id IS NULL
            AND inputs.status = 'completed'
            AND embeddings.embedding_representation = 'answer-only'
    ) THEN
        RAISE EXCEPTION
            'no completed generic input has an answer-only embedding';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM original_inputs
        WHERE
            source = {source}
            AND submission_key = 'non-responsive-context'
            AND status = 'ineligible'
    ) THEN
        RAISE EXCEPTION
            'non-responsive contextual answer is not ineligible';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM theme_suggestions AS suggestions
        JOIN theme_suggestion_evidence AS evidence
            ON evidence.suggestion_id = suggestions.id
        LEFT JOIN segment_inputs AS evidence_segment
            ON evidence_segment.id = evidence.segment_input_id
        JOIN original_inputs AS evidence_input
            ON evidence_input.id = COALESCE(
                evidence.original_input_id,
                evidence_segment.original_input_id
            )
        JOIN questions
            ON questions.id = evidence_input.question_id
        WHERE
            questions.source = {source}
            AND questions.form_key = 'purchase-theme'
            AND suggestions.materialized_at IS NOT NULL
    ) THEN
        RAISE EXCEPTION
            'purchase-theme fixture has no materialized suggestion';
    END IF;

    IF NOT EXISTS (
        SELECT tagged.theme_id
        FROM (
            SELECT
                theme_topics.theme_id,
                original_topics.topic
            FROM (
                SELECT inputs.id AS input_id, inputs.topic
                FROM original_inputs AS inputs
                WHERE inputs.topic IS NOT NULL

                UNION

                SELECT segments.original_input_id, segments.topic
                FROM segment_inputs AS segments
                WHERE segments.topic IS NOT NULL
            ) AS original_topics
            JOIN original_inputs AS inputs
                ON inputs.id = original_topics.input_id
            JOIN questions
                ON questions.id = inputs.question_id
            JOIN theme_topics
                ON lower(theme_topics.topic) = lower(original_topics.topic)
            WHERE
                questions.source = {source}
                AND questions.form_key = 'purchase-theme'
        ) AS tagged
        GROUP BY tagged.theme_id
        HAVING count(DISTINCT lower(tagged.topic)) >= 2
    ) THEN
        RAISE EXCEPTION
            'purchase-theme topics did not converge on one live theme';
    END IF;

    RAISE NOTICE 'all manual fixture assertions passed';
END;
$$;
""".strip()
        )
        self.checks += 1
        if not passed:
            self.failures += 1

    def query_all(self) -> None:
        self.query_results()
        self.query_segments()
        self.query_worker_jobs()
        self.query_theme_suggestions()
        self.query_answers_by_question()
        self.query_answers_by_submission()
        self.query_answer_topic_themes()


def print_menu(source: str) -> None:
    print(
        f"""
Triage processor manual tests
Current source: {source}

Submission and API scenarios
  G. Generic single-topic, multi-topic, and ineligible inputs
  C. Short and long contextual answers
  M. One long contextual answer covering many topics
  Q. Multiple questions in one submission
  R. Related answers to the same question
  X. Identical answer text under different questions
  V. Question conflict and version behavior
  T. Cost/checkout topic-to-theme materialization fixture
  E. Invalid payloads (expects HTTP 422)
  K. Retrieval API scope, submission, question, and pagination checks
  A. Run every submission and API scenario

Database inspections
  B. Assert all fixture outcomes (fails until workers finish)
  I. Input status, topics, segments, and embedding counts
  S. Generated segments (especially useful after M)
  J. Worker jobs and failures
  H. Questions and answers
  U. Multi-question submissions
  P. Pending/materialized theme suggestions
  L. Answer → topic → canonical themes
  Z. Run every database inspection

  ?. Show this menu
  0. Exit
""".strip()
    )


def default_source() -> str:
    return f"manual-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Interactively submit manual test inputs and inspect results.",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
    parser.add_argument(
        "--run",
        metavar="KEY",
        help=(
            "Run one menu key non-interactively, for example A for all "
            "scenarios or Z for all inspections."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runner = ManualTestRunner(api_url=args.api_url, source=args.source)
    actions = {
        "G": runner.submit_generic_inputs,
        "C": runner.submit_contextual_short_long,
        "M": runner.submit_many_topics_answer,
        "Q": runner.submit_multi_question_submission,
        "R": runner.submit_related_same_question,
        "X": runner.submit_identical_answer_contexts,
        "V": runner.submit_question_version_checks,
        "T": runner.submit_theme_materialization_fixture,
        "E": runner.submit_error_cases,
        "K": runner.test_retrieval_api,
        "A": runner.submit_all_scenarios,
        "B": runner.assert_fixture_outcomes,
        "I": runner.query_results,
        "S": runner.query_segments,
        "J": runner.query_worker_jobs,
        "H": runner.query_answers_by_question,
        "U": runner.query_answers_by_submission,
        "P": runner.query_theme_suggestions,
        "L": runner.query_answer_topic_themes,
        "Z": runner.query_all,
    }

    if args.run is not None:
        key = args.run.strip().upper()
        action = actions.get(key)
        if action is None:
            valid_keys = ", ".join(actions)
            raise SystemExit(
                f"Unknown --run key {args.run!r}. Valid keys: {valid_keys}"
            )
        print(
            f"Running key {key} with source {runner.source!r} "
            f"against {runner.api_url}"
        )
        action()
        if runner.checks:
            runner.print_summary()
        raise SystemExit(1 if runner.failures else 0)

    while True:
        print_menu(runner.source)
        try:
            choice = input("\nEnter a key: ").strip().upper()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            return

        if choice == "0":
            print("Exiting.")
            return
        if choice == "?":
            continue

        action = actions.get(choice)
        if action is None:
            print(f"\nUnknown key {choice!r}. Press ? to show the menu.\n")
            continue

        checks_before = runner.checks
        action()
        if runner.checks > checks_before:
            runner.print_summary()
        input("\nPress Enter to return to the menu...")
        print()


if __name__ == "__main__":
    main()
