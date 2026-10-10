"""PTR-3 canonical partition, lineage and lease boundaries on disposable pgvector."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import asyncpg
import httpx

from triage_processor.clients.llm import StructuredChatClient
from triage_processor.taxonomy_topic_reconciliation import reconcile_topics_run, MAX_MODEL_ATTEMPTS
from triage_processor.taxonomy_stages import ClaimedStage, claim_next_stage, complete_stage, STAGES

DSN = os.environ.get("TRIAGE_TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[3] / "infrastructure/postgres"
if not ROOT.exists():
    ROOT = Path("/infrastructure/postgres")


def snapshot_sql(path):
    return "\n".join(snapshot_sql(path.parent / line[4:].strip()) if line.startswith("\\ir ") else line
                     for line in path.read_text().splitlines())


@unittest.skipUnless(DSN, "Set TRIAGE_TEST_DATABASE_URL or use compose.test.yaml")
class TopicReconciliationPostgresTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.schema = "ptr3_" + uuid4().hex
        self.db = await asyncpg.connect(DSN)
        self.addAsyncCleanup(self.db.close)
        await self.db.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
        await self.db.execute("DROP SCHEMA IF EXISTS taxonomy_legacy_archive CASCADE")
        await self.db.execute(f'CREATE SCHEMA "{self.schema}"')
        self.addAsyncCleanup(self.db.execute, f'DROP SCHEMA "{self.schema}" CASCADE')
        await self.db.execute(f'SET search_path TO "{self.schema}", public')
        await self.db.execute(snapshot_sql(ROOT / "init.sql"))
        self.pool = await asyncpg.create_pool(DSN, min_size=1, max_size=5,
            server_settings={"search_path": f'"{self.schema}", public'})
        self.addAsyncCleanup(self.pool.close)
        self.run = await self.new_run()
        self.ids = []
        self.evidence = []
        self.sources = []
        for index, name in enumerate(("Access fees", "Service charges")):
            question = await self.db.fetchval("""INSERT INTO questions(source,form_key,question_key,question_text)
                VALUES('ptr3','survey',$1,'What prevents access?') RETURNING id""", str(index))
            source_ids = []
            for respondent in range(2):
                input_id = await self.db.fetchval("""INSERT INTO original_inputs(
                    original_text,source,status,question_id,submission_key)
                    VALUES($1,'ptr3','ineligible',$2,$3) RETURNING id""",
                    f"{name} prevent participation", question, f"respondent:{respondent}")
                embedding = await self.db.fetchval("""INSERT INTO input_embeddings(
                    original_input_id,embedding,embedding_model,embedding_representation)
                    VALUES($1,'[1,0]'::vector,'fixture','question-answer') RETURNING id""", input_id)
                source_ids.append((input_id, embedding))
            self.sources.append((question, source_ids))
            identifier, evidence = await self.provisional(self.run, index, question, name, source_ids)
            self.ids.append(identifier)
            self.evidence.extend(evidence)

    async def new_run(self):
        return await self.db.fetchval("""INSERT INTO taxonomy_runs(source_cutoff,source_snapshot_sha256,
            configuration,configuration_sha256,embedding_model,embedding_representation,embedding_dimension,
            clustering_model,topic_model,theme_model,topic_prompt_version,theme_prompt_version)
            VALUES(CURRENT_TIMESTAMP,repeat('a',64),'{"cluster_policy_version":"partial-topic-policy/v1"}',
            repeat('b',64),'fixture','question-answer',2,'fixture','fixture','fixture',
            'partial-topic-naming/v1','fixture') RETURNING id""")

    async def provisional(self, run, index, question, name, sources, *, audited=False):
        evidence = []
        # PTR-7 also freezes segments; existing two-item original tuples remain valid.
        for source in sources:
            input_id, embedding = source[:2]
            segment = source[2] if len(source) == 3 else None
            evidence.append(await self.db.fetchval("""INSERT INTO taxonomy_run_evidence(
                taxonomy_run_id,original_input_id,embedding_id,segment_input_id)
                VALUES($1,$2,$3,$4) RETURNING id""", run, input_id, embedding, segment))
        cluster = await self.db.fetchval("""INSERT INTO taxonomy_cluster_candidates(
            taxonomy_run_id,cluster_key,question_id,algorithm_label,member_count,centroid,
            diagnostics,policy_version,eligible,failure_reasons,packet_serialized_bytes,unique_original_count)
            VALUES($1,$2,$3,$4,$5,'[1,0]'::vector,'{}','partial-topic-policy/v1',TRUE,'{}',256,$6)
            RETURNING id""", run, f"question:{question}:cluster:{index}", question, index,
            len(sources), len({source[0] for source in sources}))
        for order, identifier in enumerate(evidence):
            await self.db.execute("""INSERT INTO taxonomy_cluster_memberships(
                taxonomy_run_id,cluster_candidate_id,evidence_id,membership_confidence,decision)
                VALUES($1,$2,$3,1,'clustered')""", run, cluster, identifier)
            await self.db.execute("""INSERT INTO taxonomy_cluster_representatives(
                taxonomy_run_id,cluster_candidate_id,evidence_id,representative_order,selection_kind)
                VALUES($1,$2,$3,$4,'all')""", run, cluster, identifier, order)
        response = {"name": name, "description": "The cost of access.", "evidence_ids": evidence} if audited else {}
        context = {"cluster_key": f"question:{question}:cluster:{index}"} if audited else {}
        attempt = await self.db.fetchval("""INSERT INTO taxonomy_topic_naming_attempts(
            taxonomy_run_id,cluster_candidate_id,attempt_number,model,prompt_version,prompt_sha256,
            request_context,raw_response,accepted) VALUES($1,$2,1,'fixture','partial-topic-naming/v1',
            repeat('c',64),$3::jsonb,$4::jsonb,TRUE) RETURNING id""", run, cluster,
            json.dumps(context), json.dumps(response))
        if audited:
            request = await self.db.fetchval("""INSERT INTO taxonomy_model_requests(taxonomy_run_id,stage,
                request_key,model,prompt_version,prompt_sha256,request_context,request_sha256)
                VALUES($1,'topic_naming',$2,'fixture','partial-topic-naming/v1',repeat('c',64),$3::jsonb,repeat('d',64))
                RETURNING id""", run, f"cluster:{cluster}", json.dumps(context))
            await self.db.execute("""INSERT INTO taxonomy_model_responses(taxonomy_run_id,taxonomy_model_request_id,
                raw_response,accepted) VALUES($1,$2,$3::jsonb,TRUE)""", run, request, json.dumps(response))
        identifier = await self.db.fetchval("""INSERT INTO taxonomy_provisional_topics(
            taxonomy_run_id,cluster_candidate_id,naming_attempt_id,name,normalized_name,description)
            VALUES($1,$2,$3,$4,lower($4),'The cost of access.') RETURNING id""", run, cluster, attempt, name)
        return identifier, evidence

    def merged(self, ids=None):
        return {"groups": [{"provisional_topic_ids": ids or self.ids, "name": "Access costs",
            "description": "The cost of participating.", "rationale": "Both describe the same access cost."}],
            "no_merge_topic_ids": []}

    async def reconcile(self, run=None, stage=None):
        return await reconcile_topics_run(self.pool, run_id=run or self.run,
            base_url="http://fixture", model="fixture", stage=stage)

    async def assert_no_partition(self):
        for table in ("topic_revisions", "topic_memberships", "taxonomy_canonical_topic_antecedents", "topic_lineage"):
            self.assertEqual(await self.db.fetchval(f"SELECT count(*) FROM {table} WHERE taxonomy_run_id=$1", self.run), 0)
        self.assertEqual(await self.db.fetchval("SELECT count(*) FROM topics"), 0)

    async def running_stage(self):
        identifier = await self.db.fetchval("""INSERT INTO taxonomy_run_stages(
            taxonomy_run_id,stage,attempt,status,lease_owner,lease_expires_at,heartbeat_at)
            VALUES($1,'topic_reconciliation',1,'running','old',CURRENT_TIMESTAMP+INTERVAL '5 minutes',
            CURRENT_TIMESTAMP) RETURNING id""", self.run)
        return ClaimedStage(identifier, self.run, "topic_reconciliation", 1, "old")

    async def test_exact_union_counts_provenance_and_immutable_replay(self):
        with patch("triage_processor.clients.llm.StructuredChatClient.complete", new=AsyncMock(return_value=self.merged())) as client:
            self.assertEqual(await self.reconcile(), (tuple(self.ids),))
            self.assertEqual(await self.reconcile(), (tuple(self.ids),))
        self.assertEqual(client.await_count, 1)
        memberships = await self.db.fetch("SELECT evidence_id FROM topic_memberships WHERE taxonomy_run_id=$1 ORDER BY evidence_id", self.run)
        self.assertEqual([row[0] for row in memberships], self.evidence)
        counts = await self.db.fetchrow("""SELECT count(*) AS evidence,
            count(DISTINCT q.id) AS questions,
            count(DISTINCT (i.source,q.form_key,i.submission_key)) AS submissions
            FROM topic_memberships m JOIN taxonomy_run_evidence e ON e.id=m.evidence_id
            JOIN original_inputs i ON i.id=e.original_input_id JOIN questions q ON q.id=i.question_id
            WHERE m.taxonomy_run_id=$1""", self.run)
        self.assertEqual(tuple(counts), (4, 2, 2))
        self.assertEqual(await self.db.fetchval("SELECT support_count FROM topic_revisions WHERE taxonomy_run_id=$1", self.run), 4)
        for table, assignment in (("taxonomy_topic_reconciliation_decisions", "accepted=FALSE"),
            ("taxonomy_canonical_topic_antecedents", "relationship='singleton'")):
            with self.assertRaisesRegex(asyncpg.PostgresError, "immutable"):
                await self.db.execute(f"UPDATE {table} SET {assignment} WHERE taxonomy_run_id=$1", self.run)
        other = await self.new_run()
        _, foreign = await self.provisional(other, 0, *self.sources[0][:1], "Other cost", self.sources[0][1])
        revision = await self.db.fetchval("SELECT id FROM topic_revisions WHERE taxonomy_run_id=$1", self.run)
        with self.assertRaises(asyncpg.PostgresError):
            await self.db.execute("INSERT INTO topic_memberships(taxonomy_run_id,topic_revision_id,evidence_id) VALUES($1,$2,$3)", self.run, revision, foreign[0])
        audit = await self.db.fetchrow("""SELECT r.prompt_version,r.request_context,d.decision
            FROM taxonomy_topic_reconciliation_decisions d JOIN taxonomy_model_requests r
            ON r.id=d.taxonomy_model_request_id WHERE d.taxonomy_run_id=$1""", self.run)
        self.assertEqual(audit["prompt_version"], "cross-question-topic-reconciliation/v1")
        self.assertEqual(len(json.loads(audit["request_context"])["topics"]), 2)
        self.assertEqual(json.loads(audit["decision"]), self.merged())

    async def test_isolated_topic_bypasses_model_and_has_durable_provenance(self):
        run = await self.new_run()
        question, sources = self.sources[0]
        identifier, evidence = await self.provisional(run, 0, question, "Access costs", sources)
        with patch("triage_processor.clients.llm.StructuredChatClient.complete", new=AsyncMock()) as client:
            self.assertEqual(await self.reconcile(run), ((identifier,),))
        client.assert_not_awaited()
        self.assertEqual(await self.db.fetchval("SELECT count(*) FROM taxonomy_model_requests WHERE taxonomy_run_id=$1", run), 0)
        self.assertEqual(await self.db.fetchval("SELECT decision_kind FROM taxonomy_topic_reconciliation_decisions WHERE taxonomy_run_id=$1", run), "isolated")
        self.assertEqual(await self.db.fetchval("SELECT support_count FROM topic_revisions WHERE taxonomy_run_id=$1", run), len(evidence))

    async def test_same_run_evidence_without_an_antecedent_cannot_join_topic(self):
        with patch("triage_processor.clients.llm.StructuredChatClient.complete", new=AsyncMock(return_value=self.merged())):
            await self.reconcile()
        question = self.sources[0][0]
        source = await self.db.fetchval("""INSERT INTO original_inputs(original_text,source,status,question_id)
            VALUES('Unlinked evidence','ptr3','ineligible',$1) RETURNING id""", question)
        embedding = await self.db.fetchval("""INSERT INTO input_embeddings(original_input_id,embedding,
            embedding_model,embedding_representation) VALUES($1,'[1,0]','fixture','question-answer') RETURNING id""", source)
        evidence = await self.db.fetchval("""INSERT INTO taxonomy_run_evidence(taxonomy_run_id,original_input_id,
            embedding_id) VALUES($1,$2,$3) RETURNING id""", self.run, source, embedding)
        revision = await self.db.fetchval("SELECT id FROM topic_revisions WHERE taxonomy_run_id=$1", self.run)
        with self.assertRaisesRegex(asyncpg.PostgresError, "antecedent cluster membership"):
            await self.db.execute("INSERT INTO topic_memberships(taxonomy_run_id,topic_revision_id,evidence_id) VALUES($1,$2,$3)", self.run, revision, evidence)
        self.assertEqual(await self.db.fetchval("SELECT count(*) FROM topic_memberships WHERE taxonomy_run_id=$1", self.run), 4)

    async def test_invalid_groups_leave_no_canonical_writes(self):
        invalid = [
            {"groups": [], "no_merge_topic_ids": self.ids + [999]},
            {"groups": [], "no_merge_topic_ids": self.ids[:1]},
            {"groups": [], "no_merge_topic_ids": self.ids + self.ids},
            {**self.merged(), "no_merge_topic_ids": [self.ids[0]]},
        ]
        for response in invalid:
            run = await self.new_run()
            ids = []
            for index, (question, sources) in enumerate(self.sources):
                identifier, _ = await self.provisional(run, index, question, f"Name {index}", sources)
                ids.append(identifier)
            mapping = dict(zip(self.ids, ids))
            response = json.loads(json.dumps(response))
            response["no_merge_topic_ids"] = [mapping.get(i, i) for i in response["no_merge_topic_ids"]]
            for group in response["groups"]:
                group["provisional_topic_ids"] = [mapping.get(i, i) for i in group["provisional_topic_ids"]]
            with patch("triage_processor.clients.llm.StructuredChatClient.complete", new=AsyncMock(return_value=response)):
                with self.assertRaisesRegex(ValueError, "invalid topic reconciliation"):
                    await self.reconcile(run)
            self.assertEqual(await self.db.fetchval("SELECT count(*) FROM topic_revisions WHERE taxonomy_run_id=$1", run), 0)
            self.assertFalse(await self.db.fetchval("SELECT accepted FROM taxonomy_topic_reconciliation_decisions WHERE taxonomy_run_id=$1", run))
        await self.assert_no_partition()

    async def test_structured_client_rubric_fixtures_preserve_distinctions(self):
        run = await self.new_run()
        names = ("Childcare fees", "Nursery prices", "Bus reliability", "Bus fares",
                 "River bank erosion", "Bank account fees", "Support parking charges", "Oppose parking charges")
        ids = []
        for index, name in enumerate(names):
            question = await self.db.fetchval("""INSERT INTO questions(source,form_key,question_key,question_text)
                VALUES('rubric','survey',$1,$2) RETURNING id""", str(index), f"What do you think about {name}?")
            sources = []
            for respondent in range(2):
                source = await self.db.fetchval("""INSERT INTO original_inputs(original_text,source,status,question_id)
                    VALUES($1,'rubric','ineligible',$2) RETURNING id""", name, question)
                embedding = await self.db.fetchval("""INSERT INTO input_embeddings(original_input_id,embedding,
                    embedding_model,embedding_representation) VALUES($1,'[1,0]','fixture','question-answer')
                    RETURNING id""", source)
                sources.append((source, embedding))
            identifier, _ = await self.provisional(run, index, question, name, sources)
            ids.append(identifier)
        response = {"groups": [
            {"provisional_topic_ids": ids[:2], "name": "Childcare costs", "description": "The cost of childcare.",
             "rationale": "Equivalent service cost expressed with different wording."},
            {"provisional_topic_ids": ids[6:], "name": "Parking charges", "description": "Views on parking charges.",
             "rationale": "Opposing positions on the same concept retain their evidence."}],
            "no_merge_topic_ids": ids[2:6]}
        calls = []
        def transport(request):
            payload = json.loads(request.content)
            calls.append(payload)
            packet = json.loads(payload["messages"][1]["content"])
            self.assertLessEqual(len(payload["messages"][1]["content"].encode()), 32768)
            self.assertEqual([item["id"] for item in packet["topics"]], ids)
            self.assertTrue(all(len(item["evidence"]) == 2 for item in packet["topics"]))
            self.assertIn("different meanings", payload["messages"][0]["content"])
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(response)}}]})
        client = StructuredChatClient(base_url="http://fixture", model="fixture",
                                      transport=httpx.MockTransport(transport))
        with patch("triage_processor.taxonomy_topic_reconciliation.StructuredChatClient", return_value=client):
            partition = await self.reconcile(run)
        self.assertEqual(partition, (tuple(ids[:2]), *(tuple([i]) for i in ids[2:6]), tuple(ids[6:])))
        self.assertEqual(len(calls), 1)
        self.assertEqual(await self.db.fetchval("SELECT count(*) FROM topic_memberships WHERE taxonomy_run_id=$1", run), 16)

    async def test_late_membership_failure_rolls_back_the_entire_partition(self):
        await self.db.execute("""CREATE FUNCTION ptr3_injected_failure() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF NEW.evidence_id = 4 THEN RAISE EXCEPTION 'injected persistence failure'; END IF;
            RETURN NEW; END; $$;
            CREATE TRIGGER ptr3_injected_failure BEFORE INSERT ON topic_memberships
            FOR EACH ROW EXECUTE FUNCTION ptr3_injected_failure();""")
        with patch("triage_processor.clients.llm.StructuredChatClient.complete", new=AsyncMock(return_value=self.merged())) as client:
            with self.assertRaisesRegex(asyncpg.PostgresError, "injected persistence failure"):
                await self.reconcile()
            await self.assert_no_partition()
            await self.db.execute("DROP TRIGGER ptr3_injected_failure ON topic_memberships")
            await self.reconcile()
        self.assertEqual(client.await_count, 1)

    async def test_label_collisions_write_nothing(self):
        run = await self.new_run()
        ids = []
        for index, (question, sources) in enumerate(self.sources):
            identifier, _ = await self.provisional(run, index, question,
                "Shared concept" if index == 0 else "Shared  concept", sources)
            ids.append(identifier)
        with patch("triage_processor.clients.llm.StructuredChatClient.complete",
                   new=AsyncMock(return_value={"groups": [], "no_merge_topic_ids": ids})):
            with self.assertRaisesRegex(ValueError, "names collide"):
                await self.reconcile(run)
        self.assertEqual(await self.db.fetchval("SELECT count(*) FROM topic_revisions WHERE taxonomy_run_id=$1", run), 0)
        self.assertEqual(await self.db.fetchval("SELECT count(*) FROM topics"), 0)

    async def test_transitive_contradictions_write_nothing(self):
        run = await self.new_run()
        ids = []
        for index in range(3):
            if index < 2:
                question, sources = self.sources[index]
            else:
                question = await self.db.fetchval("""INSERT INTO questions(source,form_key,question_key,question_text)
                    VALUES('ptr3','survey','third','What else prevents access?') RETURNING id""")
                sources = []
                for respondent in range(2):
                    source = await self.db.fetchval("""INSERT INTO original_inputs(original_text,source,status,question_id)
                        VALUES('Access costs','ptr3','ineligible',$1) RETURNING id""", question)
                    embedding = await self.db.fetchval("""INSERT INTO input_embeddings(original_input_id,embedding,
                        embedding_model,embedding_representation) VALUES($1,'[1,0]','fixture','question-answer')
                        RETURNING id""", source)
                    sources.append((source, embedding))
            identifier, _ = await self.provisional(run, index, question, f"Concept {index}", sources)
            ids.append(identifier)
        packets = ((ids[0], ids[1]), (ids[1], ids[2]), (ids[0], ids[2]))
        responses = [self.merged(list(packets[0])), self.merged(list(packets[1])),
                     {"groups": [], "no_merge_topic_ids": list(packets[2])}]
        with patch("triage_processor.taxonomy_topic_reconciliation.shortlist_packets", return_value=packets), patch(
                "triage_processor.clients.llm.StructuredChatClient.complete", new=AsyncMock(side_effect=responses)):
            with self.assertRaisesRegex(ValueError, "transitive"):
                await self.reconcile(run)
        self.assertEqual(await self.db.fetchval("SELECT count(*) FROM topic_revisions WHERE taxonomy_run_id=$1", run), 0)
        self.assertEqual(await self.db.fetchval("SELECT count(*) FROM taxonomy_canonical_topic_antecedents WHERE taxonomy_run_id=$1", run), 0)
        self.assertEqual(await self.db.fetchval("SELECT count(*) FROM topics"), 0)

    async def test_fifty_question_scopes_materialize_one_complete_partition(self):
        run = await self.new_run()
        ids = []
        for index in range(50):
            question = await self.db.fetchval("""INSERT INTO questions(source,form_key,question_key,question_text)
                VALUES('scale','survey',$1,'What matters?') RETURNING id""", str(index))
            sources = []
            for respondent in range(2):
                source = await self.db.fetchval("""INSERT INTO original_inputs(original_text,source,status,question_id)
                    VALUES('Shared access cost','scale','ineligible',$1) RETURNING id""", question)
                embedding = await self.db.fetchval("""INSERT INTO input_embeddings(original_input_id,embedding,
                    embedding_model,embedding_representation) VALUES($1,'[1,0]','fixture','question-answer')
                    RETURNING id""", source)
                sources.append((source, embedding))
            identifier, _ = await self.provisional(run, index, question, f"Access cost {index}", sources)
            ids.append(identifier)
        async def merge_packet(**kwargs):
            packet_ids = [item["id"] for item in json.loads(kwargs["user_content"])["topics"]]
            self.assertLessEqual(len(packet_ids), 12)
            return self.merged(packet_ids)
        with patch("triage_processor.clients.llm.StructuredChatClient.complete", new=AsyncMock(side_effect=merge_packet)) as client:
            self.assertEqual(await self.reconcile(run), (tuple(ids),))
            self.assertEqual(await self.reconcile(run), (tuple(ids),))
        self.assertLessEqual(client.await_count, 50)
        self.assertEqual(await self.db.fetchval("SELECT count(*) FROM taxonomy_canonical_topic_antecedents WHERE taxonomy_run_id=$1", run), 50)
        self.assertEqual(await self.db.fetchval("SELECT support_count FROM topic_revisions WHERE taxonomy_run_id=$1", run), 100)

    async def test_transport_failure_retries_with_preserved_audit_and_bound(self):
        with patch("triage_processor.clients.llm.StructuredChatClient.complete", new=AsyncMock(side_effect=[OSError("private"), self.merged()])):
            with self.assertRaises(OSError):
                await self.reconcile()
            await self.reconcile()
        self.assertEqual(await self.db.fetchval("SELECT count(*) FROM taxonomy_model_responses WHERE taxonomy_run_id=$1", self.run), 2)
        raw = await self.db.fetchval("SELECT raw_response FROM taxonomy_model_responses WHERE taxonomy_run_id=$1 AND NOT accepted", self.run)
        self.assertNotIn("private", raw)
        run = await self.new_run()
        for index, (question, sources) in enumerate(self.sources):
            await self.provisional(run, index, question, f"Costs {index}", sources)
        with patch("triage_processor.clients.llm.StructuredChatClient.complete", new=AsyncMock(side_effect=OSError())) as client:
            for _ in range(MAX_MODEL_ATTEMPTS):
                with self.assertRaises(OSError):
                    await self.reconcile(run)
            with self.assertRaisesRegex(ValueError, "exhausted"):
                await self.reconcile(run)
        self.assertEqual(client.await_count, MAX_MODEL_ATTEMPTS)

    async def test_crash_after_decision_resumes_without_another_model_call(self):
        with patch("triage_processor.clients.llm.StructuredChatClient.complete", new=AsyncMock(return_value=self.merged())) as client:
            with patch("triage_processor.taxonomy_topic_reconciliation._materialize_partition", new=AsyncMock(side_effect=RuntimeError("crash"))):
                with self.assertRaisesRegex(RuntimeError, "crash"):
                    await self.reconcile()
            await self.assert_no_partition()
            await self.reconcile()
        self.assertEqual(client.await_count, 1)

    async def test_stale_lease_saves_nothing_and_model_call_holds_no_lock(self):
        stage = await self.running_stage()
        started, release = asyncio.Event(), asyncio.Event()
        async def response(**_):
            started.set()
            await release.wait()
            return self.merged()
        with patch("triage_processor.clients.llm.StructuredChatClient.complete", new=AsyncMock(side_effect=response)):
            task = asyncio.create_task(self.reconcile(stage=stage))
            await asyncio.wait_for(started.wait(), 5)
            async with self.pool.acquire() as connection:
                async with connection.transaction():
                    await connection.fetchval("SELECT id FROM taxonomy_runs WHERE id=$1 FOR UPDATE NOWAIT", self.run)
            await self.db.execute("UPDATE taxonomy_run_stages SET lease_owner='new' WHERE id=$1", stage.id)
            release.set()
            with self.assertRaisesRegex(RuntimeError, "lease is no longer owned"):
                await task
        await self.assert_no_partition()
        self.assertEqual(await self.db.fetchval("SELECT count(*) FROM taxonomy_model_responses WHERE taxonomy_run_id=$1", self.run), 0)
        self.assertEqual(await self.db.fetchval("SELECT count(*) FROM taxonomy_topic_reconciliation_decisions WHERE taxonomy_run_id=$1", self.run), 0)

    async def test_concurrent_workers_create_one_partition_and_identity(self):
        started, release = asyncio.Event(), asyncio.Event()
        calls = 0
        async def response(**_):
            nonlocal calls
            calls += 1
            if calls == 2:
                started.set()
            await release.wait()
            return self.merged()
        with patch("triage_processor.clients.llm.StructuredChatClient.complete", new=AsyncMock(side_effect=response)):
            tasks = [asyncio.create_task(self.reconcile()) for _ in range(2)]
            await asyncio.wait_for(started.wait(), 5)
            release.set()
            results = await asyncio.gather(*tasks)
        self.assertEqual(results, [(tuple(self.ids),)] * 2)
        for table in ("topics", "topic_revisions", "taxonomy_topic_reconciliation_decisions", "taxonomy_model_responses"):
            self.assertEqual(await self.db.fetchval(f"SELECT count(*) FROM {table}"), 1)

    async def test_losing_invalid_response_uses_committed_winner(self):
        winner_started, loser_started, release_loser = (
            asyncio.Event(), asyncio.Event(), asyncio.Event()
        )
        calls = 0

        async def response(**_):
            nonlocal calls
            calls += 1
            if calls == 1:
                winner_started.set()
                await loser_started.wait()
                return self.merged()
            loser_started.set()
            await release_loser.wait()
            return {"groups": [], "no_merge_topic_ids": []}

        with patch("triage_processor.clients.llm.StructuredChatClient.complete",
                   new=AsyncMock(side_effect=response)):
            winner = asyncio.create_task(self.reconcile())
            await asyncio.wait_for(winner_started.wait(), 5)
            loser = asyncio.create_task(self.reconcile())
            try:
                self.assertEqual(await asyncio.wait_for(winner, 5), (tuple(self.ids),))
            finally:
                release_loser.set()
            self.assertEqual(await asyncio.wait_for(loser, 5), (tuple(self.ids),))
        self.assertEqual(await self.db.fetchval(
            "SELECT count(*) FROM taxonomy_topic_reconciliation_decisions"), 1)
        self.assertTrue(await self.db.fetchval(
            "SELECT accepted FROM taxonomy_topic_reconciliation_decisions"))

    async def test_stage_order_replay_and_successor_claim(self):
        await self.db.execute("INSERT INTO taxonomy_run_jobs(taxonomy_run_id) VALUES($1)", self.run)
        for stage in STAGES:
            completed = stage in STAGES[:STAGES.index("topic_reconciliation")]
            await self.db.execute("""INSERT INTO taxonomy_run_stages(taxonomy_run_id,stage,attempt,status,completed_at,stage_output_sha256)
                VALUES($1,$2,$3,$4,CASE WHEN $5 THEN CURRENT_TIMESTAMP END,CASE WHEN $5 THEN repeat('a',64) END)""",
                self.run, stage, 1 if completed else 0, "completed" if completed else "pending", completed)
        self.assertIsNone(await claim_next_stage(self.pool, lease_owner="theme", lease_seconds=60, allowed_stages=("theme_inference",)))
        stage = await claim_next_stage(self.pool, lease_owner="reconciler", lease_seconds=60)
        self.assertEqual(stage.stage, "topic_reconciliation")
        with patch("triage_processor.clients.llm.StructuredChatClient.complete", new=AsyncMock(return_value=self.merged())):
            await self.reconcile(stage=stage)
            await self.reconcile(stage=stage)
        self.assertTrue(await complete_stage(self.pool, stage, output_material="partition"))
        successor = await claim_next_stage(self.pool, lease_owner="theme", lease_seconds=60)
        self.assertEqual(successor.stage, "theme_inference")

    async def publish_fixture(self, run):
        # Lineage tests select a prior publication without exercising PTR-5's
        # release gate. Use the legal run state shape, keeping child rows intact.
        await self.db.execute("UPDATE taxonomy_runs SET status='running',started_at=CURRENT_TIMESTAMP WHERE id=$1", run)
        await self.db.execute("UPDATE taxonomy_runs SET status='ready_for_review',completed_at=CURRENT_TIMESTAMP WHERE id=$1", run)
        async with self.db.transaction():
            await self.db.execute("SELECT set_config('taxonomy.automatic_publish','on',true)")
            await self.db.execute("UPDATE taxonomy_runs SET status='superseded' WHERE status='published'")
            await self.db.execute("""UPDATE taxonomy_runs SET status='published',
                published_at=CURRENT_TIMESTAMP,decision_by='fixture',decision_at=CURRENT_TIMESTAMP WHERE id=$1""", run)

    async def test_replacement_stable_identity_split_merge_rename_new_and_history(self):
        with patch("triage_processor.clients.llm.StructuredChatClient.complete", new=AsyncMock(return_value=self.merged())):
            await self.reconcile()
        first = await self.db.fetchrow("SELECT * FROM topic_revisions WHERE taxonomy_run_id=$1", self.run)
        await self.publish_fixture(self.run)
        replacement = await self.new_run()
        ids = []
        for index, (question, sources) in enumerate(self.sources):
            identifier, _ = await self.provisional(replacement, index, question, f"Separate {index}", sources)
            ids.append(identifier)
        with patch("triage_processor.clients.llm.StructuredChatClient.complete", new=AsyncMock(return_value={"groups": [], "no_merge_topic_ids": ids})):
            await self.reconcile(replacement)
        split_rows = await self.db.fetch("SELECT topic_id FROM topic_revisions WHERE taxonomy_run_id=$1 ORDER BY id", replacement)
        self.assertIn(first["topic_id"], [row[0] for row in split_rows])
        self.assertEqual(await self.db.fetchval("SELECT count(*) FROM topic_lineage WHERE taxonomy_run_id=$1 AND relationship='split'", replacement), 2)
        await self.publish_fixture(replacement)
        merged = await self.new_run()
        ids = []
        for index, (question, sources) in enumerate(self.sources):
            identifier, _ = await self.provisional(merged, index, question, f"Costs {index}", sources)
            ids.append(identifier)
        with patch("triage_processor.clients.llm.StructuredChatClient.complete", new=AsyncMock(return_value=self.merged(ids))):
            await self.reconcile(merged)
        self.assertEqual(await self.db.fetchval("SELECT count(*) FROM topic_lineage WHERE taxonomy_run_id=$1 AND relationship='merge'", merged), 2)
        await self.publish_fixture(merged)
        renamed = await self.new_run()
        ids = []
        for index, (question, sources) in enumerate(self.sources):
            identifier, _ = await self.provisional(renamed, index, question, f"Costs {index}", sources)
            ids.append(identifier)
        response = self.merged(ids)
        response["groups"][0]["name"] = "Participation costs"
        with patch("triage_processor.clients.llm.StructuredChatClient.complete", new=AsyncMock(return_value=response)):
            await self.reconcile(renamed)
        self.assertEqual(await self.db.fetchval("SELECT relationship FROM topic_lineage WHERE taxonomy_run_id=$1", renamed), "rename")
        self.assertEqual(await self.db.fetchrow("SELECT * FROM topic_revisions WHERE taxonomy_run_id=$1", self.run), first)
        await self.publish_fixture(renamed)
        continued = await self.new_run()
        ids = []
        for index, (question, sources) in enumerate(self.sources):
            identifier, _ = await self.provisional(continued, index, question, f"Costs {index}", sources)
            ids.append(identifier)
        response["groups"][0]["provisional_topic_ids"] = ids
        with patch("triage_processor.clients.llm.StructuredChatClient.complete", new=AsyncMock(return_value=response)):
            await self.reconcile(continued)
        self.assertEqual(await self.db.fetchval("SELECT relationship FROM topic_lineage WHERE taxonomy_run_id=$1", continued), "continuation")
        self.assertEqual(await self.db.fetchval("SELECT relationship FROM topic_lineage WHERE taxonomy_run_id=$1", self.run), "new")
