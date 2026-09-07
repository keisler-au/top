import os
from pathlib import Path
import unittest
from uuid import uuid4

import asyncpg
from fastapi import FastAPI
import httpx

from triage_processor.api.routes import articles, dashboard, generation, form_sources, operations
from triage_processor.articles import canonical_theme_ids
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
        self.schema = "test_" + uuid4().hex
        self.admin = await asyncpg.connect(DSN)
        self.addAsyncCleanup(self.admin.close)
        await self.admin.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
        await self.admin.execute(f'CREATE SCHEMA "{self.schema}"')
        self.addAsyncCleanup(self.admin.execute, f'DROP SCHEMA "{self.schema}" CASCADE')
        await self.admin.execute(f'SET search_path TO "{self.schema}", public')
        await self.admin.execute(snapshot_sql(ROOT / "init.sql"))
        self.pool = await asyncpg.create_pool(
            DSN, min_size=1, max_size=4,
            server_settings={"search_path": f'"{self.schema}", public', "statement_timeout": "5000"},
        )
        self.addAsyncCleanup(self.pool.close)
        app = FastAPI()
        for router in (articles.router, dashboard.router, generation.router, form_sources.router, operations.router):
            app.include_router(router)
        app.state.db_pool = self.pool
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        self.addAsyncCleanup(self.client.aclose)
        await self.seed()

    async def seed(self):
        # Repeated text remains distinct evidence. Split originals never count twice.
        await self.admin.execute("""
            INSERT INTO original_inputs (original_text, source, status, topic, created_at) VALUES
            ('Repeated answer', 'test', 'completed', ' Cost ', '2026-01-01'),
            ('Repeated answer', 'test', 'completed', 'COST', '2026-01-01'),
            ('Split answer', 'test', 'completed', 'ignored original', '2026-01-01'),
            ('Not yet complete', 'test', 'new', NULL, '2026-01-01');
            INSERT INTO segment_inputs (original_input_id, segment_order, segment_text, topic) VALUES
            (3, 0, 'First cost point', 'cost'), (3, 1, 'Second cost point', 'Cost'),
            (3, 2, 'Delivery point', 'Delivery'), (4, 0, 'Pending parent', 'Cost');
            INSERT INTO themes (name) VALUES ('Alpha'), ('Beta'), ('Empty'),
                ('Alias A'), ('Alias B'), ('Cycle A'), ('Cycle B');
            UPDATE themes SET merged_into_id = 5 WHERE id = 4;
            UPDATE themes SET merged_into_id = 1 WHERE id = 5;
            UPDATE themes SET merged_into_id = 7 WHERE id = 6;
            UPDATE themes SET merged_into_id = 6 WHERE id = 7;
            INSERT INTO theme_topics (theme_id, topic) VALUES
                (1, 'Cost'), (2, 'cost'), (2, 'Delivery'), (4, 'COST'),
                (5, 'cost'), (6, 'Delivery');
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
        self.assertEqual([(row['key'], row['evidence_count']) for row in topics['items']], [('cost', 4), ('delivery', 1)])
        themes = await self.get('/taxonomy?type=theme')
        self.assertEqual([(row['name'], row['evidence_count']) for row in themes['items']], [('Beta', 5), ('Alpha', 4), ('Empty', 0)])
        evidence = await self.get('/taxonomy/theme/1/evidence')
        self.assertEqual([row['id'] for row in evidence['items']], ['segment:1', 'segment:2', 'original:2', 'original:1'])
        self.assertEqual(evidence['total'], 4)
        self.assertEqual(await canonical_theme_ids(self.admin, [4, 5, 1]), [1])
        with self.assertRaisesRegex(ValueError, 'invalid theme'):
            await canonical_theme_ids(self.admin, [6])
        self.assertEqual((await self.client.get('/taxonomy/theme/6')).status_code, 404)

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

    async def test_article_lifecycle_changes_coverage_and_recommendations(self):
        approved = await self.create_article(themes=[4, 2])
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
        for kind, key in [('theme', '1'), ('theme', '2'), ('topic', 'cost'), ('topic', 'delivery')]:
            item = await self.get(f'/taxonomy/{kind}/{key}')
            self.assertEqual((item['article_count'], item['approved_article_count']), (3, 1))
        # Existing multi-tags continue to count once after live themes merge.
        await self.admin.execute('UPDATE themes SET merged_into_id = 1 WHERE id = 2')
        item = await self.get('/taxonomy/theme/1')
        self.assertEqual((item['evidence_count'], item['article_count'], item['approved_article_count']), (5, 3, 1))
        await self.transition(approved, 'archive')
        item = await self.get('/taxonomy/theme/1')
        self.assertEqual((item['article_count'], item['approved_article_count'], item['coverage_state']), (2, 0, 'uncovered'))
        await self.transition(draft, 'approve', 409)

    async def test_stable_pagination_and_recommendation_ties(self):
        await self.admin.execute("INSERT INTO themes(name) VALUES ('Gamma'); INSERT INTO theme_topics(theme_id,topic) VALUES (8,'Cost')")
        for strategy in ['least-covered', 'most-evidence']:
            rows = (await self.get(f'/recommendations/articles?type=theme&strategy={strategy}'))['items']
            self.assertEqual([row['name'] for row in rows], ['Beta', 'Alpha', 'Gamma'])
        article = await self.create_article(themes=[2])
        await self.transition(article, 'submit')
        await self.transition(article, 'approve')
        rows = (await self.get('/recommendations/articles?type=theme&strategy=least-covered'))['items']
        self.assertEqual([row['name'] for row in rows], ['Alpha', 'Gamma', 'Beta'])
        pages = [await self.get(f'/taxonomy?type=theme&sort=evidence&direction=desc&page_size=1&page={page}') for page in range(1, 5)]
        self.assertEqual([page['items'][0]['name'] for page in pages], ['Beta', 'Alpha', 'Gamma', 'Empty'])
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

    async def test_database_constraints_and_required_indexes(self):
        article = await self.create_article()
        for query, error in [
            ("UPDATE articles SET status='approved'", asyncpg.CheckViolationError),
            ("INSERT INTO article_evidence(revision_id,original_input_id,segment_input_id,evidence_order,topic_key) VALUES (1,1,1,99,'cost')", asyncpg.CheckViolationError),
            ("INSERT INTO article_themes(article_id,theme_id) VALUES (1,4)", asyncpg.RaiseError),
            ("UPDATE article_template_versions SET html_source='changed'", asyncpg.RaiseError),
        ]:
            with self.subTest(query=query), self.assertRaises(error):
                await self.admin.execute(query)
        indexes = set(await self.admin.fetch("SELECT indexname FROM pg_indexes WHERE schemaname=$1", self.schema))
        names = {row['indexname'] for row in indexes}
        self.assertTrue({'idx_articles_status_updated', 'idx_article_themes_theme', 'idx_article_topics_topic', 'idx_original_inputs_question_id'} <= names)
