"""PTR-4 canonical themes and computed consistency on disposable PostgreSQL."""
import asyncio
import json
import os
import unittest
from unittest.mock import AsyncMock, patch

import asyncpg
from fastapi import FastAPI
import httpx

if __package__:
    from . import test_topic_reconciliation_postgres as fixture
else:
    import test_topic_reconciliation_postgres as fixture
from triage_processor.api.routes import taxonomy_review
from triage_processor.clients.llm import StructuredChatClient
from triage_processor.taxonomy_reconciliation import reconcile_run
from triage_processor.taxonomy_stage_quality import compute_run_quality, attestation_input_sha256
from triage_processor.taxonomy_stages import ClaimedStage, STAGES
from triage_processor.taxonomy_themes import infer_run, PROMPT_VERSION


@unittest.skipUnless(fixture.DSN, 'Use disposable compose.test.yaml')
class PartialTaxonomyQualityPostgresTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.TopicReconciliationPostgresTests.asyncSetUp
    new_run = fixture.TopicReconciliationPostgresTests.new_run
    merged = fixture.TopicReconciliationPostgresTests.merged
    reconcile = fixture.TopicReconciliationPostgresTests.reconcile

    async def provisional(self, *args):
        return await fixture.TopicReconciliationPostgresTests.provisional(self, *args, audited=True)

    async def prepare(self, *, merge=True, noise=0):
        response = self.merged() if merge else {'groups': [], 'no_merge_topic_ids': self.ids}
        with patch('triage_processor.clients.llm.StructuredChatClient.complete', new=AsyncMock(return_value=response)):
            await self.reconcile()
        for index in range(noise):
            # Same respondents across questions: evidence is not a submission count.
            question = self.sources[0][0]
            source = await self.db.fetchval("""INSERT INTO original_inputs(original_text,source,status,question_id,submission_key)
                VALUES('Private unclustered answer','ptr3','ineligible',$1,$2) RETURNING id""", question, f'respondent:{index%2}')
            embedding = await self.db.fetchval("""INSERT INTO input_embeddings(original_input_id,embedding,embedding_model,
                embedding_representation) VALUES($1,'[0,1]','fixture','question-answer') RETURNING id""", source)
            evidence = await self.db.fetchval("""INSERT INTO taxonomy_run_evidence(taxonomy_run_id,original_input_id,embedding_id)
                VALUES($1,$2,$3) RETURNING id""", self.run, source, embedding)
            await self.db.execute("""INSERT INTO taxonomy_cluster_memberships(taxonomy_run_id,evidence_id,decision)
                VALUES($1,$2,'noise')""", self.run, evidence)
        await self.complete_predecessors()

    async def complete_predecessors(self):
        for stage in STAGES[:STAGES.index('quality')]:
            await self.db.execute("""INSERT INTO taxonomy_run_stages(taxonomy_run_id,stage,attempt,status,completed_at,stage_output_sha256)
                VALUES($1,$2,1,'completed',CURRENT_TIMESTAMP,repeat('e',64)) ON CONFLICT DO NOTHING""", self.run, stage)

    async def facts(self):
        return json.loads(await self.db.fetchval('SELECT taxonomy_publication_facts($1)', self.run))

    async def gate(self, *, passed):
        facts = await compute_run_quality(self.pool, self.run)
        row = await self.db.fetchrow('SELECT * FROM taxonomy_release_attestations WHERE taxonomy_run_id=$1', self.run)
        self.assertEqual(row['gate_passed'], passed, row['failures'])
        return facts, row

    async def test_full_coverage_single_canonical_topic_needs_no_theme(self):
        await self.prepare()
        with patch('triage_processor.clients.llm.StructuredChatClient.complete', new=AsyncMock()) as model:
            self.assertEqual(await infer_run(self.pool, self.run, 'http://fixture', 'fixture'), 0)
            self.assertEqual(await infer_run(self.pool, self.run, 'http://fixture', 'fixture'), 0)
        model.assert_not_awaited()
        self.assertEqual(await reconcile_run(self.pool, self.run), ())
        facts, _ = await self.gate(passed=True)
        self.assertEqual((facts.evidence_count, facts.evidence_with_topic_count, facts.evidence_without_topic_count), (4,4,0))
        self.assertEqual((facts.canonical_topic_count, facts.reconciled_theme_count), (1,0))
        await self.db.execute("UPDATE taxonomy_runs SET status='running',started_at=CURRENT_TIMESTAMP WHERE id=$1",self.run)
        await self.db.execute("UPDATE taxonomy_runs SET status='ready_for_review',completed_at=CURRENT_TIMESTAMP WHERE id=$1",self.run)
        await self.db.execute('SELECT materialize_taxonomy_theme_revisions($1)',self.run)
        await self.db.execute('SELECT materialize_taxonomy_theme_revisions($1)',self.run)
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM theme_revisions'),0)

    async def test_low_coverage_rejected_attempts_and_separate_counts_pass(self):
        await self.prepare(noise=6)
        for index in range(20):
            question=self.sources[0][0]
            cluster=await self.db.fetchval("""INSERT INTO taxonomy_cluster_candidates(taxonomy_run_id,cluster_key,
                question_id,algorithm_label,member_count,centroid,diagnostics,policy_version,eligible,failure_reasons,
                packet_serialized_bytes,unique_original_count) VALUES($1,$2,$3,$4,2,'[0,1]','{}',
                'partial-topic-policy/v1',TRUE,'{}',256,2) RETURNING id""",self.run,f'rejected:{index}',question,index+2)
            for respondent in range(2):
                source=await self.db.fetchval("""INSERT INTO original_inputs(original_text,source,status,question_id,submission_key)
                    VALUES('Private rejected cluster answer','ptr3','ineligible',$1,$2) RETURNING id""",question,f'respondent:{respondent}')
                embedding=await self.db.fetchval("""INSERT INTO input_embeddings(original_input_id,embedding,embedding_model,
                    embedding_representation) VALUES($1,'[0,1]','fixture','question-answer') RETURNING id""",source)
                evidence=await self.db.fetchval("""INSERT INTO taxonomy_run_evidence(taxonomy_run_id,original_input_id,embedding_id)
                    VALUES($1,$2,$3) RETURNING id""",self.run,source,embedding)
                await self.db.execute("""INSERT INTO taxonomy_cluster_memberships(taxonomy_run_id,cluster_candidate_id,
                    evidence_id,membership_confidence,decision) VALUES($1,$2,$3,1,'clustered')""",self.run,cluster,evidence)
            context = {'cluster_key': f'rejected:{index}'}
            response = {'name': '', 'description': 'Private invalid model response', 'evidence_ids': []}
            await self.db.execute("""INSERT INTO taxonomy_topic_naming_attempts(taxonomy_run_id,cluster_candidate_id,
                attempt_number,model,prompt_version,prompt_sha256,request_context,raw_response,validation_errors,accepted)
                VALUES($1,$2,$3,'fixture','partial-topic-naming/v1',repeat('a',64),$4::jsonb,$5::jsonb,ARRAY['name_invalid'],FALSE)""",
                self.run,cluster,1,json.dumps(context),json.dumps(response))
            request = await self.db.fetchval("""INSERT INTO taxonomy_model_requests(taxonomy_run_id,stage,request_key,
                model,prompt_version,prompt_sha256,request_context,request_sha256)
                VALUES($1,'topic_naming',$2,'fixture','partial-topic-naming/v1',repeat('a',64),$3::jsonb,repeat('b',64)) RETURNING id""",
                self.run,f'rejected:{index}',json.dumps(context))
            await self.db.execute("""INSERT INTO taxonomy_model_responses(taxonomy_run_id,taxonomy_model_request_id,
                raw_response,validation_errors,accepted) VALUES($1,$2,$3::jsonb,ARRAY['name_invalid'],FALSE)""",self.run,request,json.dumps(response))
        facts, _ = await self.gate(passed=True)
        self.assertEqual((facts.evidence_count,facts.evidence_with_topic_count,facts.evidence_without_topic_count), (50,4,46))
        self.assertEqual((facts.question_count,facts.submission_count),(2,2))
        self.assertEqual((facts.naming_attempt_count,facts.rejected_topic_count),(22,20))
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM taxonomy_topic_naming_attempts WHERE NOT accepted'),20)

    async def test_related_canonical_topics_can_form_one_theme_with_exact_evidence(self):
        await self.prepare(merge=False)
        revisions = await self.db.fetch('SELECT id FROM topic_revisions WHERE taxonomy_run_id=$1 ORDER BY id',self.run)
        ids = [r['id'] for r in revisions]
        calls=[]
        raw={'create_theme': True, 'name':'Participation barriers','description':'Costs impede participation.',
             'rationale':'Distinct fees and charges have a broader relationship.','topic_revision_ids':ids}
        def transport(request):
            content=json.loads(request.content)['messages'][1]['content']
            packet=json.loads(content)
            self.assertLessEqual(len(content.encode()),32768)
            self.assertEqual([t['id'] for t in packet['topics']],ids)
            evidence=[e['evidence_id'] for t in packet['topics'] for e in t['evidence']]
            self.assertEqual(evidence,self.evidence)
            calls.append(packet)
            return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(raw)}}]})
        client=StructuredChatClient(base_url='http://fixture',model='fixture',transport=httpx.MockTransport(transport))
        with patch('triage_processor.taxonomy_themes.StructuredChatClient',return_value=client):
            self.assertEqual(await infer_run(self.pool,self.run,'http://fixture','fixture'),1)
        with patch('triage_processor.clients.llm.StructuredChatClient.complete',new=AsyncMock()) as model:
            await infer_run(self.pool,self.run,'http://fixture','fixture')
        model.assert_not_awaited()
        self.assertEqual(len(calls),1)
        plan=await reconcile_run(self.pool,self.run)
        self.assertEqual(await reconcile_run(self.pool,self.run),plan)
        facts,_=await self.gate(passed=True)
        self.assertEqual((facts.canonical_topic_count,facts.reconciled_theme_count),(2,1))
        self.assertEqual(await self.db.fetchval('SELECT prompt_version FROM taxonomy_theme_inference_attempts'),PROMPT_VERSION)

    async def test_model_no_theme_is_a_durable_valid_outcome(self):
        await self.prepare(merge=False)
        raw={'create_theme':False,'name':None,'description':None,'rationale':'Distinct topics need no broader theme.','topic_revision_ids':[]}
        with patch('triage_processor.clients.llm.StructuredChatClient.complete',new=AsyncMock(return_value=raw)) as model:
            await infer_run(self.pool,self.run,'http://fixture','fixture')
            await infer_run(self.pool,self.run,'http://fixture','fixture')
        self.assertEqual(model.await_count,1)
        self.assertEqual(await reconcile_run(self.pool,self.run),())
        await self.gate(passed=True)

    async def test_equivalent_antecedents_appear_once_in_theme_packet(self):
        question=await self.db.fetchval("""INSERT INTO questions(source,form_key,question_key,question_text)
            VALUES('ptr3','survey','reliability','How reliable is travel?') RETURNING id""")
        sources=[]
        for index in range(2):
            source=await self.db.fetchval("""INSERT INTO original_inputs(original_text,source,status,question_id)
                VALUES('Journey reliability','ptr3','ineligible',$1) RETURNING id""",question)
            embedding=await self.db.fetchval("""INSERT INTO input_embeddings(original_input_id,embedding,embedding_model,
                embedding_representation) VALUES($1,'[1,0]','fixture','question-answer') RETURNING id""",source)
            sources.append((source,embedding))
        related,_=await self.provisional(self.run,2,question,'Journey reliability',sources)
        response=self.merged()
        response['no_merge_topic_ids']=[related]
        with patch('triage_processor.clients.llm.StructuredChatClient.complete',new=AsyncMock(return_value=response)):
            await self.reconcile()
        await self.complete_predecessors()
        async def theme(**kwargs):
            topics=json.loads(kwargs['user_content'])['topics']
            self.assertEqual(len(topics),2)
            self.assertEqual([t['name'] for t in topics],['Access costs','Journey reliability'])
            return {'create_theme':True,'name':'Participation barriers','description':'Cost and reliability barriers.',
                    'rationale':'Related, distinct concepts.', 'topic_revision_ids':[t['id'] for t in topics]}
        with patch('triage_processor.clients.llm.StructuredChatClient.complete',new=AsyncMock(side_effect=theme)) as model:
            await infer_run(self.pool,self.run,'http://fixture','fixture')
        self.assertEqual(model.await_count,1)
        await reconcile_run(self.pool,self.run)
        facts,_=await self.gate(passed=True)
        self.assertEqual((facts.canonical_topic_count,facts.reconciled_theme_count),(2,1))
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM taxonomy_provisional_topics'),3)

    async def test_foreign_candidate_membership_is_rejected_and_corruption_blocks_check(self):
        await self.prepare()
        other=await self.new_run()
        _,foreign=await self.provisional(other,0,self.sources[0][0],'Other run costs',self.sources[0][1])
        revision=await self.db.fetchval('SELECT id FROM topic_revisions WHERE taxonomy_run_id=$1',self.run)
        with self.assertRaises(asyncpg.PostgresError):
            await self.db.execute('INSERT INTO topic_memberships(taxonomy_run_id,topic_revision_id,evidence_id) VALUES($1,$2,$3)',self.run,revision,foreign[0])
        # Deliberately corrupt only this isolated fixture, to prove the computed
        # consistency owner also catches corruption behind the insertion guards.
        await self.db.execute('ALTER TABLE topic_memberships DISABLE TRIGGER ALL')
        await self.db.execute('INSERT INTO topic_memberships(taxonomy_run_id,topic_revision_id,evidence_id) VALUES($1,$2,$3)',self.run,revision,foreign[0])
        await self.db.execute('ALTER TABLE topic_memberships ENABLE TRIGGER ALL')
        _,row=await self.gate(passed=False)
        self.assertIn('antecedent_membership_inconsistent',row['failures'])
        self.assertIn('topic_membership_inconsistent',row['failures'])

    async def test_unfinished_stage_blocks_check(self):
        await self.prepare()
        await self.db.execute("DELETE FROM taxonomy_run_stages WHERE stage='theme_inference'")
        _,row=await self.gate(passed=False)
        self.assertIn('processing_unfinished',row['failures'])

    async def test_missing_model_audit_cannot_be_replaced_by_another_label(self):
        await self.prepare()
        raw=await self.db.fetchval("""SELECT res.raw_response FROM taxonomy_model_responses res
            JOIN taxonomy_model_requests req ON req.id=res.taxonomy_model_request_id
            WHERE req.stage='topic_naming' ORDER BY req.id LIMIT 1""")
        # Simulate corrupted historical storage, bypassing only the response
        # immutability trigger inside this disposable schema.
        await self.db.execute('ALTER TABLE taxonomy_model_responses DISABLE TRIGGER taxonomy_model_responses_guard')
        await self.db.execute("DELETE FROM taxonomy_model_responses WHERE taxonomy_model_request_id=(SELECT min(id) FROM taxonomy_model_requests WHERE stage='topic_naming')")
        await self.db.execute('ALTER TABLE taxonomy_model_responses ENABLE TRIGGER taxonomy_model_responses_guard')
        request=await self.db.fetchval("""INSERT INTO taxonomy_model_requests(taxonomy_run_id,stage,request_key,
            model,prompt_version,prompt_sha256,request_context,request_sha256) VALUES($1,'topic_naming',
            'unrelated-context','fixture','partial-topic-naming/v1',repeat('c',64),
            '{"cluster_key":"unrelated-context"}',repeat('d',64)) RETURNING id""",self.run)
        await self.db.execute("""INSERT INTO taxonomy_model_responses(taxonomy_run_id,taxonomy_model_request_id,
            raw_response,accepted) VALUES($1,$2,$3::jsonb,TRUE)""",self.run,request,raw)
        _,row=await self.gate(passed=False)
        self.assertIn('model_trace_missing',row['failures'])

    async def test_missing_antecedent_and_missing_union_member_block_check(self):
        await self.prepare()
        await self.db.execute('ALTER TABLE taxonomy_canonical_topic_antecedents DISABLE TRIGGER canonical_topic_antecedents_guard')
        await self.db.execute('DELETE FROM taxonomy_canonical_topic_antecedents WHERE provisional_topic_id=$1',self.ids[1])
        await self.db.execute('ALTER TABLE taxonomy_canonical_topic_antecedents ENABLE TRIGGER canonical_topic_antecedents_guard')
        _,row=await self.gate(passed=False)
        self.assertIn('topic_trace_missing',row['failures'])
        self.assertIn('antecedent_membership_inconsistent',row['failures'])

    async def test_immutable_attestation_replay_concurrency_and_redacted_admin_api(self):
        await self.prepare(noise=1)
        results=await asyncio.gather(*[compute_run_quality(self.pool,self.run) for _ in range(2)])
        self.assertEqual(results[0],results[1])
        facts,row=await self.gate(passed=True)
        self.assertEqual(row['input_sha256'],attestation_input_sha256(json.loads(row['metrics'])))
        for statement in ('UPDATE taxonomy_release_attestations SET gate_passed=FALSE','DELETE FROM taxonomy_release_attestations'):
            with self.assertRaisesRegex(asyncpg.PostgresError,'immutable'):
                await self.db.execute(statement)
        app=FastAPI();app.include_router(taxonomy_review.router);app.state.db_pool=self.pool
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://fixture') as client:
            with patch.dict(os.environ,{'TAXONOMY_REVIEW_TOKEN':'ptr4-review','TAXONOMY_MUTATION_TOKEN':''}):
                self.assertEqual((await client.get(f'/taxonomy-runs/{self.run}')).status_code,200)
                self.assertEqual((await client.get(f'/taxonomy-runs/{self.run}',
                    headers={'Authorization':'Bearer incorrect'})).status_code,200)
                response=await client.get(f'/taxonomy-runs/{self.run}',headers={'Authorization':'Bearer ptr4-review'})
            with patch.dict(os.environ,{'TAXONOMY_REVIEW_TOKEN':'','TAXONOMY_MUTATION_TOKEN':'ptr4-mutation'}):
                self.assertEqual((await client.get(f'/taxonomy-runs/{self.run}')).status_code,200)
            with patch.dict(os.environ,{'TAXONOMY_REVIEW_TOKEN':'','TAXONOMY_MUTATION_TOKEN':''}):
                self.assertEqual((await client.get(f'/taxonomy-runs/{self.run}')).status_code,200)
        self.assertEqual(response.status_code,200,response.text)
        payload=response.json()
        self.assertEqual((payload['evidence_count'],payload['evidence_with_topic_count'],payload['evidence_without_topic_count']),(5,4,1))
        self.assertTrue(payload['gate_passed'])
        for private in ('Private unclustered answer','raw_response','request_context','system_prompt'):
            self.assertNotIn(private,response.text)

    async def test_stale_quality_lease_and_wrong_stage_write_nothing(self):
        await self.prepare()
        identifier=await self.db.fetchval("""INSERT INTO taxonomy_run_stages(taxonomy_run_id,stage,attempt,status,lease_owner,
            lease_expires_at,heartbeat_at) VALUES($1,'quality',1,'running','owner',CURRENT_TIMESTAMP+INTERVAL '5 minutes',CURRENT_TIMESTAMP)
            RETURNING id""",self.run)
        stage=ClaimedStage(identifier,self.run,'quality',1,'stale')
        with self.assertRaisesRegex(RuntimeError,'lease is no longer owned'):
            await compute_run_quality(self.pool,self.run,stage=stage)
        with self.assertRaisesRegex(ValueError,'does not match'):
            await compute_run_quality(self.pool,self.run,stage=ClaimedStage(identifier,self.run,'theme_inference',1,'owner'))
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM taxonomy_release_attestations'),0)

    async def test_stale_theme_response_saves_nothing_and_holds_no_transaction(self):
        await self.prepare(merge=False)
        await self.db.execute("DELETE FROM taxonomy_run_stages WHERE stage='theme_inference'")
        identifier=await self.db.fetchval("""INSERT INTO taxonomy_run_stages(taxonomy_run_id,stage,attempt,status,
            lease_owner,lease_expires_at,heartbeat_at) VALUES($1,'theme_inference',1,'running','owner',
            CURRENT_TIMESTAMP+INTERVAL '5 minutes',CURRENT_TIMESTAMP) RETURNING id""",self.run)
        stage=ClaimedStage(identifier,self.run,'theme_inference',1,'owner')
        started,release=asyncio.Event(),asyncio.Event()
        async def response(**_):
            started.set()
            await release.wait()
            return {'create_theme':False,'topic_revision_ids':[]}
        with patch('triage_processor.clients.llm.StructuredChatClient.complete',new=AsyncMock(side_effect=response)):
            task=asyncio.create_task(infer_run(self.pool,self.run,'http://fixture','fixture',stage=stage))
            await asyncio.wait_for(started.wait(),5)
            try:
                async with self.db.transaction():
                    await self.db.fetchval('SELECT id FROM taxonomy_run_stages WHERE id=$1 FOR UPDATE NOWAIT',identifier)
                await self.db.execute("UPDATE taxonomy_run_stages SET lease_owner='replacement' WHERE id=$1",identifier)
            finally:
                release.set()
            with self.assertRaisesRegex(RuntimeError,'lease is no longer owned'):
                await task
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM taxonomy_theme_inference_attempts'),0)
        self.assertEqual(await self.db.fetchval('SELECT count(*) FROM taxonomy_candidate_themes'),0)
        self.assertEqual(await self.db.fetchval("""SELECT count(*) FROM taxonomy_model_responses res
            JOIN taxonomy_model_requests req ON req.id=res.taxonomy_model_request_id WHERE req.stage='theme_inference'"""),0)
