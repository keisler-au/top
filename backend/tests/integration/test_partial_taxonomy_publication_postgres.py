"""PTR-5 publication, readers and generation against disposable pgvector."""
from contextlib import asynccontextmanager
import asyncio
import json
import os
import unittest
from unittest.mock import AsyncMock, patch

import asyncpg
from fastapi import FastAPI
import httpx

if __package__:
    from . import test_partial_taxonomy_quality_postgres as fixture
else:
    import test_partial_taxonomy_quality_postgres as fixture
from triage_processor.api.routes import dashboard, generation, inputs, operations, taxonomy_review
from triage_processor.taxonomy_stage_quality import compute_run_quality
from triage_processor.taxonomy_status import current_candidate_status
from triage_processor.taxonomy_themes import infer_run
from triage_processor.taxonomy_reconciliation import reconcile_run
from triage_processor.workers.article_generation import claim_job, process_job


@unittest.skipUnless(fixture.fixture.DSN, 'Use disposable compose.test.yaml')
class PartialTaxonomyPublicationPostgresTests(unittest.IsolatedAsyncioTestCase):
    new_run = fixture.PartialTaxonomyQualityPostgresTests.new_run
    provisional = fixture.PartialTaxonomyQualityPostgresTests.provisional
    merged = fixture.PartialTaxonomyQualityPostgresTests.merged
    reconcile = fixture.PartialTaxonomyQualityPostgresTests.reconcile
    prepare = fixture.PartialTaxonomyQualityPostgresTests.prepare
    complete_predecessors = fixture.PartialTaxonomyQualityPostgresTests.complete_predecessors

    async def asyncSetUp(self):
        await fixture.PartialTaxonomyQualityPostgresTests.asyncSetUp(self)
        app = FastAPI()
        for router in (dashboard.router, generation.router, inputs.router, operations.router, taxonomy_review.router):
            app.include_router(router)
        app.state.db_pool = self.pool
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://fixture',
                                       headers={'Authorization': 'Bearer ptr5'})
        self.addAsyncCleanup(self.client.aclose)
        env = patch.dict(os.environ, {'TAXONOMY_MUTATION_TOKEN': 'ptr5', 'TAXONOMY_REVIEW_TOKEN': 'ptr5'})
        env.start()
        self.addCleanup(env.stop)

    async def ready(self, *, noise=2, merge=True, theme=False):
        await self.prepare(noise=noise,merge=merge)
        if theme:
            ids = [row['id'] for row in await self.db.fetch('SELECT id FROM topic_revisions WHERE taxonomy_run_id=$1 ORDER BY id',self.run)]
            response = {'create_theme':True,'name':'Participation barriers','description':'Fees and charges.',
                        'rationale':'Related distinct costs.','topic_revision_ids':ids}
            with patch('triage_processor.clients.llm.StructuredChatClient.complete',new=AsyncMock(return_value=response)):
                await infer_run(self.pool,self.run,'http://fixture','fixture')
            await reconcile_run(self.pool,self.run)
        await compute_run_quality(self.pool, self.run)
        await self.db.execute("UPDATE taxonomy_runs SET status='running',started_at=CURRENT_TIMESTAMP WHERE id=$1",self.run)
        await self.db.execute("UPDATE taxonomy_runs SET status='ready_for_review',completed_at=CURRENT_TIMESTAMP WHERE id=$1",self.run)
        return await self.db.fetchval('SELECT updated_at FROM taxonomy_runs WHERE id=$1',self.run)

    async def publish(self):
        expected = await self.db.fetchval('SELECT updated_at FROM taxonomy_runs WHERE id=$1',self.run)
        return await self.db.fetchval("SELECT (publish_taxonomy_run($1,$2,'ptr5')).id",self.run,expected)

    async def successor(self):
        self.run = await self.new_run()
        self.ids = []
        self.evidence = []
        for index, (question, sources) in enumerate(self.sources):
            identifier, evidence = await self.provisional(self.run,index,question,('Access fees','Service charges')[index],sources)
            self.ids.append(identifier)
            self.evidence.extend(evidence)

    async def get(self,path):
        response = await self.client.get(path)
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    async def test_partial_zero_theme_publication_readers_and_replay(self):
        await self.ready()
        self.assertEqual(await self.publish(),self.run)
        self.assertEqual(await self.publish(),self.run)
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM taxonomy_publication_decisions'),1)
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM topic_aliases'),1)
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM theme_revisions'),0)
        summary = await self.get('/dashboard/summary')
        self.assertEqual((summary['evidence_count'],summary['evidence_with_topic_count'],summary['evidence_without_topic_count']),(6,4,2))
        self.assertEqual(summary['topic_coverage'],'partial')
        self.assertEqual(summary['published_taxonomy_run_id'],self.run)
        rows = await self.get('/inputs')
        self.assertTrue(all('taxonomy_state' not in item and item['status']=='ineligible' for item in rows))
        self.assertTrue(all(item['published_taxonomy_run_id']==self.run and item['themes']==[] for item in rows))
        self.assertEqual(sum(bool(item['topics']) for item in rows),4)
        ops = (await self.get('/operations/summary'))['taxonomy_runs']
        self.assertEqual((ops['topic_coverage'],ops['evidence_with_topic_count'],ops['evidence_without_topic_count']),('partial',4,2))
        self.assertEqual(ops['automation_state'],'automatically_published')
        self.assertEqual(await current_candidate_status(self.db),'published')
        schema = self.client._transport.app.openapi()['components']['schemas']['InputResponse']['properties']
        self.assertNotIn('taxonomy_state',schema)
        self.assertIn('status',schema)
        self.assertIn('published_taxonomy_run_id',schema)

    async def test_replacement_and_rollback_restore_associations_without_changing_sources(self):
        await self.ready()
        await self.publish()
        first = self.run
        source_before = await self.db.fetch('SELECT row_to_json(i)::text FROM original_inputs i ORDER BY id')
        before = await self.get('/inputs')
        await self.successor()
        self.assertEqual(await current_candidate_status(self.db),'running_candidate')
        await self.ready(noise=0)
        await self.publish()
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM taxonomy_runs WHERE status=\'published\''),1)
        self.assertEqual(await self.db.fetchval('SELECT status FROM taxonomy_runs WHERE id=$1',first),'superseded')
        self.assertTrue(all(item['published_taxonomy_run_id']==self.run for item in await self.get('/inputs')))
        self.assertEqual(await self.db.fetch('SELECT row_to_json(i)::text FROM original_inputs i ORDER BY id'),source_before)
        await self.db.execute("SELECT rollback_taxonomy_run($1,'ptr5','restore prior')",first)
        await self.db.execute("SELECT rollback_taxonomy_run($1,'ptr5','replay')",first)
        self.assertEqual(await self.get('/inputs'),before)
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM taxonomy_rollback_decisions'),1)
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM taxonomy_publication_decisions'),2)
        with self.assertRaisesRegex(asyncpg.PostgresError,'immutable'):
            await self.db.execute('DELETE FROM taxonomy_publication_decisions WHERE taxonomy_run_id=$1',first)

    async def test_automatic_requires_matching_decision_then_replays_once(self):
        await self.ready()
        with self.assertRaisesRegex(asyncpg.PostgresError,'matching automatic decision'):
            await self.db.execute("SELECT publish_taxonomy_run_automatically($1,'ptr5-policy')",self.run)
        await self.db.execute("""INSERT INTO taxonomy_automation_decisions(idempotency_key,policy_version,evidence_cutoff,status,taxonomy_run_id)
            VALUES('automatic:ptr5-policy:fixture','ptr5-policy',CURRENT_TIMESTAMP,'snapshotted',$1)""",self.run)
        with self.assertRaisesRegex(asyncpg.PostgresError,'matching automatic decision'):
            await self.db.execute("SELECT publish_taxonomy_run_automatically($1,'wrong')",self.run)
        for _ in range(2):
            await self.db.execute("SELECT publish_taxonomy_run_automatically($1,'ptr5-policy')",self.run)
        decision = await self.db.fetchrow('SELECT decision_kind,automation_policy_version FROM taxonomy_publication_decisions')
        self.assertEqual(tuple(decision),('automatic','ptr5-policy'))

    async def test_failed_integrity_and_old_gate_keep_prior_publication(self):
        await self.ready()
        await self.publish()
        prior = self.run
        await self.successor()
        await self.db.execute("UPDATE taxonomy_runs SET status='running',started_at=CURRENT_TIMESTAMP WHERE id=$1",self.run)
        # Unfinished processing is a computed failure, never a useful partial result.
        await compute_run_quality(self.pool,self.run)
        self.assertEqual(await current_candidate_status(self.db),'quality_blocked')
        with self.assertRaisesRegex(asyncpg.PostgresError,'current-version'):
            await self.publish()
        self.assertEqual(await self.db.fetchval("SELECT id FROM taxonomy_runs WHERE status='published'"),prior)
        await self.successor()
        await self.db.execute("""INSERT INTO taxonomy_release_attestations(taxonomy_run_id,metrics,thresholds,threshold_version,gate_passed,input_sha256)
            VALUES($1,'{}','{}','taxonomy-release-gate-v2',TRUE,repeat('f',64))""",self.run)
        with self.assertRaisesRegex(asyncpg.PostgresError,'current-version'):
            await self.publish()
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM taxonomy_publication_decisions'),1)

    async def test_changed_facts_stale_review_and_missing_operator_are_rejected(self):
        expected = await self.ready()
        with self.assertRaisesRegex(asyncpg.PostgresError,'operator name'):
            await self.db.execute('SELECT publish_taxonomy_run($1,$2,NULL)',self.run,expected)
        with self.assertRaisesRegex(asyncpg.PostgresError,'no longer ready'):
            await self.db.execute("SELECT publish_taxonomy_run($1,$2::timestamptz-INTERVAL '1 second','ptr5')",self.run,expected)
        # Deliberate corruption of the immutable gate simulates an incompatible deployment.
        await self.db.execute('ALTER TABLE taxonomy_release_attestations DISABLE TRIGGER USER')
        await self.db.execute("UPDATE taxonomy_release_attestations SET metrics=metrics||'{\"evidence_count\":7}' WHERE taxonomy_run_id=$1",self.run)
        await self.db.execute('ALTER TABLE taxonomy_release_attestations ENABLE TRIGGER USER')
        with self.assertRaisesRegex(asyncpg.PostgresError,'facts changed'):
            await self.publish()
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM topic_aliases'),0)

    async def test_audit_failure_rolls_back_swap_and_all_projection_writes(self):
        await self.ready()
        await self.publish()
        prior = self.run
        await self.successor()
        await self.ready()
        await self.db.execute("""CREATE FUNCTION ptr5_fail_audit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'ptr5 audit failure'; END; $$;
            CREATE TRIGGER ptr5_fail BEFORE INSERT ON taxonomy_publication_decisions FOR EACH ROW EXECUTE FUNCTION ptr5_fail_audit();""")
        before = await self.get('/dashboard/summary')
        with self.assertRaisesRegex(asyncpg.PostgresError,'ptr5 audit failure'):
            await self.publish()
        self.assertEqual(await self.get('/dashboard/summary'),before)
        self.assertEqual(await self.db.fetchval("SELECT id FROM taxonomy_runs WHERE status='published'"),prior)
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM topic_aliases WHERE created_in_run_id=$1',self.run),0)

    async def test_concurrent_same_candidate_is_one_atomic_decision(self):
        expected = await self.ready()
        async def publish():
            async with self.pool.acquire() as db:
                return await db.fetchval("SELECT (publish_taxonomy_run($1,$2,'ptr5')).id",self.run,expected)
        self.assertEqual(await asyncio.gather(publish(),publish()),[self.run,self.run])
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM taxonomy_publication_decisions'),1)
        self.assertEqual(await self.db.fetchval("SELECT count(*) FROM taxonomy_runs WHERE status='published'"),1)

    async def test_competing_automatic_swap_rejects_changed_publication_and_can_retry(self):
        expected = await self.ready()
        first = self.run
        await self.successor()
        await self.ready()
        second = self.run
        await self.db.execute("""INSERT INTO taxonomy_automation_decisions(idempotency_key,policy_version,evidence_cutoff,status,taxonomy_run_id)
            VALUES('automatic:ptr5-policy:competitor','ptr5-policy',CURRENT_TIMESTAMP,'snapshotted',$1)""",second)
        async with self.pool.acquire() as other:
            pid = await other.fetchval('SELECT pg_backend_pid()')
            async with self.db.transaction():
                await self.db.execute("SELECT pg_advisory_xact_lock(hashtext('taxonomy-publication'))")
                task = asyncio.create_task(other.execute("SELECT publish_taxonomy_run_automatically($1,'ptr5-policy')",second))
                try:
                    for _ in range(200):
                        waiting = await self.db.fetchval("SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=$1 AND locktype='advisory' AND NOT granted)",pid)
                        if waiting:
                            break
                        await asyncio.sleep(0.01)
                    self.assertTrue(waiting,'competitor did not reach the publication lock')
                    await self.db.execute("SELECT publish_taxonomy_run($1,$2,'ptr5')",first,expected)
                except BaseException:
                    task.cancel()
                    await asyncio.gather(task,return_exceptions=True)
                    raise
            with self.assertRaisesRegex(asyncpg.PostgresError,'concurrent taxonomy publication'):
                await task
        self.assertEqual(await self.db.fetchval("SELECT id FROM taxonomy_runs WHERE status='published'"),first)
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM topic_aliases WHERE created_in_run_id=$1',second),0)
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM taxonomy_publication_decisions'),1)
        await self.db.execute("SELECT publish_taxonomy_run_automatically($1,'ptr5-policy')",second)
        self.assertEqual(await self.db.fetchval("SELECT id FROM taxonomy_runs WHERE status='published'"),second)

    async def test_zero_theme_replacement_records_retirement_and_rollback_restores_theme(self):
        await self.ready(merge=False,theme=True)
        await self.publish()
        prior = self.run
        before = await self.get('/inputs')
        theme = await self.db.fetchval('SELECT theme_id FROM theme_revisions WHERE taxonomy_run_id=$1',prior)
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM theme_aliases'),1)
        await self.successor()
        await self.ready()
        await self.publish()
        lineage = await self.db.fetchrow('SELECT predecessor_theme_id,successor_theme_id,relationship FROM theme_lineage WHERE taxonomy_run_id=$1',self.run)
        self.assertEqual(tuple(lineage),(theme,None,'retired'))
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM theme_revisions WHERE taxonomy_run_id=$1',self.run),0)
        self.assertTrue(all(item['themes']==[] for item in await self.get('/inputs')))
        await self.db.execute("SELECT rollback_taxonomy_run($1,'ptr5','restore theme')",prior)
        rows = await self.get('/inputs')
        self.assertEqual(rows[:len(before)],before)
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM theme_revisions WHERE taxonomy_run_id=$1',prior),1)

    async def test_topic_generation_without_themes_freezes_scope_and_rejects_foreign_evidence(self):
        await self.ready()
        await self.publish()
        topic = str(await self.db.fetchval('SELECT topic_id FROM topic_revisions WHERE taxonomy_run_id=$1',self.run))
        template = await self.client.post('/article-templates',json={'name':'PTR5','html_source':'<article>{{title}}{{article_body}}</article>'})
        self.assertEqual(template.status_code,201,template.text)
        version = template.json()['versions'][0]['id']
        source = self.sources[0][1][0][0]
        foreign = await self.db.fetchval('SELECT max(original_input_id) FROM taxonomy_run_evidence WHERE taxonomy_run_id=$1',self.run)
        payload = {'strategy':'specific','taxonomy_type':'topic','taxonomy_key':topic,'template_version_id':version,'evidence_ids':[f'original:{foreign}']}
        rejected = await self.client.post('/article-generation-jobs',json=payload)
        self.assertEqual(rejected.status_code,422,rejected.text)
        payload['evidence_ids'] = [f'original:{source}']
        first = self.run
        await self.successor()
        await self.ready(noise=0,merge=False)
        owner = self
        class DuringReadConnection:
            def __init__(self, db):
                self.db = db
            def __getattr__(self, name):
                return getattr(self.db, name)
            async def fetchrow(self, query, *args):
                row = await self.db.fetchrow(query,*args)
                if 'dashboard:taxonomy-detail' in query:
                    await owner.publish()
                return row
        class DuringReadPool:
            @asynccontextmanager
            async def acquire(self):
                async with owner.pool.acquire() as db:
                    yield DuringReadConnection(db)
        # Swap after target lookup but before evidence lookup/job insertion.
        app = self.client._transport.app
        app.state.db_pool = DuringReadPool()
        try:
            created = await self.client.post('/article-generation-jobs',json=payload)
        finally:
            app.state.db_pool = self.pool
        self.assertEqual(created.status_code,202,created.text)
        job = await claim_job(self.pool,locked_by='ptr5',lease_seconds=60)
        model = AsyncMock()
        model.complete.return_value = {'title':'Access','standfirst':'Cost','sections':[{'heading':'Cost','paragraphs':['Fees prevent participation.'],'evidence_ids':[f'original:{source}']}],'theme_ids':[],'topic_keys':[topic]}
        article = await process_job(self.pool,model,job,model='fixture')
        self.assertGreater(article,0)
        self.assertEqual(await self.db.fetchval('SELECT taxonomy_run_id FROM article_generation_jobs WHERE id=$1',job.id),first)
        self.assertEqual(await self.db.fetchval('SELECT taxonomy_run_id FROM article_topics WHERE article_id=$1',article),first)
        self.assertEqual(await self.db.fetchval(
            'SELECT e.taxonomy_run_id FROM article_evidence e JOIN article_revisions r ON r.id=e.revision_id WHERE r.article_id=$1', article), first)
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM article_themes WHERE article_id=$1',article),0)
