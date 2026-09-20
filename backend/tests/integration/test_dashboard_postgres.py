import asyncio
import json
import os
from pathlib import Path
import unittest
from uuid import uuid4

import asyncpg
from fastapi import FastAPI
import httpx

from triage_processor.api.routes import articles, dashboard, generation, form_sources, inputs, operations, taxonomy_review, public_site
from triage_processor.articles import canonical_theme_ids
from triage_processor.taxonomy_snapshots import SnapshotRequest, create_taxonomy_snapshot
from triage_processor.taxonomy_stage_quality import (
    THRESHOLD_VERSION,
    attestation_input_sha256,
    compute_run_quality,
)
from triage_processor.taxonomy_stages import claim_next_stage, complete_stage
from triage_processor.workers.article_generation import claim_job, process_job

DSN = os.environ.get("TRIAGE_TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[3] / "infrastructure/postgres"
if not ROOT.exists():
    ROOT = Path("/infrastructure/postgres")


def snapshot_sql(path):
    """Expand the snapshot's psql-relative includes without changing its DDL."""
    return "\n".join(
        snapshot_sql(path.parent / line[4:].strip())
        if line.startswith("\\ir ") else line
        for line in path.read_text().splitlines()
    )


@unittest.skipUnless(DSN, "Set TRIAGE_TEST_DATABASE_URL or use compose.test.yaml")
class DashboardPostgresTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._operator_environment = {
            "TAXONOMY_MUTATION_TOKEN": os.environ.get("TAXONOMY_MUTATION_TOKEN"),
            "TAXONOMY_REVIEW_TOKEN": os.environ.get("TAXONOMY_REVIEW_TOKEN"),
            "OPERATIONS_RATE_LIMIT_REQUESTS": os.environ.get("OPERATIONS_RATE_LIMIT_REQUESTS"),
            "OPERATIONS_RATE_LIMIT_WINDOW_SECONDS": os.environ.get("OPERATIONS_RATE_LIMIT_WINDOW_SECONDS"),
        }
        os.environ.update({
            "TAXONOMY_MUTATION_TOKEN": "test-mutation-token",
            "TAXONOMY_REVIEW_TOKEN": "test-review-token",
            "OPERATIONS_RATE_LIMIT_REQUESTS": "30",
            "OPERATIONS_RATE_LIMIT_WINDOW_SECONDS": "60",
        })
        self.addAsyncCleanup(self._restore_operator_environment)
        self.schema = "test_" + uuid4().hex
        self.admin = await asyncpg.connect(DSN)
        self.addAsyncCleanup(self.admin.close)
        await self.admin.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
        await self.admin.execute("DROP SCHEMA IF EXISTS taxonomy_legacy_archive CASCADE")
        await self.admin.execute(f'CREATE SCHEMA "{self.schema}"')
        self.addAsyncCleanup(self.admin.execute, f'DROP SCHEMA "{self.schema}" CASCADE')
        await self.admin.execute(f'SET search_path TO "{self.schema}", public')
        await self.admin.execute(snapshot_sql(ROOT / "init.sql"))
        self.pool = await asyncpg.create_pool(
            DSN, min_size=1, max_size=4,
            server_settings={"search_path": f'"{self.schema}", public', "statement_timeout": "5000"},
        )
        self.addAsyncCleanup(self.pool.close)
        self.app = FastAPI()
        for router in (articles.router, dashboard.router, generation.router, form_sources.router, inputs.router, operations.router, taxonomy_review.router, public_site.router):
            self.app.include_router(router)
        self.app.state.db_pool = self.pool
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test",
            headers={"Authorization": "Bearer test-mutation-token"},
        )
        self.addAsyncCleanup(self.client.aclose)
        await self.seed()

    def _restore_operator_environment(self):
        for key, value in self._operator_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    async def seed(self):
        # Repeated text remains distinct evidence. Split originals never count twice.
        await self.admin.execute("""
            INSERT INTO original_inputs (original_text, source, status, created_at) VALUES
            ('Repeated answer', 'test', 'completed', '2026-01-01'),
            ('Repeated answer', 'test', 'completed', '2026-01-01'),
            ('Split answer', 'test', 'completed', '2026-01-01'),
            ('Not yet complete', 'test', 'new', '2026-01-01');
            INSERT INTO segment_inputs (original_input_id, segment_order, segment_text) VALUES
            (3, 0, 'First cost point'), (3, 1, 'Second cost point'),
            (3, 2, 'Delivery point'), (4, 0, 'Pending parent');
        """)
        # Dashboard and article readers deliberately consume only this frozen,
        # published run. The legacy rows above must never be a fallback.
        await self.admin.execute("""
            INSERT INTO input_embeddings (original_input_id, embedding, embedding_model, embedding_representation) VALUES
                (1, '[1,0]'::vector, 'fixture', 'fixture'), (2, '[1,0]'::vector, 'fixture', 'fixture');
            INSERT INTO input_embeddings (segment_input_id, embedding, embedding_model, embedding_representation) VALUES
                (1, '[1,0]'::vector, 'fixture', 'fixture'), (2, '[1,0]'::vector, 'fixture', 'fixture'),
                (3, '[0,1]'::vector, 'fixture', 'fixture');
            INSERT INTO taxonomy_runs (
                source_cutoff, source_snapshot_sha256, configuration, configuration_sha256,
                embedding_model, embedding_representation, embedding_dimension, clustering_model,
                topic_model, theme_model, topic_prompt_version, theme_prompt_version
            ) VALUES (
                CURRENT_TIMESTAMP, repeat('a', 64), '{}'::jsonb, repeat('b', 64),
                'fixture', 'fixture', 2, 'fixture', 'fixture', 'fixture', 'fixture', 'fixture'
            );
            INSERT INTO taxonomy_run_evidence(taxonomy_run_id, original_input_id, embedding_id) VALUES
                (1, 1, 1), (1, 2, 2);
            INSERT INTO taxonomy_run_evidence(taxonomy_run_id, original_input_id, segment_input_id, embedding_id) VALUES
                (1, 3, 1, 3), (1, 3, 2, 4), (1, 3, 3, 5);
            INSERT INTO topics DEFAULT VALUES; INSERT INTO topics DEFAULT VALUES;
            INSERT INTO topic_revisions(taxonomy_run_id, topic_id, cluster_key, name, normalized_name, literal_description, support_count, centroid, continuity_decision) VALUES
                (1, 1, 'cost', 'Cost', 'cost', 'Cost evidence', 4, '[1,0]'::vector, 'new'),
                (1, 2, 'delivery', 'Delivery', 'delivery', 'Delivery evidence', 1, '[0,1]'::vector, 'new');
            INSERT INTO topic_memberships(taxonomy_run_id, topic_revision_id, evidence_id) VALUES
                (1, 1, 1), (1, 1, 2), (1, 1, 3), (1, 1, 4), (1, 2, 5);
            INSERT INTO taxonomy_candidate_themes(taxonomy_run_id, name, description, rationale, inference_request, inference_response) VALUES
                (1, 'Alpha', 'Cost', 'fixture', '{}'::jsonb, '{}'::jsonb),
                (1, 'Beta', 'Cost and delivery', 'fixture', '{}'::jsonb, '{}'::jsonb),
                (1, 'Empty', 'No links', 'fixture', '{}'::jsonb, '{}'::jsonb);
            INSERT INTO taxonomy_candidate_theme_topics(taxonomy_run_id, candidate_theme_id, topic_revision_id) VALUES
                (1, 1, 1), (1, 2, 1), (1, 2, 2);
            INSERT INTO taxonomy_reconciled_themes(taxonomy_run_id, canonical_candidate_theme_id, normalized_name, topic_set_sha256) VALUES
                (1, 1, 'alpha', repeat('a', 64)), (1, 2, 'beta', repeat('b', 64)), (1, 3, 'empty', repeat('c', 64));
            INSERT INTO taxonomy_reconciled_theme_antecedents(taxonomy_run_id, reconciled_theme_id, candidate_theme_id, relationship) VALUES
                (1, 1, 1, 'canonical'), (1, 2, 2, 'canonical'), (1, 3, 3, 'canonical');
            UPDATE taxonomy_runs SET status='running', started_at=CURRENT_TIMESTAMP WHERE id=1;
            UPDATE taxonomy_runs SET status='ready_for_review', completed_at=CURRENT_TIMESTAMP WHERE id=1;
            SELECT materialize_taxonomy_theme_revisions(1);
            UPDATE taxonomy_runs SET status='published', decision_by='fixture', decision_at=CURRENT_TIMESTAMP, published_at=CURRENT_TIMESTAMP WHERE id=1;
        """)

    async def get(self, path):
        response = await self.client.get(path)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def create_article(self, *, evidence="original:1", title="Article", themes=None):
        response = await self.client.post("/articles", json={
            "title": title, "structured_content": {"sections": [{"heading": "Cost", "paragraphs": ["Evidence"]}]},
            "rendered_html": "<article><h1>Article</h1><p>Evidence</p></article>",
            "theme_ids": themes if themes is not None else [1, 2],
            "topics": [{"name": "Cost"}, {"name": " COST "}, {"name": "Delivery"}],
            "evidence": [{"evidence_id": evidence}],
        })
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    async def transition(self, article, action, expected=200):
        response = await self.client.post(f"/articles/{article['id']}/{action}", json={})
        self.assertEqual(response.status_code, expected, response.text)
        return response.json()

    async def test_canonical_evidence_and_aliases_do_not_multiply_counts(self):
        self.assertEqual(await self.get('/dashboard/summary'), {
            "evidence_count": 5, "theme_count": 3, "topic_count": 2, "article_count": 0,
            "awaiting_approval_count": 0, "failed_generation_count": 0,
        })
        topics = await self.get('/taxonomy?type=topic')
        self.assertEqual([(row['key'], row['evidence_count']) for row in topics['items']], [('1', 4), ('2', 1)])
        themes = await self.get('/taxonomy?type=theme')
        self.assertEqual([(row['name'], row['evidence_count']) for row in themes['items']], [('Beta', 5), ('Alpha', 4), ('Empty', 0)])
        evidence = await self.get('/taxonomy/theme/1/evidence')
        self.assertEqual([row['id'] for row in evidence['items']], ['segment:1', 'segment:2', 'original:2', 'original:1'])
        self.assertEqual(evidence['total'], 4)
        self.assertEqual(await canonical_theme_ids(self.admin, [1]), [1])
        with self.assertRaisesRegex(ValueError, 'invalid theme'):
            await canonical_theme_ids(self.admin, [4, 5, 6])
        self.assertEqual((await self.client.get('/taxonomy/theme/6')).status_code, 404)

    async def test_inputs_use_only_the_published_snapshot_for_coverage(self):
        payload = await self.get('/inputs')
        by_id = {item['id']: item for item in payload}
        self.assertEqual(by_id[1]['taxonomy_state'], 'classified')
        self.assertEqual(by_id[1]['published_taxonomy_run_id'], 1)
        self.assertEqual(by_id[1]['topics'], [{'id': 1, 'name': 'Cost'}])
        self.assertEqual(by_id[1]['themes'], [{'id': 1, 'name': 'Alpha', 'description': 'Cost'}, {'id': 2, 'name': 'Beta', 'description': 'Cost and delivery'}])
        self.assertEqual(by_id[3]['topics'], [
            {'id': 1, 'name': 'Cost'}, {'id': 2, 'name': 'Delivery'},
        ])
        # This input was excluded from the published cutoff, so it must not
        # acquire a classification from mutable source state.
        self.assertEqual(by_id[4]['taxonomy_state'], 'pending_classification')
        self.assertEqual(by_id[4]['topics'], [])
        self.assertEqual(by_id[4]['themes'], [])
        self.assertNotIn('topic', by_id[4])

    async def test_quality_attestation_is_computed_once_and_immutable(self):
        facts = await compute_run_quality(self.pool, 1)
        self.assertEqual(facts.evidence_count, 5)
        row = await self.admin.fetchrow("""
            SELECT metrics, thresholds, threshold_version, gate_passed, failures, input_sha256
            FROM taxonomy_release_attestations WHERE taxonomy_run_id=1
        """)
        metrics = json.loads(row["metrics"]) if isinstance(row["metrics"], str) else dict(row["metrics"])
        self.assertEqual(row["threshold_version"], THRESHOLD_VERSION)
        self.assertEqual(row["input_sha256"], attestation_input_sha256(metrics))
        self.assertFalse(row["gate_passed"])
        self.assertIn("snapshot_incomplete", row["failures"])
        await compute_run_quality(self.pool, 1)
        self.assertEqual(
            await self.admin.fetchval(
                "SELECT count(*) FROM taxonomy_release_attestations WHERE taxonomy_run_id=1"
            ),
            1,
        )
        with self.assertRaises(asyncpg.PostgresError):
            await self.admin.execute(
                "UPDATE taxonomy_release_attestations SET gate_passed=TRUE WHERE taxonomy_run_id=1"
            )
        with self.assertRaises(asyncpg.PostgresError):
            await self.admin.execute(
                "DELETE FROM taxonomy_release_attestations WHERE taxonomy_run_id=1"
            )

    async def test_publication_is_deployment_default_off(self):
        response = await self.client.post("/taxonomy-runs/1/publish", json={
            "expected_updated_at": "2026-01-01T00:00:00Z", "operator": "fixture",
        })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "taxonomy_publication_disabled")

    async def test_database_publication_rejects_absent_or_failed_attestation(self):
        async def candidate_run() -> int:
            return await self.admin.fetchval("""
                INSERT INTO taxonomy_runs(
                    source_cutoff, source_snapshot_sha256, configuration, configuration_sha256,
                    embedding_model, embedding_representation, embedding_dimension,
                    clustering_model, topic_model, theme_model, topic_prompt_version, theme_prompt_version
                ) VALUES(
                    CURRENT_TIMESTAMP, repeat('d', 64), '{"version":"fixture"}'::jsonb, repeat('e', 64),
                    'fixture', 'fixture', 2, 'fixture', 'fixture', 'fixture', 'fixture', 'fixture'
                ) RETURNING id
            """)

        absent = await candidate_run()
        with self.assertRaisesRegex(asyncpg.PostgresError, "gate is not attested"):
            await self.admin.fetchval(
                "SELECT publish_taxonomy_run($1, CURRENT_TIMESTAMP, 'fixture')", absent
            )
        failed = await candidate_run()
        await self.admin.execute("""
            INSERT INTO taxonomy_release_attestations(
                taxonomy_run_id, metrics, thresholds, threshold_version, gate_passed, failures, input_sha256
            ) VALUES($1, '{}'::jsonb, '{}'::jsonb, 'fixture', FALSE, ARRAY['fixture_failure'], repeat('f', 64))
        """, failed)
        with self.assertRaisesRegex(asyncpg.PostgresError, "gate is not attested"):
            await self.admin.fetchval(
                "SELECT publish_taxonomy_run($1, CURRENT_TIMESTAMP, 'fixture')", failed
            )


    async def test_operations_summary_is_bounded_and_content_safe(self):
        await self.admin.execute("""
            UPDATE worker_jobs
            SET status = 'failed', locked_at = NULL, locked_by = NULL,
                last_error = 'must never be exposed', updated_at = CURRENT_TIMESTAMP
            WHERE job_type = 'eligibility_segmentation';
            INSERT INTO form_sources (source, form_id, spreadsheet_id, last_error)
            VALUES ('google-sheets', 'ops', 'ops-sheet', 'credential-like failure');
            INSERT INTO article_generation_jobs (
                status, strategy, taxonomy_type, taxonomy_key, taxonomy_name,
                template_version_id, status_url, last_error
            ) VALUES (
                'failed', 'specific', 'topic', 'cost', 'Cost', 1, '/article-generation-jobs/1', 'raw model output'
            );
        """)
        payload = await self.get('/operations/summary')
        self.assertEqual(payload['article_generation']['failed'], 1)
        self.assertEqual(payload['enabled_form_sources'], 1)
        self.assertEqual(payload['form_poll_failures'], 1)
        stages = {item['stage']: item for item in payload['evidence_pipeline']}
        self.assertEqual(stages['eligibility_segmentation']['failed'], 1)
        self.assertNotIn('last_error', str(payload))
        self.assertNotIn('must never be exposed', str(payload))
        self.assertNotIn('credential-like failure', str(payload))

    async def test_operations_and_taxonomy_routes_require_the_right_operator_role(self):
        anonymous = httpx.AsyncClient(transport=httpx.ASGITransport(self.app), base_url="http://test")
        self.addAsyncCleanup(anonymous.aclose)
        self.assertEqual((await anonymous.get("/operations/summary")).status_code, 401)
        self.assertEqual((await anonymous.post("/taxonomy-runs", json=self.snapshot_payload())).status_code, 401)
        malformed = httpx.AsyncClient(
            transport=httpx.ASGITransport(self.app), base_url="http://test",
            headers={"Authorization": "Basic not-a-bearer-token"},
        )
        self.addAsyncCleanup(malformed.aclose)
        self.assertEqual((await malformed.get("/operations/summary")).status_code, 401)

        reviewer = httpx.AsyncClient(
            transport=httpx.ASGITransport(self.app), base_url="http://test",
            headers={"Authorization": "Bearer test-review-token"},
        )
        self.addAsyncCleanup(reviewer.aclose)
        self.assertEqual((await reviewer.get("/operations/summary")).status_code, 200)
        self.assertEqual((await reviewer.get("/taxonomy-runs/1")).status_code, 200)
        self.assertEqual((await reviewer.post("/taxonomy-runs/1/reject", json={
            "expected_updated_at": "2026-01-01T00:00:00Z", "operator": "reviewer",
        })).status_code, 401)

    async def test_operator_routes_fail_closed_when_tokens_are_unconfigured(self):
        os.environ.pop("TAXONOMY_MUTATION_TOKEN")
        os.environ.pop("TAXONOMY_REVIEW_TOKEN")
        response = await self.client.get("/operations/summary")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], {"code": "operations_auth_unconfigured"})

    async def test_mutation_token_can_read_without_a_separate_review_token(self):
        os.environ.pop("TAXONOMY_REVIEW_TOKEN")
        self.assertEqual((await self.client.get("/operations/summary")).status_code, 200)

    async def test_operations_rate_limit_and_taxonomy_error_redaction(self):
        os.environ["OPERATIONS_RATE_LIMIT_REQUESTS"] = "2"
        os.environ["OPERATIONS_RATE_LIMIT_WINDOW_SECONDS"] = "3600"
        responses = await asyncio.gather(*[
            self.client.get("/operations/summary") for _ in range(5)
        ])
        self.assertEqual(sorted(response.status_code for response in responses), [200, 200, 429, 429, 429])
        limited = next(response for response in responses if response.status_code == 429)
        self.assertEqual(limited.json()["detail"], {"code": "operations_rate_limited"})

        # Mutation requests use a separate bucket; an invalid durable transition
        # must return a bounded code instead of its PostgreSQL error text.
        rejected = await self.client.post("/taxonomy-runs/1/schedule")
        self.assertEqual(rejected.status_code, 409)
        self.assertEqual(rejected.json()["detail"], {"code": "taxonomy_schedule_conflict"})

    async def test_article_lifecycle_changes_coverage_and_recommendations(self):
        approved = await self.create_article(themes=[1, 2])
        self.assertEqual(approved['theme_ids'], [1, 2])
        self.assertEqual(len(approved['topics']), 2)
        await self.transition(approved, 'submit')
        await self.transition(approved, 'approve')
        draft = await self.create_article()
        ready = await self.create_article()
        await self.transition(ready, 'submit')
        archived = await self.create_article()
        await self.transition(archived, 'archive')
        summary = await self.get('/dashboard/summary')
        self.assertEqual(summary['article_count'], 3)
        self.assertEqual(summary['awaiting_approval_count'], 1)
        for kind, key in [('theme', '1'), ('theme', '2'), ('topic', '1'), ('topic', '2')]:
            item = await self.get(f'/taxonomy/{kind}/{key}')
            self.assertEqual((item['article_count'], item['approved_article_count']), (3, 1))
        item = await self.get('/taxonomy/theme/1')
        self.assertEqual((item['evidence_count'], item['article_count'], item['approved_article_count']), (4, 3, 1))
        await self.transition(approved, 'archive')
        item = await self.get('/taxonomy/theme/1')
        self.assertEqual((item['article_count'], item['approved_article_count'], item['coverage_state']), (2, 0, 'uncovered'))
        await self.transition(draft, 'approve', 409)

    async def test_approval_projection_is_atomic_and_reapproval_preserves_history(self):
        draft = await self.create_article(title="First public title", themes=[1])
        self.assertEqual(
            await self.admin.fetchval("SELECT count(*) FROM article_publications WHERE article_id=$1", draft["id"]),
            0,
        )
        review = await self.create_article(title="Review only")
        await self.transition(review, "submit")
        archived = await self.create_article(title="Archived only")
        await self.transition(archived, "archive")
        self.assertEqual(await self.admin.fetchval("SELECT count(*) FROM article_publications"), 0)

        await self.transition(draft, "submit")
        approved = await self.transition(draft, "approve")
        first = await self.admin.fetchrow("""
            SELECT approved_revision_id, slug, first_published_at, updated_at
            FROM article_publications WHERE article_id=$1
        """, draft["id"])
        self.assertEqual(first["approved_revision_id"], approved["current_revision"]["id"])
        self.assertEqual(first["slug"], f"first-public-title-{draft['id']}")
        self.assertEqual(
            [(row["stable_theme_id"], row["display_name"]) for row in await self.admin.fetch("""
                SELECT stable_theme_id, display_name FROM article_publication_themes
                WHERE article_id=$1 AND approved_revision_id=$2
            """, draft["id"], first["approved_revision_id"])],
            [(1, "Alpha")],
        )

        await self.transition(approved, "return-to-draft")
        revised = await self.client.patch(f"/articles/{draft['id']}", json={
            "title": "Revised public title",
            "theme_ids": [2],
            "expected_revision_id": approved["current_revision"]["id"],
        })
        self.assertEqual(revised.status_code, 200, revised.text)
        await self.transition(revised.json(), "submit")
        reapproved = await self.transition(revised.json(), "approve")
        current = await self.admin.fetchrow("""
            SELECT approved_revision_id, slug, first_published_at, updated_at
            FROM article_publications WHERE article_id=$1
        """, draft["id"])
        self.assertEqual(current["approved_revision_id"], reapproved["current_revision"]["id"])
        self.assertNotEqual(current["approved_revision_id"], first["approved_revision_id"])
        self.assertEqual(current["slug"], first["slug"])
        self.assertEqual(current["first_published_at"], first["first_published_at"])
        self.assertGreaterEqual(current["updated_at"], first["updated_at"])
        snapshots = await self.admin.fetch("""
            SELECT approved_revision_id, stable_theme_id, display_name
            FROM article_publication_themes WHERE article_id=$1
            ORDER BY approved_revision_id, stable_theme_id
        """, draft["id"])
        self.assertEqual(
            [(row["approved_revision_id"], row["stable_theme_id"], row["display_name"]) for row in snapshots],
            [
                (first["approved_revision_id"], 1, "Alpha"),
                (current["approved_revision_id"], 2, "Beta"),
            ],
        )

    async def test_approval_projection_failure_rolls_back_the_transition(self):
        article = await self.create_article()
        await self.transition(article, "submit")
        await self.admin.execute("""
            CREATE FUNCTION fail_publication_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'test publication snapshot failure'; END $$;
            CREATE TRIGGER fail_publication_snapshot
            BEFORE INSERT ON article_publication_themes
            FOR EACH ROW EXECUTE FUNCTION fail_publication_snapshot();
        """)
        with self.assertRaises(asyncpg.RaiseError):
            await self.transition(article, "approve")
        row = await self.get(f"/articles/{article['id']}")
        self.assertEqual(row["status"], "ready_for_review")
        self.assertIsNone(row["approved_at"])
        self.assertEqual(
            await self.admin.fetchval("SELECT count(*) FROM article_publications WHERE article_id=$1", article["id"]),
            0,
        )
        self.assertEqual(
            await self.admin.fetchval("SELECT count(*) FROM article_audit WHERE article_id=$1 AND action='approved'", article["id"]),
            0,
        )

    async def test_internal_public_site_renders_only_active_approved_projections(self):
        article = await self.create_article(title="Public <title>", themes=[1, 2])
        await self.transition(article, "submit")
        approved = await self.transition(article, "approve")
        slug = f"public-title-{article['id']}"
        for path in ("/_site/", "/_site/insights", "/_site/themes", "/_site/about", "/_site/robots.txt", "/_site/sitemap.xml", f"/_site/insights/{slug}", "/_site/themes/1-alpha"):
            response = await self.client.get(path)
            self.assertEqual(response.status_code, 200, (path, response.text))
        detail = (await self.client.get(f"/_site/insights/{slug}")).text
        self.assertIn("<main", detail)
        self.assertIn('href="#main"', detail)
        self.assertEqual(detail.count("<h1>"), 1)
        self.assertIn("Public &lt;title&gt;", detail)
        self.assertNotIn("original_input_id", detail)
        self.assertNotIn("submission_key", detail)
        self.assertIn('rel="canonical"', detail)
        self.assertIn("Evidence", detail)
        sitemap = (await self.client.get("/_site/sitemap.xml")).text
        self.assertIn(f"/insights/{slug}", sitemap)
        self.assertNotIn("/_site/", sitemap)
        self.assertEqual((await self.client.get("/_site/insights?x=" + "a" * 121)).status_code, 404)
        self.assertEqual((await self.client.get("/_site/insights?page=1000")).status_code, 404)
        self.assertEqual((await self.client.get("/_site/themes/999-unknown")).status_code, 404)
        self.assertEqual((await self.client.get("/_site/not-a-route")).status_code, 404)
        await self.transition(approved, "archive")
        self.assertEqual((await self.client.get(f"/_site/insights/{slug}")).status_code, 404)

    async def test_stable_pagination_and_recommendation_ties(self):
        for strategy in ['least-covered', 'most-evidence']:
            rows = (await self.get(f'/recommendations/articles?type=theme&strategy={strategy}'))['items']
            self.assertEqual([row['name'] for row in rows], ['Beta', 'Alpha'])
        article = await self.create_article(themes=[2])
        await self.transition(article, 'submit')
        await self.transition(article, 'approve')
        rows = (await self.get('/recommendations/articles?type=theme&strategy=least-covered'))['items']
        self.assertEqual([row['name'] for row in rows], ['Alpha', 'Beta'])
        pages = [await self.get(f'/taxonomy?type=theme&sort=evidence&direction=desc&page_size=1&page={page}') for page in range(1, 4)]
        self.assertEqual([page['items'][0]['name'] for page in pages], ['Beta', 'Alpha', 'Empty'])
        pages = [await self.get(f'/taxonomy/theme/1/evidence?page_size=1&page={page}') for page in range(1, 5)]
        self.assertEqual([page['items'][0]['id'] for page in pages], ['segment:1', 'segment:2', 'original:2', 'original:1'])

    async def test_segment_article_revision_provenance_and_immutability(self):
        article = await self.create_article(evidence='segment:1')
        revision = article['current_revision']['id']
        row = await self.admin.fetchrow('SELECT original_input_id, segment_input_id FROM article_evidence WHERE revision_id=$1', revision)
        self.assertEqual(tuple(row), (None, 1))
        provenance = await self.get(f"/articles/{article['id']}/evidence")
        self.assertEqual(provenance[0]['original_input_id'], 3)
        response = await self.client.patch(f"/articles/{article['id']}", json={
            'title': 'Revised', 'expected_revision_id': revision, 'evidence': [{'evidence_id': 'segment:2'}],
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['current_revision']['revision_number'], 2)
        conflict = await self.client.patch(f"/articles/{article['id']}", json={'title': 'Stale', 'expected_revision_id': revision})
        self.assertEqual(conflict.status_code, 409)
        with self.assertRaises(asyncpg.RaiseError):
            await self.admin.execute("UPDATE article_revisions SET title='Mutated' WHERE id=$1", revision)
        with self.assertRaises(asyncpg.ForeignKeyViolationError):
            await self.admin.execute('DELETE FROM segment_inputs WHERE id=1')
        await self.transition(article, 'submit')
        await self.transition(article, 'approve')
        response = await self.client.patch(f"/articles/{article['id']}", json={'title': 'Overwrite approved'})
        self.assertEqual(response.status_code, 409)

    async def test_approval_audit_failure_rolls_back_status_and_coverage(self):
        article = await self.create_article()
        await self.transition(article, 'submit')
        before = await self.get('/dashboard/summary')
        await self.admin.execute("""
            CREATE FUNCTION fail_approval_audit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF NEW.action='approved' THEN RAISE EXCEPTION 'test audit failure'; END IF; RETURN NEW; END $$;
            CREATE TRIGGER fail_audit BEFORE INSERT ON article_audit FOR EACH ROW EXECUTE FUNCTION fail_approval_audit();
        """)
        with self.assertRaises(asyncpg.RaiseError):
            await self.transition(article, 'approve')
        self.assertEqual(await self.get('/dashboard/summary'), before)
        row = await self.get(f"/articles/{article['id']}")
        self.assertEqual(row['status'], 'ready_for_review')
        self.assertIsNone(row['approved_at'])
        self.assertEqual(await self.admin.fetchval("SELECT count(*) FROM article_audit WHERE action='approved'"), 0)
        self.assertEqual(await self.admin.fetchval("SELECT count(*) FROM article_publications WHERE article_id=$1", article["id"]), 0)

    async def test_database_constraints_and_required_indexes(self):
        article = await self.create_article()
        for query, error in [
            ("UPDATE articles SET status='approved'", asyncpg.CheckViolationError),
            ("INSERT INTO article_evidence(revision_id,original_input_id,segment_input_id,evidence_order,topic_key) VALUES (1,1,1,99,'cost')", asyncpg.CheckViolationError),
            ("INSERT INTO article_themes(article_id,stable_theme_id,theme_name_snapshot) VALUES (1,4,'invalid')", asyncpg.ForeignKeyViolationError),
            ("UPDATE article_template_versions SET html_source='changed'", asyncpg.RaiseError),
        ]:
            with self.subTest(query=query), self.assertRaises(error):
                await self.admin.execute(query)
        indexes = set(await self.admin.fetch("SELECT indexname FROM pg_indexes WHERE schemaname=$1", self.schema))
        names = {row['indexname'] for row in indexes}
        self.assertTrue({'idx_articles_status_updated', 'idx_article_themes_stable_theme', 'idx_article_topics_run_topic', 'idx_original_inputs_question_id'} <= names)

    async def test_taxonomy_run_candidate_state_is_isolated_and_protected(self):
        before = await self.get('/dashboard/summary')
        run_id = await self.admin.fetchval("""
            INSERT INTO taxonomy_runs (
                source_cutoff, source_snapshot_sha256, configuration,
                configuration_sha256, embedding_model, embedding_representation,
                clustering_model, topic_model, theme_model,
                topic_prompt_version, theme_prompt_version
            ) VALUES (
                '2026-02-01', repeat('a', 64), '{"min_cluster_size": 3}',
                repeat('b', 64), 'embeddinggemma', 'question-answer',
                'hdbscan-0.8.44', 'qwen3:4b-instruct', 'qwen3:4b-instruct',
                'topic-v1', 'theme-v1'
            ) RETURNING id
        """)
        await self.admin.execute("""
            INSERT INTO input_embeddings (
                original_input_id, embedding, embedding_model, embedding_representation
            ) VALUES (3, '[1,0]', 'embeddinggemma', 'question-answer') ON CONFLICT (original_input_id) WHERE original_input_id IS NOT NULL DO UPDATE SET embedding=EXCLUDED.embedding;
            INSERT INTO input_embeddings (
                segment_input_id, embedding, embedding_model, embedding_representation
            ) VALUES (1, '[1,0]', 'embeddinggemma', 'question-answer') ON CONFLICT (segment_input_id) WHERE segment_input_id IS NOT NULL DO UPDATE SET embedding=EXCLUDED.embedding;
        """)
        original_embedding = await self.admin.fetchval(
            'SELECT id FROM input_embeddings WHERE original_input_id=3'
        )
        segment_embedding = await self.admin.fetchval(
            'SELECT id FROM input_embeddings WHERE segment_input_id=1'
        )
        await self.admin.execute(
            'INSERT INTO taxonomy_run_evidence(taxonomy_run_id,original_input_id,embedding_id) VALUES($1,3,$2)',
            run_id, original_embedding,
        )
        with self.assertRaises(asyncpg.RaiseError):
            await self.admin.execute(
                'INSERT INTO taxonomy_run_evidence(taxonomy_run_id,original_input_id,segment_input_id,embedding_id) VALUES($1,3,1,$2)',
                run_id, segment_embedding,
            )
        with self.assertRaises(asyncpg.RaiseError):
            await self.admin.execute("UPDATE taxonomy_runs SET source_cutoff='2026-03-01' WHERE id=$1", run_id)

        topic_id = await self.admin.fetchval('INSERT INTO topics DEFAULT VALUES RETURNING id')
        revision_id = await self.admin.fetchval("""
            INSERT INTO topic_revisions(
                taxonomy_run_id, topic_id, cluster_key, name, normalized_name,
                literal_description, support_count, centroid, continuity_decision
            ) VALUES($1,$2,'cluster-1','Cost barriers','cost barriers',
                'Respondents mention cost as a barrier.',1,'[1,0]','new') RETURNING id
        """, run_id, topic_id)
        evidence_id = await self.admin.fetchval(
            'SELECT id FROM taxonomy_run_evidence WHERE taxonomy_run_id=$1', run_id
        )
        await self.admin.execute(
            'INSERT INTO topic_memberships(taxonomy_run_id,topic_revision_id,evidence_id) VALUES($1,$2,$3)',
            run_id, revision_id, evidence_id,
        )
        await self.admin.execute(
            "UPDATE taxonomy_runs SET status='running', started_at=CURRENT_TIMESTAMP WHERE id=$1", run_id
        )
        await self.admin.execute(
            "UPDATE taxonomy_runs SET status='failed', error_summary='provider unavailable' WHERE id=$1", run_id
        )
        await self.admin.execute(
            "UPDATE taxonomy_runs SET status='running', error_summary=NULL WHERE id=$1", run_id
        )
        await self.admin.execute(
            "UPDATE taxonomy_runs SET status='ready_for_review', completed_at=CURRENT_TIMESTAMP WHERE id=$1", run_id
        )
        with self.assertRaises(asyncpg.RaiseError):
            await self.admin.execute(
                "UPDATE topic_revisions SET literal_description='changed' WHERE id=$1", revision_id
            )
        with self.assertRaises(asyncpg.RaiseError):
            await self.admin.execute(
                'INSERT INTO taxonomy_run_evidence(taxonomy_run_id,original_input_id,embedding_id) VALUES($1,1,$2)',
                run_id, original_embedding,
            )
        self.assertEqual(await self.get('/dashboard/summary'), before)

    @staticmethod
    def snapshot_payload(**overrides):
        payload = {
            "idempotency_key": "snapshot-key-1",
            "configuration": {
                "version": "batch-snapshot-v1",
                "clustering": {"min_cluster_size": 3, "min_samples": 2},
            },
            "embedding_model": "embeddinggemma",
            "embedding_representation": "question-answer",
            "embedding_dimension": 2,
            "clustering_model": "hdbscan-0.8.44",
            "topic_model": "qwen3:4b-instruct",
            "theme_model": "qwen3:4b-instruct",
            "topic_prompt_version": "taxonomy-topic-v1",
            "theme_prompt_version": "taxonomy-theme-v1",
        }
        payload.update(overrides)
        return payload

    async def seed_snapshot_embeddings(self, *, model="embeddinggemma", representation="question-answer"):
        await self.admin.executemany("""
            INSERT INTO input_embeddings (
                original_input_id, embedding, embedding_model, embedding_representation
            ) VALUES ($1, $2::vector, $3, $4)
            ON CONFLICT (original_input_id) WHERE original_input_id IS NOT NULL
            DO UPDATE SET embedding = EXCLUDED.embedding,
                          embedding_model = EXCLUDED.embedding_model,
                          embedding_representation = EXCLUDED.embedding_representation
        """, [
            (1, "[1,0]", model, representation),
            (2, "[0,1]", model, representation),
        ])
        await self.admin.executemany("""
            INSERT INTO input_embeddings (
                segment_input_id, embedding, embedding_model, embedding_representation
            ) VALUES ($1, $2::vector, $3, $4)
            ON CONFLICT (segment_input_id) WHERE segment_input_id IS NOT NULL
            DO UPDATE SET embedding = EXCLUDED.embedding,
                          embedding_model = EXCLUDED.embedding_model,
                          embedding_representation = EXCLUDED.embedding_representation
        """, [
            (1, "[1,0]", model, representation),
            (2, "[0.5,0.5]", model, representation),
            (3, "[0,1]", model, representation),
        ])

    async def test_snapshot_api_freezes_canonical_evidence_and_is_idempotent(self):
        await self.seed_snapshot_embeddings()
        payload = self.snapshot_payload()
        created = await self.client.post("/taxonomy-runs", json=payload)
        self.assertEqual(created.status_code, 201, created.text)
        body = created.json()
        self.assertFalse(body["reused"])
        self.assertTrue(body["queued"])
        self.assertEqual((body["evidence_count"], body["embedding_dimension"]), (5, 2))
        run_id = body["id"]
        evidence = await self.admin.fetch(
            "SELECT original_input_id, segment_input_id FROM taxonomy_run_evidence WHERE taxonomy_run_id=$1 ORDER BY original_input_id, segment_input_id NULLS FIRST",
            run_id,
        )
        self.assertEqual(
            [tuple(row) for row in evidence],
            [(1, None), (2, None), (3, 1), (3, 2), (3, 3)],
        )
        stages = await self.admin.fetch(
            "SELECT stage, attempt, status, stage_input_sha256, stage_output_sha256 "
            "FROM taxonomy_run_stages WHERE taxonomy_run_id=$1 ORDER BY id", run_id
        )
        self.assertEqual(
            [(row["stage"], row["attempt"], row["status"]) for row in stages],
            [
                ("snapshot", 1, "completed"), ("clustering", 0, "pending"),
                ("topic_naming", 0, "pending"), ("theme_inference", 0, "pending"),
                ("theme_reconciliation", 0, "pending"), ("quality", 0, "pending"),
                ("ready_for_publication", 0, "pending"),
            ],
        )
        self.assertTrue(all(len(row["stage_input_sha256"]) == 64 for row in stages))
        self.assertEqual(stages[0]["stage_output_sha256"], await self.admin.fetchval(
            "SELECT source_snapshot_sha256 FROM taxonomy_runs WHERE id=$1", run_id
        ))
        await self.admin.execute("""
            INSERT INTO original_inputs (original_text, source, status)
            VALUES ('Late answer', 'test', 'completed');
            INSERT INTO input_embeddings (
                original_input_id, embedding, embedding_model, embedding_representation
            ) VALUES (5, '[1,0]', 'embeddinggemma', 'question-answer');
        """)
        repeated = await self.client.post("/taxonomy-runs", json=payload)
        self.assertEqual(repeated.status_code, 201, repeated.text)
        self.assertTrue(repeated.json()["reused"])
        self.assertEqual(repeated.json()["id"], run_id)
        self.assertEqual(
            await self.admin.fetchval("SELECT count(*) FROM taxonomy_run_evidence WHERE taxonomy_run_id=$1", run_id),
            5,
        )
        changed = await self.client.post(
            "/taxonomy-runs", json=self.snapshot_payload(configuration={
                "version": "batch-snapshot-v2", "clustering": {"min_cluster_size": 3}
            })
        )
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertEqual(changed.json()["detail"]["code"], "taxonomy_idempotency_conflict")

    async def test_snapshot_validation_is_bounded_and_rolls_back(self):
        await self.seed_snapshot_embeddings(model="different-model")
        response = await self.client.post("/taxonomy-runs", json=self.snapshot_payload())
        self.assertEqual(response.status_code, 409, response.text)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "invalid_taxonomy_snapshot")
        self.assertEqual(detail["counts"]["model_mismatch"], 5)
        self.assertNotIn("Repeated answer", response.text)
        self.assertEqual(await self.admin.fetchval("SELECT count(*) FROM taxonomy_runs"), 1)
        self.assertEqual(await self.admin.fetchval("SELECT count(*) FROM taxonomy_run_evidence"), 5)
        self.assertEqual(await self.admin.fetchval("SELECT count(*) FROM taxonomy_run_jobs"), 0)

        await self.seed_snapshot_embeddings()
        await self.admin.execute("""
            CREATE FUNCTION fail_snapshot_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'snapshot evidence insert failed'; END;
            $$;
            CREATE TRIGGER fail_snapshot_evidence
            BEFORE INSERT ON taxonomy_run_evidence
            FOR EACH ROW EXECUTE FUNCTION fail_snapshot_evidence();
        """)
        request = SnapshotRequest(**self.snapshot_payload(idempotency_key="snapshot-rollback"))
        with self.assertRaises(asyncpg.RaiseError):
            await create_taxonomy_snapshot(self.pool, request)
        self.assertEqual(await self.admin.fetchval("SELECT count(*) FROM taxonomy_runs"), 1)
        self.assertEqual(await self.admin.fetchval("SELECT count(*) FROM taxonomy_run_evidence"), 5)
        self.assertEqual(await self.admin.fetchval("SELECT count(*) FROM taxonomy_run_jobs"), 0)

    async def test_stage_lease_is_exclusive_reclaimable_and_owner_bound(self):
        await self.seed_snapshot_embeddings()
        created = await self.client.post("/taxonomy-runs", json=self.snapshot_payload())
        self.assertEqual(created.status_code, 201, created.text)
        run_id = created.json()["id"]

        first = await claim_next_stage(
            self.pool, lease_owner="worker-one", lease_seconds=60,
        )
        self.assertIsNotNone(first)
        self.assertEqual((first.run_id, first.stage, first.attempt), (run_id, "clustering", 1))
        self.assertIsNone(await claim_next_stage(
            self.pool, lease_owner="worker-two", lease_seconds=60,
        ))

        await self.admin.execute(
            "UPDATE taxonomy_run_stages SET lease_expires_at=CURRENT_TIMESTAMP - INTERVAL '1 second' WHERE id=$1",
            first.id,
        )
        reclaimed = await claim_next_stage(
            self.pool, lease_owner="worker-two", lease_seconds=60,
        )
        self.assertIsNotNone(reclaimed)
        self.assertEqual((reclaimed.id, reclaimed.attempt, reclaimed.lease_owner), (first.id, 2, "worker-two"))
        self.assertFalse(await complete_stage(self.pool, first, output_material="old worker output"))
        self.assertTrue(await complete_stage(self.pool, reclaimed, output_material="reclaimed output"))
        self.assertEqual(await self.admin.fetchval(
            "SELECT status FROM taxonomy_run_stages WHERE id=$1", first.id,
        ), "completed")
