"""Disposable PTR-8 journey: real workers/Ollama, deterministic structured chat.

Only Google Sheets transport/auth and structured chat output are fixtures. The
production Sheets reader, poll processor, HTTP sink, API, queues, scheduler,
clustering/reconciliation/gate, generation and public edge remain real.
"""
from __future__ import annotations

import asyncio
import json
import os
import time

import asyncpg
import httpx

from triage_processor.integrations.google_sheets import (
    ApiInputSink, GoogleSheetsReader, claim_form_source, process_form_source,
)

API = os.getenv('JOURNEY_API_BASE_URL', 'http://api:8000')
EDGE = os.getenv('JOURNEY_EDGE_BASE_URL', 'http://public-web:8080')
CHAT = os.getenv('JOURNEY_CHAT_BASE_URL', 'http://chat-fixture:8080')
DSN = os.environ['DATABASE_URL']
FREQUENT = 'More frequent buses for rural villages.'
FARES = 'Affordable fares for local public transport.'


async def wait_for(description, check, timeout=180):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = await check()
        if last:
            return last
        await asyncio.sleep(.3)
    raise AssertionError(f'Timed out: {description}; last={last}')


async def main():
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=3)
    db = await asyncpg.connect(DSN)
    async with httpx.AsyncClient(base_url=API, timeout=15) as api, httpx.AsyncClient(base_url=EDGE) as edge, httpx.AsyncClient(base_url=CHAT) as chat:
        async def request(method, path, **kwargs):
            response = await api.request(method, path, **kwargs)
            assert response.is_success, (method, path, response.status_code, response.text)
            return response.json()

        async def mode(value):
            (await chat.post('/fixture/mode', json={'mode': value})).raise_for_status()

        async def add(text, sequence):
            return await request('POST', '/inputs', json={
                'original_text': text, 'source': 'taxonomy-compose-journey',
                'source_record_key': str(sequence), 'submission_key': str(sequence),
                'question_context': {'form_key': 'journey-api', 'question_key': 'transport',
                                     'question_version': 1, 'question_text': 'How could transport improve?'},
            })

        async def terminal(after=0, status='published'):
            async def check():
                failed_stage = await db.fetchrow("SELECT r.id,r.error_summary FROM taxonomy_runs r WHERE r.id>$1 AND r.status='failed' ORDER BY r.id DESC LIMIT 1", after)
                assert failed_stage is None, f'Unexpected failed taxonomy stage: {failed_stage}'
                if status == 'published':
                    blocked = await db.fetchrow("SELECT r.id,g.failures FROM taxonomy_runs r JOIN taxonomy_release_attestations g ON g.taxonomy_run_id=r.id WHERE r.id>$1 AND NOT g.gate_passed ORDER BY r.id DESC LIMIT 1", after)
                    assert blocked is None, f'Unexpected computed gate failure: {blocked}'
                return await db.fetchval('SELECT id FROM taxonomy_runs WHERE id>$1 AND status=$2 ORDER BY id DESC LIMIT 1', after, status)
            return await wait_for(f'{status} successor after {after}', check)

        async def inputs():
            return await request('GET', '/inputs', params={'limit': 100})

        async def verify(run, *, partial, themes, count):
            rows = await inputs()
            assert {row['published_taxonomy_run_id'] for row in rows} == {run}, rows
            assert all('taxonomy_state' not in row and row['question_id'] for row in rows)
            assert await db.fetchval("SELECT count(*) FROM taxonomy_runs WHERE status='published'") == 1
            stages = await db.fetch('SELECT stage,status FROM taxonomy_run_stages WHERE taxonomy_run_id=$1', run)
            assert len(stages) == 8 and all(row['status'] == 'completed' for row in stages), stages
            gate = await db.fetchrow('SELECT gate_passed,threshold_version,failures FROM taxonomy_release_attestations WHERE taxonomy_run_id=$1', run)
            assert gate['gate_passed'] and gate['threshold_version'] == 'taxonomy-release-gate-v3' and list(gate['failures']) == []
            summary = await request('GET', '/dashboard/summary')
            assert summary['published_taxonomy_run_id'] == run and summary['evidence_count'] == count, summary
            assert summary['evidence_with_topic_count'] + summary['evidence_without_topic_count'] == count
            assert summary['topic_coverage'] == ('partial' if partial else 'full'), summary
            assert summary['evidence_without_topic_count'] == (6 if partial else 0), summary
            assert summary['evidence_with_topic_count'] == count - (6 if partial else 0), summary
            assert await db.fetchval('SELECT count(*) FROM theme_revisions WHERE taxonomy_run_id=$1', run) == themes
            expected = {'Accessible transit'} if partial else {'Accessible transit', 'Affordable travel'}
            topics = await db.fetch('SELECT id,name,support_count FROM topic_revisions WHERE taxonomy_run_id=$1 ORDER BY id', run)
            assert {topic['name'] for topic in topics} == expected, topics
            for topic in topics:
                assert await db.fetchval('SELECT count(*) FROM taxonomy_canonical_topic_antecedents WHERE taxonomy_run_id=$1 AND topic_revision_id=$2', run, topic['id']) == 2
                assert await db.fetchval('SELECT count(*) FROM topic_memberships WHERE taxonomy_run_id=$1 AND topic_revision_id=$2', run, topic['id']) == topic['support_count']
                actual = {row['evidence_id'] for row in await db.fetch(
                    'SELECT evidence_id FROM topic_memberships WHERE taxonomy_run_id=$1 AND topic_revision_id=$2', run, topic['id'])}
                antecedents = await db.fetch("""
                    SELECT DISTINCT m.evidence_id, c.question_id
                    FROM taxonomy_canonical_topic_antecedents a
                    JOIN taxonomy_provisional_topics p ON p.id=a.provisional_topic_id AND p.taxonomy_run_id=a.taxonomy_run_id
                    JOIN taxonomy_cluster_candidates c ON c.id=p.cluster_candidate_id AND c.taxonomy_run_id=p.taxonomy_run_id
                    JOIN taxonomy_cluster_memberships m ON m.cluster_candidate_id=p.cluster_candidate_id AND m.taxonomy_run_id=p.taxonomy_run_id
                    WHERE a.taxonomy_run_id=$1 AND a.topic_revision_id=$2 AND m.decision='clustered'
                """, run, topic['id'])
                assert actual == {row['evidence_id'] for row in antecedents}
                assert len({row['question_id'] for row in antecedents}) == 2
            if themes:
                assert {row['topic_revision_id'] for row in await db.fetch(
                    'SELECT topic_revision_id FROM theme_revision_topics WHERE taxonomy_run_id=$1', run)} == {topic['id'] for topic in topics}
            assert await db.fetchval("SELECT count(*) FROM taxonomy_automation_decisions WHERE taxonomy_run_id=$1 AND status='snapshotted'", run) == 1
            # Automatic replay must retain its existing immutable decision.
            before = await db.fetchval('SELECT count(*) FROM taxonomy_publication_decisions')
            await db.execute("SELECT publish_taxonomy_run_automatically($1,'taxonomy-automation-v3')", run)
            assert await db.fetchval('SELECT count(*) FROM taxonomy_publication_decisions') == before
            review = await request('GET', f'/taxonomy-runs/{run}', headers={'Authorization': 'Bearer journey-review-only'})
            assert review['evidence_count'] == count, review
            assert all(len(topic['antecedents']) == 2 for topic in review['topics'])
            for row in rows:
                if 'SPAM' in row['original_text']:
                    assert row['topics'] == [] and row['themes'] == []
                elif partial and 'fares' in row['original_text']:
                    assert row['topics'] == [] and row['themes'] == []
                else:
                    assert len(row['topics']) == 1 and len(row['themes']) == themes, row
            return rows, topics

        try:
            assert await db.fetchval('SELECT count(*) FROM original_inputs') == 0, 'Use a fresh disposable journey database'
            await mode('partial')
            source = await request('POST', '/form-sources', json={
                'form_id': 'journey-sheet', 'spreadsheet_id': 'fixture-sheet', 'sheet_name': 'Responses',
                'ignored_headers': ['Timestamp'], 'enabled': True,
            })
            # A privacy-safe Sheets values response passes through the actual
            # Google reader and importer; live credentials are never required.
            def sheet_response(request):
                assert request.headers['Authorization'] == 'Bearer journey-fixture'
                values = [['Timestamp', 'How could transport improve?']] if request.url.path.endswith('1:1') else [[str(i), text] for i, text in enumerate([FREQUENT]*3+[FARES]*3)]
                return httpx.Response(200, json={'values': values})
            class Credentials:
                valid = True
                token = 'journey-fixture'
            sheets = GoogleSheetsReader(Credentials(), transport=httpx.MockTransport(sheet_response))
            sink = ApiInputSink(API)
            try:
                claimed = await claim_form_source(pool)
                assert claimed.id == source['id']
                assert await process_form_source(pool, sheets, sink, claimed, batch_size=10) == 6
                # Re-delivering identical rows exercises HTTP idempotency.
                assert await process_form_source(pool, sheets, sink, claimed, batch_size=10) == 6
            finally:
                await sink.close()
                await sheets.close()
            assert await db.fetchval('SELECT last_read_row FROM form_sources WHERE id=$1', source['id']) == 7
            for i, text in enumerate([FREQUENT]*3+[FARES]*3+['SPAM unrelated advertisement']):
                await add(text, i)
            first = await terminal()
            first_inputs, topics = await verify(first, partial=True, themes=0, count=12)
            spam = await db.fetchrow("SELECT id,status FROM original_inputs WHERE original_text LIKE 'SPAM%'")
            assert spam['status'] == 'ineligible', spam
            assert await db.fetchval('SELECT count(*) FROM input_embeddings WHERE original_input_id=$1', spam['id']) == 0
            assert await db.fetchval('SELECT count(*) FROM original_inputs') == 13
            assert {row['source'] for row in first_inputs if row['topics']} == {'google-sheets', 'taxonomy-compose-journey'}, first_inputs
            assert await db.fetchval('SELECT count(*) FROM input_embeddings') == 12
            assert await db.fetchval("SELECT count(*) FROM input_embeddings WHERE embedding_model='nomic-embed-text' AND embedding_representation='question-answer' AND vector_dims(embedding)=768") == 12
            # Neutral model labels intentionally have no word overlap with the
            # bus answers; accepted provisional topics are still publishable.
            assert await db.fetchval('SELECT count(*) FROM taxonomy_provisional_topics WHERE taxonomy_run_id=$1', first) == 2
            template = await request('POST', '/article-templates', json={'name': 'Journey template', 'html_source': '<article><h1>{{ title }}</h1>{{ article_body }}</article>'})
            version = template['versions'][0]['id']
            topic_key = str(await db.fetchval('SELECT topic_id FROM topic_revisions WHERE id=$1', topics[0]['id']))
            job = await request('POST', '/article-generation-jobs', json={'taxonomy_type': 'topic', 'taxonomy_key': topic_key, 'template_version_id': version})
            async def generated():
                row = await request('GET', f"/article-generation-jobs/{job['id']}")
                assert row['status'] != 'failed', row
                return row if row['status'] == 'completed' else None
            result = await wait_for('zero-theme generation', generated)
            article = result['resulting_article_id']
            assert await db.fetchval('SELECT taxonomy_run_id FROM article_generation_jobs WHERE id=$1', job['id']) == first
            draft = await request('GET', f'/articles/{article}')
            assert draft['status'] == 'ready_for_review' and draft['theme_ids'] == []
            assert await db.fetchval('SELECT count(*) FROM article_evidence WHERE taxonomy_run_id=$1', first) == 6
            assert (await edge.get('/insights')).status_code == 200
            assert 'Community transport insight' not in (await edge.get('/insights')).text
            assert await db.fetchval('SELECT count(*) FROM article_publications') == 0
            approved = await request('POST', f'/articles/{article}/approve', json={})
            slug = await db.fetchval('SELECT slug FROM article_publications WHERE article_id=$1', article)
            approved_html = (await edge.get(f'/insights/{slug}')).text
            assert 'Community transport insight' in approved_html
            for path in ('/api/inputs', f'/articles/{article}', f'/taxonomy-runs/{first}', '/operations/summary', '/inputs', '/article-generation-jobs'):
                assert (await edge.get(path)).status_code == 404, path
            assert 'SPAM' not in approved_html and 'generation_metadata' not in approved_html
            await mode('full')
            await add(FREQUENT, 100)
            second = await terminal(first)
            await verify(second, partial=False, themes=1, count=13)
            assert (await edge.get(f'/insights/{slug}')).text == approved_html
            assert await request('GET', f'/articles/{article}') == approved
            second_inputs = await inputs()
            await mode('failed')
            await add(FREQUENT, 101)
            failed = await terminal(second, status='ready_for_review')
            assert await db.fetchval('SELECT gate_passed FROM taxonomy_release_attestations WHERE taxonomy_run_id=$1', failed) is False
            current = await inputs()
            assert all(row['published_taxonomy_run_id'] == second for row in current)
            by_id = {row['id']: row for row in current}
            assert all(by_id[row['id']] == row for row in second_inputs)
            # Unchanged failed evidence must not make a new candidate loop.
            await asyncio.sleep(4)
            assert await db.fetchval('SELECT max(id) FROM taxonomy_runs') == failed
            for _ in range(2):
                await db.execute("SELECT rollback_taxonomy_run($1,'journey','PTR8 explicit recovery')", first)
                restored = {row['id']: row for row in await inputs()}
                assert all(restored[row['id']] == row for row in first_inputs)
            assert await db.fetchval('SELECT count(*) FROM taxonomy_rollback_decisions') == 1
            assert (await edge.get(f'/insights/{slug}')).text == approved_html
            print(json.dumps({'result': 'PASS', 'partial_run': first, 'full_run': second, 'failed_run': failed,
                              'article_id': article, 'migration_markers': await db.fetchval('SELECT count(*) FROM schema_migrations')}, sort_keys=True))
        finally:
            await db.close()
            await pool.close()


if __name__ == '__main__':
    asyncio.run(main())
