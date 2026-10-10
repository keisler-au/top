"""PTR-7: actual gated replacement/rollback must not alter approved HTTP pages.

Runs after test_public_site_e2e in the isolated full suite. Fixtures persist
only in Compose's disposable public schema, so this file must never target an
application database. API/edge requests reach the rebuilt containers.
"""
import os
import unittest

import asyncpg
import httpx

from integration.taxonomy_replacement_fixture import ReplacementFixture

DSN = os.environ.get('TRIAGE_TEST_DATABASE_URL')
EDGE = os.environ.get('PUBLIC_EDGE_BASE_URL')
API = os.environ.get('PUBLIC_API_BASE_URL')


@unittest.skipUnless(DSN and EDGE and API,'Use disposable compose.test.yaml with rebuilt API/public edge')
class PublicTaxonomyReplacementTests(ReplacementFixture,unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await asyncpg.connect(DSN)
        self.addAsyncCleanup(self.db.close)
        self.pool = await asyncpg.create_pool(DSN,min_size=1,max_size=3)
        self.addAsyncCleanup(self.pool.close)
        self.client = httpx.AsyncClient(base_url=API)
        self.addAsyncCleanup(self.client.aclose)
        self.edge = httpx.AsyncClient(base_url=EDGE)
        self.addAsyncCleanup(self.edge.aclose)
        await self.create_sources()

    async def publish(self,run):
        updated = await self.db.fetchval('SELECT updated_at FROM taxonomy_runs WHERE id=$1',run)
        self.assertEqual(await self.db.fetchval("SELECT (publish_taxonomy_run($1,$2,'ptr7')).id",run,updated),run)

    async def article_snapshots(self,article):
        result = {}
        for table,condition in (
            ('articles','id=$1'),('article_revisions','article_id=$1'),('article_topics','article_id=$1'),
            ('article_themes','article_id=$1'),('article_publications','article_id=$1'),
            ('article_publication_themes','article_id=$1'),('article_audit','article_id=$1'),
            ('article_evidence','revision_id IN (SELECT id FROM article_revisions WHERE article_id=$1)'),
        ):
            result[table] = await self.db.fetchval(f"SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),'[]')::text FROM {table} t WHERE {condition}",article)
        return result

    async def test_02_real_replacement_and_rollback_preserve_approved_topic_and_theme_displays(self):
        first = await self.build_run()
        await self.publish(first)
        before_inputs = await self.assert_matrix(first,'first')
        first_history = await self.frozen_history(first)
        theme_ids = [row['theme_id'] for row in await self.db.fetch('SELECT theme_id FROM theme_revisions WHERE taxonomy_run_id=$1 ORDER BY theme_id',first)]
        response = await self.client.post('/articles',json={
            'title':'PTR7 historical display '+self.form[-8:],
            'structured_content':{'standfirst':'Historical insight','sections':[]},
            'rendered_html':'<p>Approved historical topic: Zulu old.</p>',
            'generation_metadata':{'private_ptr7_metadata':'do-not-expose'},
            'theme_ids':theme_ids,'topics':[{'name':'Zulu old'}],
            'evidence':[{'evidence_id':f"original:{self.inputs['removed']}"}],
        })
        self.assertEqual(response.status_code,201,response.text)
        article = response.json()['id']
        for action in ('submit','approve'):
            response = await self.client.post(f'/articles/{article}/{action}',json={})
            self.assertEqual(response.status_code,200,response.text)
        approved = response.json()
        self.assertEqual(approved['topics'],[{'name':'Zulu old'}])
        slug = await self.db.fetchval('SELECT slug FROM article_publications WHERE article_id=$1',article)
        path = f'/insights/{slug}'
        page = await self.edge.get(path)
        self.assertEqual(page.status_code,200,page.text)
        original_html = page.text
        original_themes = (await self.edge.get('/themes')).text
        self.assertIn('Zulu historical',original_html)
        self.assertIn('Alpha historical',original_html)
        self.assertIn('Approved historical topic: Zulu old.',original_html)
        self.assertNotIn('do-not-expose',original_html)
        self.assertNotIn('Private PTR7 answer',original_html)
        article_history = await self.article_snapshots(article)
        source = await self.source_rows()
        second = await self.build_run('second')
        self.assertEqual(await self.read_inputs(),before_inputs)
        await self.publish(second)
        await self.assert_matrix(second,'second')
        await self.publish(second)
        for candidate in (first,second):
            for forbidden in (f'/taxonomy-runs/{candidate}',f'/taxonomy-runs/{candidate}/topics/1/evidence',
                              f'/api/taxonomy-runs/{candidate}',f'/api/articles/{article}'):
                self.assertEqual((await self.edge.get(forbidden)).status_code,404)
        self.assertEqual(await self.frozen_history(first),first_history)
        self.assertEqual(await self.article_snapshots(article),article_history)
        self.assertEqual((await self.client.get(f'/articles/{article}')).json(),approved)
        self.assertEqual((await self.edge.get(path)).text,original_html)
        self.assertEqual((await self.edge.get('/themes')).text,original_themes)
        self.assertNotIn('Yankee new',(await self.edge.get(path)).text)
        # Restore the first run twice. Association readers switch together;
        # approved display/storage and both runs' frozen results do not change.
        second_history = await self.frozen_history(second)
        for _ in range(2):
            await self.db.execute("SELECT rollback_taxonomy_run($1,'ptr7','Historical HTTP display check')",first)
            self.assertEqual(await self.read_inputs(),before_inputs)
            self.assertEqual((await self.edge.get(path)).text,original_html)
        self.assertEqual(await self.frozen_history(first),first_history)
        self.assertEqual(await self.frozen_history(second),second_history)
        self.assertEqual(await self.article_snapshots(article),article_history)
        self.assertEqual(await self.source_rows(),source)
        self.assertEqual(await self.db.fetchval("SELECT count(*) FROM taxonomy_runs WHERE status='published'"),1)
