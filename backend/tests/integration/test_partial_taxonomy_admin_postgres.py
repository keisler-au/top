"""PTR-6 operator/read/generation contracts against disposable PostgreSQL."""
import os
import unittest
from unittest.mock import patch

if __package__:
    from . import test_partial_taxonomy_publication_postgres as fixture
else:
    import test_partial_taxonomy_publication_postgres as fixture


@unittest.skipUnless(fixture.fixture.fixture.DSN, 'Use disposable compose.test.yaml')
class PartialTaxonomyAdminPostgresTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.PartialTaxonomyPublicationPostgresTests.asyncSetUp
    new_run = fixture.PartialTaxonomyPublicationPostgresTests.new_run
    provisional = fixture.PartialTaxonomyPublicationPostgresTests.provisional
    merged = fixture.PartialTaxonomyPublicationPostgresTests.merged
    reconcile = fixture.PartialTaxonomyPublicationPostgresTests.reconcile
    prepare = fixture.PartialTaxonomyPublicationPostgresTests.prepare
    complete_predecessors = fixture.PartialTaxonomyPublicationPostgresTests.complete_predecessors
    ready = fixture.PartialTaxonomyPublicationPostgresTests.ready
    publish = fixture.PartialTaxonomyPublicationPostgresTests.publish
    successor = fixture.PartialTaxonomyPublicationPostgresTests.successor
    get = fixture.PartialTaxonomyPublicationPostgresTests.get

    async def test_review_readable_merged_antecedents_and_canonical_evidence(self):
        await self.ready()
        review = await self.get(f'/taxonomy-runs/{self.run}')
        self.assertEqual((review['evidence_count'],review['evidence_with_topic_count'],review['evidence_without_topic_count']),(6,4,2))
        self.assertTrue(review['gate_passed'])
        self.assertEqual(review['theme_count'],0)
        topic = review['topics'][0]
        self.assertEqual(topic['antecedent_provisional_topic_ids'],self.ids)
        self.assertEqual([a['name'] for a in topic['antecedents']],['Access fees','Service charges'])
        self.assertEqual({a['question_id'] for a in topic['antecedents']},{q for q,_ in self.sources})
        self.assertTrue(all(a['relationship']=='equivalent' and a['support_count']==2 for a in topic['antecedents']))
        evidence = await self.get(f"/taxonomy-runs/{self.run}/topics/{topic['id']}/evidence")
        self.assertEqual([e['id'] for e in evidence['items']],self.evidence)
        self.assertEqual((evidence['offset'],evidence['page_size']),(0,50))
        tail = await self.get(f"/taxonomy-runs/{self.run}/topics/{topic['id']}/evidence?offset=50")
        self.assertEqual(tail['items'],[])
        for offset in (-1,100001):
            self.assertEqual((await self.client.get(f"/taxonomy-runs/{self.run}/topics/{topic['id']}/evidence?offset={offset}")).status_code,422)
        self.assertEqual((await self.client.get(f"/taxonomy-runs/{self.run}/topics/99999/evidence")).status_code,404)
        forbidden = {'raw_response','request_context','decision','prompt','rationale','inference_request','inference_response'}
        def keys(value):
            if isinstance(value,dict):
                return set(value).union(*(keys(v) for v in value.values()))
            if isinstance(value,list):
                return set().union(*(keys(v) for v in value))
            return set()
        self.assertFalse(forbidden & keys(review))

    async def test_unresolved_review_is_bounded_and_preserves_support(self):
        await self.prepare()
        question = self.sources[0][0]
        await self.db.execute("""INSERT INTO taxonomy_cluster_candidates(taxonomy_run_id,cluster_key,
            question_id,algorithm_label,member_count,centroid,diagnostics,policy_version,eligible,failure_reasons,
            packet_serialized_bytes,unique_original_count)
            SELECT $1,'unresolved:'||n,$2,n+2,2,'[0,1]','{}','partial-topic-policy/v1',FALSE,
                ARRAY['cohesion_below_minimum'],256,2 FROM generate_series(1,101) n""",self.run,question)
        review = await self.get(f'/taxonomy-runs/{self.run}')
        self.assertTrue(review['truncated'])
        self.assertEqual(len(review['clusters']),100)
        unresolved = [c for c in review['clusters'] if c['outcome']=='unresolved']
        self.assertTrue(unresolved)
        self.assertTrue(all(c['support_count']==2 and c['reasons']==['cohesion_below_minimum'] for c in unresolved))
        self.assertNotIn('Private',str(review))

    async def test_rejected_naming_shows_reason_without_raw_model_payload(self):
        await self.prepare()
        cluster = await self.db.fetchval("""INSERT INTO taxonomy_cluster_candidates(taxonomy_run_id,cluster_key,
            question_id,algorithm_label,member_count,centroid,diagnostics,policy_version,eligible,failure_reasons,
            packet_serialized_bytes,unique_original_count)
            VALUES($1,'rejected',$2,9,2,'[0,1]','{}','partial-topic-policy/v1',TRUE,'{}',256,2)
            RETURNING id""",self.run,self.sources[0][0])
        await self.db.execute("""INSERT INTO taxonomy_topic_naming_attempts(taxonomy_run_id,cluster_candidate_id,
            attempt_number,model,prompt_version,prompt_sha256,request_context,raw_response,validation_errors,accepted)
            VALUES($1,$2,1,'fixture','partial-topic-naming/v1',repeat('a',64),
                '{"prompt":"private-prompt"}','{"description":"private-model-payload"}',ARRAY['name_blank'],FALSE)""",
            self.run,cluster)
        review = await self.get(f'/taxonomy-runs/{self.run}')
        rejected = next(c for c in review['clusters'] if c['id']==cluster)
        self.assertEqual((rejected['outcome'],rejected['support_count'],rejected['reasons']),('unresolved',2,['name_blank']))
        self.assertNotIn('private-prompt',str(review))
        self.assertNotIn('private-model-payload',str(review))

    async def test_review_reads_need_no_credentials_or_operator_configuration(self):
        await self.prepare()
        revision = await self.db.fetchval('SELECT id FROM topic_revisions WHERE taxonomy_run_id=$1',self.run)
        paths = ['/taxonomy-runs',f'/taxonomy-runs/{self.run}',f'/taxonomy-runs/{self.run}/topics/{revision}/evidence']
        self.client.headers.pop('Authorization', None)
        for configuration in ({'TAXONOMY_REVIEW_TOKEN':'review','TAXONOMY_MUTATION_TOKEN':''},
                              {'TAXONOMY_REVIEW_TOKEN':'','TAXONOMY_MUTATION_TOKEN':'mutate'},
                              {'TAXONOMY_REVIEW_TOKEN':'','TAXONOMY_MUTATION_TOKEN':'',
                               'OPERATIONS_RATE_LIMIT_REQUESTS':'invalid'}):
            with patch.dict(os.environ,configuration):
                for path in paths:
                    response = await self.client.get(path)
                    self.assertEqual(response.status_code,200,response.text)
                    response = await self.client.get(path,headers={'Authorization':'Bearer wrong'})
                    self.assertEqual(response.status_code,200,response.text)
                # Viewing does not relax access to taxonomy writes or operations.
                for action in ('publish','reject'):
                    response = await self.client.post(f'/taxonomy-runs/{self.run}/{action}',json={
                        'expected_updated_at':'2026-01-01T00:00:00Z','operator':'anonymous'})
                    self.assertEqual(response.status_code,401 if configuration['TAXONOMY_MUTATION_TOKEN'] else 503)
                response = await self.client.post(f'/taxonomy-runs/{self.run}/schedule')
                self.assertEqual(response.status_code,401 if configuration['TAXONOMY_MUTATION_TOKEN'] else 503)
                response = await self.client.get('/operations/summary')
                self.assertEqual(response.status_code,401 if any(configuration[k] for k in ('TAXONOMY_REVIEW_TOKEN','TAXONOMY_MUTATION_TOKEN')) else 503)

    async def test_partial_canonical_topic_recommendations_and_empty_input_associations(self):
        await self.ready()
        await self.publish()
        for strategy in ('most-evidence','least-covered'):
            result = await self.get(f'/recommendations/articles?type=topic&strategy={strategy}')
            self.assertEqual(len(result['items']),1)
            self.assertEqual(result['items'][0]['type'],'topic')
        self.assertEqual((await self.get('/taxonomy?type=theme'))['items'],[])
        self.assertEqual(len((await self.get('/taxonomy?type=topic'))['items']),1)
        rows = await self.get('/inputs')
        self.assertTrue(any(item['topics']==[] and item['themes']==[] for item in rows))
        self.assertTrue(all('taxonomy_state' not in item and item['published_taxonomy_run_id']==self.run for item in rows))

    # Reexecute the full HTTP job/worker persistence proof as PTR-6 evidence;
    # it includes a publication during job creation and rejects foreign evidence.
    test_zero_theme_generation_freezes_canonical_evidence = fixture.PartialTaxonomyPublicationPostgresTests.test_topic_generation_without_themes_freezes_scope_and_rejects_foreign_evidence
