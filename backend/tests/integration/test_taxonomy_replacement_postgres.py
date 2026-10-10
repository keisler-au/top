"""PTR-7 replacement/history proof at the PostgreSQL and inputs HTTP boundaries."""
import asyncio
import os
import unittest
from unittest.mock import patch

import asyncpg

if __package__:
    from . import test_partial_taxonomy_publication_postgres as predecessor
    from .taxonomy_replacement_fixture import ReplacementFixture
else:
    import test_partial_taxonomy_publication_postgres as predecessor
    from taxonomy_replacement_fixture import ReplacementFixture

from triage_processor.taxonomy_stage_quality import compute_run_quality


@unittest.skipUnless(predecessor.fixture.fixture.DSN,'Use disposable compose.test.yaml')
class TaxonomyReplacementPostgresTests(ReplacementFixture,unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await predecessor.PartialTaxonomyPublicationPostgresTests.asyncSetUp(self)
        environment = patch.dict(os.environ,{'TAXONOMY_PUBLICATION_ENABLED':'true'})
        environment.start()
        self.addCleanup(environment.stop)
        await self.create_sources()

    async def test_successor_replaces_every_original_and_split_array_then_replay_rollback(self):
        first = await self.build_run()
        await self.publish(first)
        await self.publish(first)
        before = await self.assert_matrix(first,'first')
        source_before = await self.source_rows()
        history_before = await self.frozen_history(first)
        reviewed_before = (await self.client.get(f'/taxonomy-runs/{first}')).json()['topics']
        second = await self.build_run('second')
        self.assertEqual(await self.read_inputs(),before,'ready candidate must not change current associations')
        await self.publish(second)
        await self.assert_matrix(second,'second')
        self.assertEqual(await self.db.fetchval('SELECT status FROM taxonomy_runs WHERE id=$1',first),'superseded')
        self.assertEqual(await self.frozen_history(first),history_before)
        self.assertEqual((await self.client.get(f'/taxonomy-runs/{first}')).json()['topics'],reviewed_before)
        # Historical evidence remains queryable through the protected run reader.
        for topic in reviewed_before:
            response = await self.client.get(f"/taxonomy-runs/{first}/topics/{topic['id']}/evidence")
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(len(response.json()['items']),topic['support_count'])
        second_history = await self.frozen_history(second)
        await self.publish(second)
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM taxonomy_publication_decisions'),2)
        for _ in range(2):
            await self.db.execute("SELECT rollback_taxonomy_run($1,'ptr7','Restore historical associations')",first)
            self.assertEqual(await self.read_inputs(),before)
        self.assertEqual(await self.frozen_history(second),second_history)
        self.assertEqual(await self.frozen_history(first),history_before)
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM taxonomy_rollback_decisions'),1)
        self.assertEqual(await self.source_rows(),source_before)
        self.assertEqual(await self.db.fetchval("SELECT count(*) FROM taxonomy_runs WHERE status='published'"),1)
        for table in ('original_inputs','segment_inputs'):
            columns = await self.db.fetch('SELECT column_name FROM information_schema.columns WHERE table_schema=$1 AND table_name=$2',self.schema,table)
            self.assertFalse({'topic','theme','taxonomy_state'} & {row['column_name'] for row in columns})

    async def test_failed_gate_and_failed_publication_leave_all_current_arrays_unchanged(self):
        first = await self.build_run()
        await self.publish(first)
        before = await self.assert_matrix(first,'first')
        history = await self.frozen_history(first)
        source = await self.source_rows()
        failed = await self.new_run()
        await compute_run_quality(self.pool,failed)
        updated = await self.db.fetchval('SELECT updated_at FROM taxonomy_runs WHERE id=$1',failed)
        response = await self.client.post(f'/taxonomy-runs/{failed}/publish',json={
            'expected_updated_at':updated.isoformat(),'operator':'ptr7'})
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(response.json()['detail']['code'],'taxonomy_publication_gate_failed')
        self.assertEqual(await self.read_inputs(),before)
        second = await self.build_run('second')
        # Fail after materialization and the swap, at the audit insertion.
        await self.db.execute("""CREATE FUNCTION ptr7_fail_audit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'private injected failure'; END; $$;
            CREATE TRIGGER ptr7_fail BEFORE INSERT ON taxonomy_publication_decisions FOR EACH ROW EXECUTE FUNCTION ptr7_fail_audit();""")
        updated = await self.db.fetchval('SELECT updated_at FROM taxonomy_runs WHERE id=$1',second)
        response = await self.client.post(f'/taxonomy-runs/{second}/publish',json={
            'expected_updated_at':updated.isoformat(),'operator':'ptr7'})
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(response.json()['detail']['code'],'taxonomy_decision_conflict')
        self.assertNotIn('private injected failure',response.text)
        self.assertEqual(await self.read_inputs(),before)
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM theme_revisions WHERE taxonomy_run_id=$1',second),0)
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM topic_aliases WHERE created_in_run_id=$1',second),0)
        self.assertEqual(await self.db.fetchval('SELECT status FROM taxonomy_runs WHERE id=$1',second),'ready_for_review')
        self.assertEqual(await self.frozen_history(first),history)
        self.assertEqual(await self.source_rows(),source)
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM taxonomy_publication_decisions'),1)
        await self.db.execute('DROP TRIGGER ptr7_fail ON taxonomy_publication_decisions')
        await self.publish(second)
        await self.assert_matrix(second,'second')

    async def test_competing_swap_and_inflight_readers_keep_one_complete_run(self):
        first = await self.build_run()
        await self.publish(first)
        before = await self.assert_matrix(first,'first')
        history = await self.frozen_history(first)
        source = await self.source_rows()
        second = await self.build_run('second')
        competing = await self.build_run('competing')
        expected = await self.db.fetchval('SELECT updated_at FROM taxonomy_runs WHERE id=$1',second)
        competitor_updated = await self.db.fetchval('SELECT updated_at FROM taxonomy_runs WHERE id=$1',competing)
        async with self.pool.acquire() as other:
            pid = await other.fetchval('SELECT pg_backend_pid()')
            async with self.db.transaction():
                await self.db.execute("SELECT pg_advisory_xact_lock(hashtext('taxonomy-publication'))")
                task = asyncio.create_task(other.execute("SELECT publish_taxonomy_run($1,$2,'ptr7')",competing,competitor_updated))
                try:
                    waiting = False
                    for _ in range(200):
                        waiting = await self.db.fetchval("SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=$1 AND locktype='advisory' AND NOT granted)",pid)
                        if waiting:
                            break
                        await asyncio.sleep(.01)
                    self.assertTrue(waiting,'competitor did not reach the publication lock')
                    await self.db.execute("SELECT publish_taxonomy_run($1,$2,'ptr7')",second,expected)
                    # The writer has changed both statuses and materialized themes,
                    # but an independent HTTP reader must see the old committed run.
                    self.assertEqual(await self.read_inputs(),before)
                except BaseException:
                    task.cancel()
                    await asyncio.gather(task,return_exceptions=True)
                    raise
            with self.assertRaisesRegex(asyncpg.PostgresError,'concurrent taxonomy publication'):
                await task
        await self.assert_matrix(second,'second')
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM theme_revisions WHERE taxonomy_run_id=$1',competing),0)
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM topic_aliases WHERE created_in_run_id=$1',competing),0)
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM taxonomy_publication_decisions'),2)
        # Re-reviewing and retrying the competing candidate is an explicit new
        # switch; a replay then returns exactly the same complete association set.
        await self.publish(competing)
        after = await self.assert_matrix(competing,'competing')
        await self.publish(competing)
        self.assertEqual(await self.read_inputs(),after)
        await self.db.execute("SELECT rollback_taxonomy_run($1,'ptr7','Concurrent test recovery')",first)
        self.assertEqual(await self.read_inputs(),before)
        self.assertEqual(await self.frozen_history(first),history)
        self.assertEqual(await self.source_rows(),source)
        self.assertEqual(await self.db.fetchval("SELECT count(*) FROM taxonomy_runs WHERE status='published'"),1)

    async def test_zero_theme_successor_removes_every_current_theme_and_rollback_restores_them(self):
        first = await self.build_run()
        await self.publish(first)
        before = await self.assert_matrix(first,'first')
        history = await self.frozen_history(first)
        second = await self.build_run('second',themes=False)
        await self.publish(second)
        await self.assert_matrix(second,'second',themes=False)
        self.assertTrue(all(row['themes']==[] for row in await self.read_inputs()))
        self.assertEqual(await self.frozen_history(first),history)
        await self.db.execute("SELECT rollback_taxonomy_run($1,'ptr7','Restore optional themes')",first)
        self.assertEqual(await self.read_inputs(),before)
