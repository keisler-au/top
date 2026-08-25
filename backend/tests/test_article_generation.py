import unittest

from triage_processor.api.generation_schemas import GeneratedArticle
from triage_processor.articles import normalize_topic
from triage_processor.templates import render_template, sanitize_html, validate_template_source
from triage_processor.workers.article_generation import (
    GenerationJob,
    claim_job,
    fail_job,
    validate_generated_article,
)


class AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeConnection:
    def __init__(self, claimed=None):
        self.claimed = claimed
        self.fetchrow_calls = []
        self.execute_calls = []

    async def fetchrow(self, query, *values):
        self.fetchrow_calls.append((query, values))
        return self.claimed

    async def execute(self, query, *values):
        self.execute_calls.append((query, values))
        return "UPDATE 1"


class FakePool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return AsyncContext(self.connection)


class TemplateSecurityTests(unittest.TestCase):
    def test_validates_and_renders_escaped_structured_content(self):
        source = (
            "<article><h1>{{title}}</h1><p>{{standfirst}}</p>"
            "<main>{{article_body}}</main></article>"
        )

        placeholders = validate_template_source(source)
        rendered = render_template(
            source,
            {
                "title": "<script>alert(1)</script>",
                "standfirst": "A & B",
                "sections": [
                    {
                        "heading": "Safe <heading>",
                        "paragraphs": ["Evidence <img src=x onerror=alert(1)>"],
                    }
                ],
            },
        )

        self.assertEqual(placeholders, ["title", "standfirst", "article_body"])
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<img", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("A &amp; B", rendered)

    def test_rejects_executable_template_markup(self):
        unsafe_sources = [
            "<article><script>x</script><h1>{{title}}</h1>{{article_body}}</article>",
            '<article onload="x"><h1>{{title}}</h1>{{article_body}}</article>',
            '<article><a href="javascript:x">x</a><h1>{{title}}</h1>{{article_body}}</article>',
            "<form><h1>{{title}}</h1>{{article_body}}</form>",
        ]

        for source in unsafe_sources:
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    validate_template_source(source)

    def test_rejects_malformed_template_markup(self):
        malformed_sources = [
            "<article><h1>{{title}}</article>{{article_body}}",
            "<article><h1>{{title}}</h1>{{article_body}}",
        ]

        for source in malformed_sources:
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    validate_template_source(source)

    def test_requires_supported_essential_placeholders(self):
        with self.assertRaisesRegex(ValueError, "title"):
            validate_template_source("<article>{{article_body}}</article>")
        with self.assertRaisesRegex(ValueError, "unsupported"):
            validate_template_source(
                "<article><h1>{{title}}</h1>{{article_body}}{{code}}</article>"
            )

    def test_sanitizes_persisted_editor_html(self):
        rendered = sanitize_html(
            '<article onload="bad()"><h1>Safe</h1><script>bad()</script></article>'
        )

        self.assertNotIn("onload", rendered)
        self.assertNotIn("script", rendered)
        self.assertIn("<h1>Safe</h1>", rendered)


class GeneratedArticleValidationTests(unittest.TestCase):
    def test_accepts_grounded_topic_article(self):
        generated = GeneratedArticle.model_validate(
            {
                "title": "Parks",
                "standfirst": "Residents support parks.",
                "sections": [
                    {
                        "heading": "Demand",
                        "paragraphs": ["Residents requested more green space."],
                        "evidence_ids": ["segment:2"],
                    }
                ],
                "theme_ids": [],
                "topic_keys": ["indoor green space"],
            }
        )

        validate_generated_article(
            generated,
            taxonomy_type="topic",
            taxonomy_key="indoor green space",
            evidence_ids={"segment:2"},
            evidence_topic_keys={"indoor green space"},
        )

    def test_topic_identity_trims_without_collapsing_internal_whitespace(self):
        generated = GeneratedArticle.model_validate(
            {
                "title": "Parks",
                "sections": [
                    {
                        "heading": "Demand",
                        "paragraphs": ["Claim"],
                        "evidence_ids": ["segment:2"],
                    }
                ],
                "theme_ids": [],
                "topic_keys": ["  Indoor  Green Space  "],
            }
        )

        validate_generated_article(
            generated,
            taxonomy_type="topic",
            taxonomy_key="indoor  green space",
            evidence_ids={"segment:2"},
            evidence_topic_keys={"indoor  green space"},
        )

    def test_rejects_citations_and_tags_outside_frozen_job(self):
        generated = GeneratedArticle.model_validate(
            {
                "title": "Parks",
                "sections": [
                    {
                        "heading": "Demand",
                        "paragraphs": ["Claim"],
                        "evidence_ids": ["segment:999"],
                    }
                ],
                "theme_ids": [],
                "topic_keys": ["different topic"],
            }
        )

        with self.assertRaisesRegex(ValueError, "outside the job"):
            validate_generated_article(
                generated,
                taxonomy_type="topic",
                taxonomy_key="indoor green space",
                evidence_ids={"segment:2"},
                evidence_topic_keys={"indoor green space"},
            )


class TopicNormalizationTests(unittest.TestCase):
    def test_matches_dashboard_lower_trim_contract(self):
        self.assertEqual(
            normalize_topic("  Cost  Barriers  "),
            ("cost  barriers", "Cost  Barriers"),
        )


class GenerationQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_claims_pending_or_expired_job_with_owned_lease(self):
        connection = FakeConnection(claimed={"id": 9, "attempts": 2})

        job = await claim_job(
            FakePool(connection),
            locked_by="generator-1",
            lease_seconds=600,
        )

        self.assertEqual(
            job,
            GenerationJob(id=9, locked_by="generator-1", attempts=2),
        )
        query, values = connection.fetchrow_calls[0]
        self.assertIn("FOR UPDATE SKIP LOCKED", query)
        self.assertIn("status = 'processing'", query)
        self.assertEqual(values, (600, "generator-1"))

    async def test_retries_then_dead_letters_with_bounded_backoff(self):
        retry_connection = FakeConnection()
        await fail_job(
            FakePool(retry_connection),
            GenerationJob(id=9, locked_by="generator-1", attempts=2),
            RuntimeError("temporary"),
            max_attempts=3,
            retry_base_seconds=10,
            retry_max_seconds=60,
        )
        _, retry_values = retry_connection.execute_calls[0]
        self.assertEqual(retry_values, (9, "generator-1", "pending", 20, "temporary"))

        failed_connection = FakeConnection()
        await fail_job(
            FakePool(failed_connection),
            GenerationJob(id=9, locked_by="generator-1", attempts=3),
            ValueError("invalid response"),
            max_attempts=3,
            retry_base_seconds=10,
            retry_max_seconds=60,
        )
        _, failed_values = failed_connection.execute_calls[0]
        self.assertEqual(failed_values[2], "failed")
