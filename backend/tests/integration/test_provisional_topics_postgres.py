"""PTR-2 provisional naming boundaries against disposable PostgreSQL."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import asyncpg

from triage_processor.taxonomy_stages import ClaimedStage
from triage_processor.taxonomy_topics import PROMPT_VERSION, materialize_run


DSN = os.environ.get("TRIAGE_TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[3] / "infrastructure/postgres"
if not ROOT.exists():
    ROOT = Path("/infrastructure/postgres")


def snapshot_sql(path: Path) -> str:
    return "\n".join(
        snapshot_sql(path.parent / line[4:].strip()) if line.startswith("\\ir ") else line
        for line in path.read_text().splitlines()
    )


@unittest.skipUnless(DSN, "Set TRIAGE_TEST_DATABASE_URL or use compose.test.yaml")
class ProvisionalTopicsPostgresTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.schema = "ptr2_" + uuid4().hex
        self.admin = await asyncpg.connect(DSN)
        self.addAsyncCleanup(self.admin.close)
        await self.admin.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
        await self.admin.execute("DROP SCHEMA IF EXISTS taxonomy_legacy_archive CASCADE")
        await self.admin.execute(f'CREATE SCHEMA "{self.schema}"')
        self.addAsyncCleanup(self.admin.execute, f'DROP SCHEMA "{self.schema}" CASCADE')
        await self.admin.execute(f'SET search_path TO "{self.schema}", public')
        await self.admin.execute(snapshot_sql(ROOT / "init.sql"))
        self.pool = await asyncpg.create_pool(
            DSN,
            min_size=1,
            max_size=4,
            server_settings={"search_path": f'"{self.schema}", public'},
        )
        self.addAsyncCleanup(self.pool.close)
        self.run_id, self.cluster_id, self.evidence_ids = await self._seed_cluster()

    async def _seed_cluster(self):
        question_id = await self.admin.fetchval(
            """INSERT INTO questions(source,form_key,question_key,question_text)
               VALUES('ptr2',$1,'access','What makes access difficult?') RETURNING id""",
            uuid4().hex,
        )
        input_ids = []
        for answer in ("The fee is too high", "Charges keep people out"):
            input_ids.append(await self.admin.fetchval(
                """INSERT INTO original_inputs(original_text,source,status,question_id)
                   VALUES($1,'ptr2','ineligible',$2) RETURNING id""",
                answer,
                question_id,
            ))
        embedding_ids = []
        for index, input_id in enumerate(input_ids):
            embedding_ids.append(await self.admin.fetchval(
                """INSERT INTO input_embeddings(
                       original_input_id,embedding,embedding_model,embedding_representation
                   ) VALUES($1,$2::vector,'fixture','question-answer') RETURNING id""",
                input_id,
                "[1,0]" if index == 0 else "[0.99,0.01]",
            ))
        run_id = await self.admin.fetchval(
            """INSERT INTO taxonomy_runs(
                   source_cutoff,source_snapshot_sha256,configuration,configuration_sha256,
                   embedding_model,embedding_representation,embedding_dimension,
                   clustering_model,topic_model,theme_model,topic_prompt_version,theme_prompt_version
               ) VALUES(CURRENT_TIMESTAMP,repeat('a',64),
                   '{"cluster_policy_version":"partial-topic-policy/v1"}'::jsonb,
                   repeat('b',64),'fixture','question-answer',2,'fixture','fixture','fixture',$1,'fixture')
               RETURNING id""",
            PROMPT_VERSION,
        )
        evidence_ids = []
        for input_id, embedding_id in zip(input_ids, embedding_ids, strict=True):
            evidence_ids.append(await self.admin.fetchval(
                """INSERT INTO taxonomy_run_evidence(
                       taxonomy_run_id,original_input_id,embedding_id
                   ) VALUES($1,$2,$3) RETURNING id""",
                run_id,
                input_id,
                embedding_id,
            ))
        cluster_id = await self.admin.fetchval(
            """INSERT INTO taxonomy_cluster_candidates(
                   taxonomy_run_id,cluster_key,question_id,algorithm_label,member_count,
                   centroid,diagnostics,policy_version,eligible,failure_reasons,
                   packet_serialized_bytes,unique_original_count
               ) VALUES($1,'question:1:hdbscan:0',$2,0,2,'[1,0]'::vector,'{}'::jsonb,
                   'partial-topic-policy/v1',TRUE,ARRAY[]::text[],256,2) RETURNING id""",
            run_id,
            question_id,
        )
        for order, evidence_id in enumerate(evidence_ids):
            await self.admin.execute(
                """INSERT INTO taxonomy_cluster_memberships(
                       taxonomy_run_id,cluster_candidate_id,evidence_id,membership_confidence,decision
                   ) VALUES($1,$2,$3,1,'clustered')""",
                run_id,
                cluster_id,
                evidence_id,
            )
            await self.admin.execute(
                """INSERT INTO taxonomy_cluster_representatives(
                       taxonomy_run_id,cluster_candidate_id,evidence_id,representative_order,selection_kind
                   ) VALUES($1,$2,$3,$4,'all')""",
                run_id,
                cluster_id,
                evidence_id,
                order,
            )
        return run_id, cluster_id, tuple(evidence_ids)

    def _response(self):
        return {
            "name": "Access fees",
            "description": "Charges that limit access.",
            "evidence_ids": list(self.evidence_ids),
        }

    async def _running_stage(self, owner: str) -> ClaimedStage:
        row = await self.admin.fetchrow(
            """INSERT INTO taxonomy_run_stages(
                   taxonomy_run_id,stage,attempt,status,lease_owner,lease_expires_at,heartbeat_at
               ) VALUES($1,'topic_naming',1,'running',$2,CURRENT_TIMESTAMP + INTERVAL '5 minutes',CURRENT_TIMESTAMP)
               RETURNING id,taxonomy_run_id,stage,attempt,lease_owner""",
            self.run_id,
            owner,
        )
        return ClaimedStage(row["id"], row["taxonomy_run_id"], row["stage"], row["attempt"], row["lease_owner"])

    async def test_acceptance_is_provisional_immutable_auditable_and_replay_safe(self):
        with patch(
            "triage_processor.clients.llm.StructuredChatClient.complete",
            new=AsyncMock(return_value=self._response()),
        ) as complete:
            self.assertEqual(await materialize_run(
                self.pool, run_id=self.run_id, base_url="http://fixture", model="fixture", api_key=None
            ), 1)
            self.assertEqual(await materialize_run(
                self.pool, run_id=self.run_id, base_url="http://fixture", model="fixture", api_key=None
            ), 0)
        self.assertEqual(complete.await_count, 1)
        row = await self.admin.fetchrow(
            """SELECT provisional.name,attempt.accepted,attempt.validation_errors,
                      request.request_sha256,response.accepted AS response_accepted
               FROM taxonomy_provisional_topics provisional
               JOIN taxonomy_topic_naming_attempts attempt ON attempt.id=provisional.naming_attempt_id
               JOIN taxonomy_model_requests request
                 ON request.taxonomy_run_id=provisional.taxonomy_run_id
                AND request.stage='topic_naming'
               JOIN taxonomy_model_responses response
                 ON response.taxonomy_model_request_id=request.id
               WHERE provisional.taxonomy_run_id=$1""",
            self.run_id,
        )
        self.assertEqual(row["name"], "Access fees")
        self.assertTrue(row["accepted"])
        self.assertEqual(row["validation_errors"], [])
        self.assertEqual(len(row["request_sha256"]), 64)
        self.assertTrue(row["response_accepted"])
        self.assertEqual(await self.admin.fetchval(
            "SELECT count(*) FROM topic_revisions WHERE taxonomy_run_id=$1", self.run_id
        ), 0)
        with self.assertRaisesRegex(asyncpg.PostgresError, "immutable"):
            await self.admin.execute(
                "UPDATE taxonomy_provisional_topics SET description='changed' WHERE taxonomy_run_id=$1",
                self.run_id,
            )

    async def test_invalid_shape_retries_twice_and_keeps_both_rejections(self):
        invalid = {"name": "", "description": "", "evidence_ids": list(self.evidence_ids)}
        with patch(
            "triage_processor.clients.llm.StructuredChatClient.complete",
            new=AsyncMock(return_value=invalid),
        ) as complete:
            self.assertEqual(await materialize_run(
                self.pool, run_id=self.run_id, base_url="http://fixture", model="fixture", api_key=None
            ), 0)
        self.assertEqual(complete.await_count, 2)
        rows = await self.admin.fetch(
            """SELECT attempt_number,accepted,validation_errors
               FROM taxonomy_topic_naming_attempts WHERE taxonomy_run_id=$1 ORDER BY attempt_number""",
            self.run_id,
        )
        self.assertEqual([row["attempt_number"] for row in rows], [1, 2])
        self.assertTrue(all(not row["accepted"] for row in rows))
        self.assertTrue(all("name_blank" in row["validation_errors"] for row in rows))
        self.assertEqual(await self.admin.fetchval(
            "SELECT count(*) FROM taxonomy_provisional_topics WHERE taxonomy_run_id=$1", self.run_id
        ), 0)

    async def test_model_call_holds_no_run_lock_and_stale_stage_cannot_save(self):
        stage = await self._running_stage("old-owner")
        started = asyncio.Event()
        release = asyncio.Event()

        async def blocking_response(**_kwargs):
            started.set()
            await release.wait()
            return self._response()

        with patch(
            "triage_processor.clients.llm.StructuredChatClient.complete",
            new=AsyncMock(side_effect=blocking_response),
        ):
            task = asyncio.create_task(materialize_run(
                self.pool, run_id=self.run_id, base_url="http://fixture", model="fixture",
                api_key=None, stage=stage,
            ))
            await started.wait()
            async with self.pool.acquire() as connection:
                transaction = connection.transaction()
                await transaction.start()
                try:
                    await connection.fetchval(
                        "SELECT id FROM taxonomy_runs WHERE id=$1 FOR UPDATE NOWAIT", self.run_id
                    )
                finally:
                    await transaction.rollback()
            await self.admin.execute(
                "UPDATE taxonomy_run_stages SET lease_owner='new-owner' WHERE id=$1", stage.id
            )
            release.set()
            with self.assertRaisesRegex(RuntimeError, "lease is no longer owned"):
                await task

        self.assertEqual(await self.admin.fetchval(
            "SELECT count(*) FROM taxonomy_model_responses WHERE taxonomy_run_id=$1", self.run_id
        ), 0)
        self.assertEqual(await self.admin.fetchval(
            "SELECT count(*) FROM taxonomy_topic_naming_attempts WHERE taxonomy_run_id=$1", self.run_id
        ), 0)
        self.assertEqual(await self.admin.fetchval(
            "SELECT count(*) FROM taxonomy_provisional_topics WHERE taxonomy_run_id=$1", self.run_id
        ), 0)
