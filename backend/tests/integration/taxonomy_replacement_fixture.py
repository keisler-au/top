"""Reusable PTR-7 matrix of immutable evidence and computed-gate runs.

This fixture supplies audited predecessor stage outputs. It calls the real
canonical/topic and theme reconciliation, quality and publication owners.
It does not replace PTR-8's ingestion/worker/scheduler journey.
"""
import json
from uuid import uuid4

if __package__:
    from . import test_partial_taxonomy_publication_postgres as predecessor
else:
    import test_partial_taxonomy_publication_postgres as predecessor

from triage_processor.taxonomy_reconciliation import reconcile_run
from triage_processor.taxonomy_stage_quality import compute_run_quality
from triage_processor.taxonomy_stages import record_model_request, record_model_response
from triage_processor.taxonomy_themes import validate_theme, PROMPT_VERSION, PROMPT_SHA256


class ReplacementFixture:
    new_run = predecessor.PartialTaxonomyPublicationPostgresTests.new_run
    provisional = predecessor.PartialTaxonomyPublicationPostgresTests.provisional
    reconcile = predecessor.PartialTaxonomyPublicationPostgresTests.reconcile
    complete_predecessors = predecessor.PartialTaxonomyPublicationPostgresTests.complete_predecessors

    async def create_sources(self):
        self.form = 'ptr7-' + uuid4().hex
        self.question = await self.db.fetchval("""INSERT INTO questions(source,form_key,question_key,question_text)
            VALUES('ptr7',$1,'access','What helps or prevents access?') RETURNING id""", self.form)
        self.inputs = {}
        self.sources_by_key = {}
        for name in ('added','removed','replaced','empty','anchor_a','anchor_b','split'):
            identifier = await self.db.fetchval("""INSERT INTO original_inputs(original_text,source,status,question_id)
                VALUES($1,'ptr7','completed',$2) RETURNING id""", 'Private PTR7 answer: '+name, self.question)
            self.inputs[name] = identifier
            if name != 'split':
                embedding = await self.db.fetchval("""INSERT INTO input_embeddings(original_input_id,embedding,
                    embedding_model,embedding_representation) VALUES($1,'[1,0]','fixture','question-answer') RETURNING id""", identifier)
                self.sources_by_key[name] = (identifier, embedding)
        original = self.inputs['split']
        decision = await self.db.fetchval("""INSERT INTO input_preparation_decisions(original_input_id,eligible,
            segments,model,prompt_version,decision_source) VALUES($1,TRUE,
            '["First idea","Repeated first idea","Second idea","Unclustered idea"]','fixture','fixture','model') RETURNING id""", original)
        for order, answer in enumerate(('First idea','Repeated first idea','Second idea','Unclustered idea')):
            segment = await self.db.fetchval("""INSERT INTO segment_inputs(original_input_id,segment_order,
                segment_text,preparation_decision_id) VALUES($1,$2,$3,$4) RETURNING id""", original, order, answer, decision)
            embedding = await self.db.fetchval("""INSERT INTO input_embeddings(segment_input_id,embedding,
                embedding_model,embedding_representation) VALUES($1,'[1,0]','fixture','question-answer') RETURNING id""", segment)
            self.sources_by_key['segment_'+str(order)] = (original, embedding, segment)

    async def build_run(self, version='first', *, themes=True):
        run = await self.new_run()
        if version == 'first':
            groups = [('Zulu old',('removed','replaced','segment_0','segment_1')),
                      ('alpha retained',('anchor_a','anchor_b','segment_2'))]
            theme_names = ('Zulu historical','Alpha historical')
        else:
            suffix = 'new' if version == 'second' else 'competing'
            groups = [('Beta '+suffix,('added','replaced','segment_0','segment_2')),
                      ('alpha retained',('anchor_a','anchor_b','segment_1'))]
            theme_names = ('Yankee '+suffix,'Beta '+suffix)
        covered = set()
        for index, (name, keys) in enumerate(groups):
            await self.provisional(run,index,self.question,name,[self.sources_by_key[key] for key in keys])
            covered.update(keys)
        for key in sorted(self.sources_by_key.keys() - covered):
            source = self.sources_by_key[key]
            evidence = await self.db.fetchval("""INSERT INTO taxonomy_run_evidence(taxonomy_run_id,
                original_input_id,embedding_id,segment_input_id) VALUES($1,$2,$3,$4) RETURNING id""",
                run,source[0],source[1],source[2] if len(source)==3 else None)
            await self.db.execute("""INSERT INTO taxonomy_cluster_memberships(taxonomy_run_id,evidence_id,decision)
                VALUES($1,$2,'noise')""",run,evidence)
        # One question: canonical reconciliation stores isolated singleton decisions.
        await self.reconcile(run)
        revisions = await self.db.fetch('SELECT id,name,topic_id FROM topic_revisions WHERE taxonomy_run_id=$1 ORDER BY id',run)
        if themes:
            for index, name in enumerate(theme_names):
                await self.add_theme(run,index,name,[row['id'] for row in revisions])
        await reconcile_run(self.pool,run)
        self.run = run
        await self.complete_predecessors()
        await compute_run_quality(self.pool,run)
        gate = await self.db.fetchrow('SELECT gate_passed,failures FROM taxonomy_release_attestations WHERE taxonomy_run_id=$1',run)
        self.assertTrue(gate['gate_passed'],gate['failures'])
        await self.db.execute("UPDATE taxonomy_runs SET status='running',started_at=CURRENT_TIMESTAMP WHERE id=$1",run)
        await self.db.execute("UPDATE taxonomy_runs SET status='ready_for_review',completed_at=CURRENT_TIMESTAMP WHERE id=$1",run)
        return run

    async def add_theme(self,run,index,name,topics):
        request = {'topics':[{'id':identifier} for identifier in topics]}
        raw = {'create_theme':True,'name':name,'description':'A related access pattern.',
               'rationale':'Two related distinct topics.','topic_revision_ids':topics}
        self.assertEqual(validate_theme(raw,set(topics)),(True,()))
        request_id = await record_model_request(self.pool,run_id=run,stage='theme_inference',
            request_key=f'ptr7:{index}',model='fixture',prompt_version=PROMPT_VERSION,
            prompt_sha256=PROMPT_SHA256,request_context=request)
        async with self.db.transaction():
            await record_model_response(self.db,run_id=run,request_id=request_id,
                raw_response=raw,validation_errors=(),accepted=True)
            await self.db.execute("""INSERT INTO taxonomy_theme_inference_attempts(taxonomy_run_id,
                neighbourhood_key,model,prompt_version,prompt_sha256,request_context,raw_response,accepted)
                VALUES($1,$2,'fixture',$3,$4,$5::jsonb,$6::jsonb,TRUE)""",
                run,f'ptr7:{index}',PROMPT_VERSION,PROMPT_SHA256,json.dumps(request),json.dumps(raw))
            candidate = await self.db.fetchval("""INSERT INTO taxonomy_candidate_themes(taxonomy_run_id,name,
                description,rationale,inference_request,inference_response) VALUES($1,$2,$3,$4,$5::jsonb,$6::jsonb) RETURNING id""",
                run,name,raw['description'],raw['rationale'],json.dumps(request),json.dumps(raw))
            await self.db.executemany("""INSERT INTO taxonomy_candidate_theme_topics(taxonomy_run_id,
                candidate_theme_id,topic_revision_id) VALUES($1,$2,$3)""",[(run,candidate,topic) for topic in topics])

    async def publish(self,run):
        updated = await self.db.fetchval('SELECT updated_at FROM taxonomy_runs WHERE id=$1',run)
        response = await self.client.post(f'/taxonomy-runs/{run}/publish',json={
            'expected_updated_at':updated.isoformat(),'operator':'ptr7','note':'Successive-run fixture'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['id'],run)

    async def read_inputs(self):
        response = await self.client.get('/inputs',params={'source':'ptr7','form_key':self.form,'limit':50})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    async def assert_matrix(self,run,version,*,themes=True,rows=None):
        rows = await self.read_inputs() if rows is None else rows
        self.assertEqual({row['id'] for row in rows},set(self.inputs.values()))
        self.assertEqual({row['published_taxonomy_run_id'] for row in rows},{run})
        self.assertTrue(all('taxonomy_state' not in row and row['status']=='completed' for row in rows))
        by_id = {row['id']:row for row in rows}
        beta = 'Zulu old' if version=='first' else 'Beta '+('new' if version=='second' else 'competing')
        names = {'added':[] if version=='first' else [beta],
                 'removed':[beta] if version=='first' else [],'replaced':[beta],'empty':[],
                 'anchor_a':['alpha retained'],'anchor_b':['alpha retained'],
                 'split':['alpha retained',beta]}
        theme_rows = await self.db.fetch('SELECT theme_id AS id,name,description FROM theme_revisions WHERE taxonomy_run_id=$1 ORDER BY lower(name),theme_id',run)
        expected_themes = [dict(row) for row in theme_rows] if themes else []
        self.assertEqual(len(expected_themes),2 if themes else 0)
        for key,identifier in self.inputs.items():
            item = by_id[identifier]
            self.assertEqual([topic['name'] for topic in item['topics']],names[key],key)
            revisions = await self.db.fetch('SELECT topic_id AS id,name FROM topic_revisions WHERE taxonomy_run_id=$1 AND name=ANY($2::text[]) ORDER BY lower(name),topic_id',run,names[key])
            self.assertEqual(item['topics'],[dict(row) for row in revisions],key)
            self.assertEqual(item['themes'],expected_themes if names[key] else [],key)
        # The parent has four segments: repeated membership and one unclustered
        # segment must still yield two ordered unique topics/two unique themes.
        self.assertEqual(len(by_id[self.inputs['split']]['topics']),2)
        return rows

    async def frozen_history(self,run):
        tables = ('taxonomy_run_evidence','taxonomy_cluster_candidates','taxonomy_cluster_memberships',
                  'taxonomy_cluster_representatives','taxonomy_topic_naming_attempts','taxonomy_provisional_topics',
                  'taxonomy_topic_reconciliation_decisions','taxonomy_canonical_topic_antecedents','topic_revisions',
                  'topic_memberships','topic_representative_evidence','topic_lineage','taxonomy_candidate_themes',
                  'taxonomy_candidate_theme_topics','taxonomy_theme_inference_attempts','taxonomy_reconciled_themes',
                  'taxonomy_reconciled_theme_antecedents','theme_revisions','theme_revision_topics','theme_lineage',
                  'taxonomy_model_requests','taxonomy_model_responses','taxonomy_run_stages',
                  'taxonomy_release_attestations','taxonomy_publication_decisions')
        result = {}
        for table in tables:
            result[table] = await self.db.fetchval(f"SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),'[]'::jsonb)::text FROM {table} t WHERE taxonomy_run_id=$1",run)
        result['provenance'] = await self.db.fetchval("""SELECT (to_jsonb(r)-ARRAY['status','updated_at',
            'decision_by','decision_at','decision_note','published_at'])::text FROM taxonomy_runs r WHERE id=$1""",run)
        return result

    async def source_rows(self):
        return {table:await self.db.fetchval(f"SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.id),'[]')::text FROM {table} t")
                for table in ('original_inputs','segment_inputs','input_preparation_decisions','input_embeddings')}
