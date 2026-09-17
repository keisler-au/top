"""Disposable PostgreSQL upgrade fixtures for the batch-taxonomy migrations."""
from __future__ import annotations

import os
import json
from pathlib import Path
import unittest
from uuid import uuid4

import asyncpg


DSN = os.environ.get("TRIAGE_TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[3] / "infrastructure/postgres"
if not ROOT.exists():
    ROOT = Path("/infrastructure/postgres")


def legacy_base_sql() -> str:
    """The pre-article fresh schema: an upgrade fixture, not a second schema."""
    return (ROOT / "init.sql").read_text().split("\\ir migrations/013_add_articles.sql", 1)[0]


def migration_sql(path: Path) -> str:
    return path.read_text()


@unittest.skipUnless(DSN, "Set TRIAGE_TEST_DATABASE_URL or use compose.test.yaml")
class MigrationUpgradePostgresTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.schema = "upgrade_" + uuid4().hex
        self.connection = await asyncpg.connect(DSN)
        self.addAsyncCleanup(self.connection.close)
        await self.connection.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
        # The archive is deliberately a separately named schema in production.
        # Each disposable upgrade fixture must therefore clear its prior copy
        # before applying the one-shot archive migration.
        await self.connection.execute("DROP SCHEMA IF EXISTS taxonomy_legacy_archive CASCADE")
        await self.connection.execute(f'CREATE SCHEMA "{self.schema}"')
        self.addAsyncCleanup(self.connection.execute, f'DROP SCHEMA "{self.schema}" CASCADE')
        await self.connection.execute(f'SET search_path TO "{self.schema}", public')

    async def apply_from(self, first: int, last: int = 999) -> None:
        for path in sorted((ROOT / "migrations").glob("*.sql")):
            if first <= int(path.name[:3]) <= last:
                await self.connection.execute(migration_sql(path))

    async def test_legacy_only_upgrade_preserves_historical_rows_and_article_output(self):
        await self.connection.execute(legacy_base_sql())
        await self.connection.execute("""
            INSERT INTO original_inputs(original_text, source, status, topic)
            VALUES ('legacy raw evidence', 'fixture', 'completed', 'Legacy cost');
            INSERT INTO segment_inputs(original_input_id, segment_order, segment_text, topic)
            VALUES (1, 0, 'legacy segment', 'Legacy cost');
            INSERT INTO themes(name, description) VALUES ('Legacy theme', 'legacy theme description');
            INSERT INTO theme_topics(theme_id, topic) VALUES (1, 'Legacy cost');
            INSERT INTO theme_suggestions(action, proposed_name, proposed_description, rationale, group_fingerprint)
            VALUES ('new', 'Suggested', 'suggested description', 'fixture', repeat('a', 64));
            INSERT INTO worker_jobs(job_type, original_input_id, status, available_at)
            VALUES ('topics', 1, 'pending', CURRENT_TIMESTAMP);
        """)
        await self.apply_from(13, 14)
        await self.connection.execute("""
            INSERT INTO articles(title, status, archived_at) VALUES ('Archived legacy article', 'archived', CURRENT_TIMESTAMP);
            INSERT INTO article_revisions(article_id, revision_number, title, structured_content, rendered_html)
            VALUES (1, 1, 'Archived legacy article', '{"sections":[]}'::jsonb, '<article>legacy output</article>');
            UPDATE articles SET current_revision_id=1 WHERE id=1;
            INSERT INTO article_topics(article_id, topic_key, topic_name) VALUES (1, 'legacy cost', 'Legacy cost');
            INSERT INTO article_themes(article_id, theme_id) VALUES (1, 1);
            INSERT INTO article_evidence(revision_id, original_input_id, evidence_order, citation_id, topic_key)
            VALUES (1, 1, 0, 'legacy-citation', 'legacy cost');
        """)
        # Reapplying the remaining migrations models an installation upgraded
        # from the populated legacy-only fixture.
        await self.apply_from(15, 36)
        rollout_run_id = await self.connection.fetchval("""
            INSERT INTO taxonomy_runs(
                source_cutoff, source_snapshot_sha256, configuration,
                configuration_sha256, embedding_model, embedding_representation,
                embedding_dimension, clustering_model, topic_model, theme_model,
                topic_prompt_version, theme_prompt_version
            ) VALUES (
                CURRENT_TIMESTAMP, repeat('a', 64), '{}'::jsonb,
                repeat('b', 64), 'fixture', 'fixture', 2, 'fixture',
                'fixture', 'fixture', 'fixture', 'fixture'
            ) RETURNING id
        """)
        await self.connection.execute("""
            INSERT INTO taxonomy_rollout_reports(
                taxonomy_run_id, legacy_metrics, candidate_metrics, mappings,
                signed_off_by, signed_off_at, sign_off_note
            ) VALUES ($1, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb,
                      'fixture-operator', CURRENT_TIMESTAMP, 'retired record')
        """, rollout_run_id)
        await self.apply_from(37, 37)
        self.assertEqual(await self.connection.fetchval("SELECT original_text FROM original_inputs WHERE id=1"), "legacy raw evidence")
        self.assertEqual(await self.connection.fetchval("SELECT segment_text FROM segment_inputs WHERE id=1"), "legacy segment")
        for retired_relation in (
            "themes", "theme_topics", "theme_suggestions",
            "theme_suggestion_existing_themes", "theme_suggestion_topics",
            "theme_suggestion_evidence", "topic_assignment_attempts",
        ):
            with self.subTest(retired_relation=retired_relation):
                self.assertIsNone(await self.connection.fetchval("SELECT to_regclass($1)", retired_relation))
        for table_name in ("original_inputs", "segment_inputs"):
            with self.subTest(table_name=table_name):
                self.assertIsNone(await self.connection.fetchval(
                    "SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=$1 AND column_name='topic'",
                    table_name,
                ))
        self.assertEqual(
            await self.connection.fetchval(
                "SELECT count(*) FROM worker_jobs WHERE original_input_id=1"
            ),
            0,
        )
        for retired_type in ("topics", "themes"):
            with self.subTest(retired_type=retired_type):
                with self.assertRaises(asyncpg.CheckViolationError):
                    await self.connection.execute(
                        """
                        INSERT INTO worker_jobs(job_type, original_input_id)
                        VALUES($1, 1)
                        """,
                        retired_type,
                    )
        await self.connection.execute(
            "INSERT INTO worker_jobs(job_type, original_input_id) VALUES('embeddings', 1)"
        )
        self.assertEqual(await self.connection.fetchval("SELECT rendered_html FROM article_revisions WHERE id=1"), "<article>legacy output</article>")
        self.assertEqual(await self.connection.fetchval("SELECT citation_id FROM article_evidence WHERE revision_id=1"), "legacy-citation")
        self.assertEqual(await self.connection.fetchval("SELECT status FROM articles WHERE id=1"), "archived")
        self.assertIsNone(await self.connection.fetchval("SELECT to_regclass('taxonomy_rollout_reports')"))
        self.assertEqual(await self.connection.fetchval("""
            SELECT sign_off_note FROM taxonomy_legacy_archive.rollout_reports
            WHERE taxonomy_run_id=$1
        """, rollout_run_id), "retired record")
        archive = await self.connection.fetchrow("""
            SELECT table_counts, table_hashes, archive_sha256
            FROM taxonomy_legacy_archive.exports
        """)
        table_counts = json.loads(archive["table_counts"])
        table_hashes = json.loads(archive["table_hashes"])
        self.assertEqual(table_counts["input_topics"], 1)
        self.assertEqual(table_counts["segment_topics"], 1)
        self.assertEqual(table_counts["themes"], 1)
        self.assertEqual(table_counts["theme_suggestions"], 1)
        self.assertEqual(
            table_hashes["theme_topics"],
            await self.connection.fetchval("SELECT taxonomy_legacy_archive.table_sha256('theme_topics')"),
        )
        self.assertEqual(await self.connection.fetchval("""
            SELECT encode(digest(table_counts::text || E'\\n' || table_hashes::text, 'sha256'), 'hex')
            FROM taxonomy_legacy_archive.exports
        """), archive["archive_sha256"])
        self.assertEqual(await self.connection.fetchval("""
            SELECT topic FROM taxonomy_legacy_archive.segment_topics
            WHERE segment_input_id=1 AND original_input_id=1
        """), "Legacy cost")
        for statement in (
            "UPDATE taxonomy_legacy_archive.themes SET name='mutated' WHERE theme_id=1",
            "DELETE FROM taxonomy_legacy_archive.theme_topics WHERE theme_id=1",
            "INSERT INTO taxonomy_legacy_archive.input_topics VALUES (99, 'bad', CURRENT_TIMESTAMP)",
            "UPDATE taxonomy_legacy_archive.rollout_reports SET sign_off_note='mutated'",
        ):
            with self.assertRaisesRegex(asyncpg.PostgresError, "immutable"):
                await self.connection.execute(statement)

    async def test_current_schema_has_every_migration_marker_and_reapplying_is_a_noop(self):
        await self.connection.execute(legacy_base_sql())
        await self.apply_from(13)
        await self.connection.execute("CREATE TABLE schema_migrations(filename TEXT PRIMARY KEY)")
        names = [path.name for path in sorted((ROOT / "migrations").glob("*.sql"))]
        await self.connection.executemany("INSERT INTO schema_migrations(filename) VALUES($1)", [(name,) for name in names])
        self.assertEqual(await self.connection.fetchval("SELECT count(*) FROM schema_migrations"), len(names))
        self.assertTrue(await self.connection.fetchval("SELECT to_regprocedure('publish_taxonomy_run(bigint,timestamptz,text,text)') IS NOT NULL"))

    async def test_migrations_are_independently_transactional_and_linted(self):
        for path in sorted((ROOT / "migrations").glob("*.sql")):
            source = migration_sql(path).strip()
            self.assertTrue(source.startswith("BEGIN;"), path.name)
            self.assertTrue(source.endswith("COMMIT;"), path.name)
            self.assertNotIn("\\ir ", source, path.name)
            self.assertNotIn("COPY ", source.upper(), path.name)

    async def test_first_publication_is_gate_bound_and_records_an_immutable_decision(self):
        await self.connection.execute(legacy_base_sql())
        await self.apply_from(13)
        run_id = await self.connection.fetchval("""
            INSERT INTO taxonomy_runs(source_cutoff,source_snapshot_sha256,configuration,configuration_sha256,
              embedding_model,embedding_representation,embedding_dimension,clustering_model,topic_model,theme_model,topic_prompt_version,theme_prompt_version)
            VALUES(CURRENT_TIMESTAMP,repeat('a',64),'{}'::jsonb,repeat('b',64),'fixture','fixture',2,'fixture','fixture','fixture','fixture','fixture') RETURNING id
        """)
        topic_id = await self.connection.fetchval("INSERT INTO topics DEFAULT VALUES RETURNING id")
        await self.connection.execute("""
            INSERT INTO topic_revisions(taxonomy_run_id,topic_id,cluster_key,name,normalized_name,literal_description,support_count,continuity_decision)
            VALUES($1,$2,'fixture','Fixture','fixture','fixture',1,'new')
        """, run_id, topic_id)
        await self.connection.execute("UPDATE taxonomy_runs SET status='running',started_at=CURRENT_TIMESTAMP WHERE id=$1", run_id)
        candidate_theme = await self.connection.fetchval("""
            INSERT INTO taxonomy_candidate_themes(taxonomy_run_id,name,description,rationale,inference_request,inference_response)
            VALUES($1,'Fixture theme','fixture','fixture','{}','{}') RETURNING id
        """, run_id)
        await self.connection.execute("INSERT INTO taxonomy_candidate_theme_topics VALUES($1,$2,$3,TRUE)", run_id, candidate_theme, await self.connection.fetchval("SELECT id FROM topic_revisions WHERE taxonomy_run_id=$1", run_id))
        reconciled_theme = await self.connection.fetchval("""
            INSERT INTO taxonomy_reconciled_themes(taxonomy_run_id,canonical_candidate_theme_id,normalized_name,topic_set_sha256)
            VALUES($1,$2,'fixture theme',repeat('d',64)) RETURNING id
        """, run_id, candidate_theme)
        await self.connection.execute("INSERT INTO taxonomy_reconciled_theme_antecedents VALUES($1,$2,$3,'canonical')", run_id, reconciled_theme, candidate_theme)
        await self.connection.execute("UPDATE taxonomy_runs SET status='ready_for_review',completed_at=CURRENT_TIMESTAMP WHERE id=$1", run_id)
        expected = await self.connection.fetchval("SELECT updated_at FROM taxonomy_runs WHERE id=$1", run_id)
        with self.assertRaisesRegex(asyncpg.PostgresError, "gate is not attested"):
            await self.connection.fetchval("SELECT publish_taxonomy_run($1,$2,'fixture')", run_id, expected)
        await self.connection.execute("""
            INSERT INTO taxonomy_release_attestations(taxonomy_run_id,metrics,thresholds,threshold_version,gate_passed,input_sha256)
            VALUES($1,'{}'::jsonb,'{}'::jsonb,'fixture-v1',TRUE,repeat('c',64))
        """, run_id)
        await self.connection.fetchval("SELECT publish_taxonomy_run($1,$2,'fixture','proof')", run_id, expected)
        decision = await self.connection.fetchrow("SELECT gate_input_sha256,threshold_version,decided_by FROM taxonomy_publication_decisions WHERE taxonomy_run_id=$1", run_id)
        self.assertEqual(tuple(decision), ("c" * 64, "fixture-v1", "fixture"))
        with self.assertRaises(asyncpg.PostgresError):
            await self.connection.execute("DELETE FROM taxonomy_publication_decisions WHERE taxonomy_run_id=$1", run_id)
        await self.connection.execute("SELECT set_config('taxonomy.rollback','on',false)")
        await self.connection.execute("UPDATE taxonomy_runs SET status='superseded' WHERE id=$1", run_id)
        newer = await self.connection.fetchval("""
            INSERT INTO taxonomy_runs(source_cutoff,source_snapshot_sha256,configuration,configuration_sha256,embedding_model,embedding_representation,embedding_dimension,clustering_model,topic_model,theme_model,topic_prompt_version,theme_prompt_version)
            VALUES(CURRENT_TIMESTAMP,repeat('d',64),'{}'::jsonb,repeat('e',64),'fixture','fixture',2,'fixture','fixture','fixture','fixture','fixture') RETURNING id
        """)
        newer_topic = await self.connection.fetchval("INSERT INTO topics DEFAULT VALUES RETURNING id")
        await self.connection.execute("INSERT INTO topic_revisions(taxonomy_run_id,topic_id,cluster_key,name,normalized_name,literal_description,support_count,continuity_decision) VALUES($1,$2,'newer','Newer','newer','newer',1,'new')", newer, newer_topic)
        await self.connection.execute("UPDATE taxonomy_runs SET status='running',started_at=CURRENT_TIMESTAMP WHERE id=$1", newer)
        newer_theme = await self.connection.fetchval("""
            INSERT INTO taxonomy_candidate_themes(taxonomy_run_id,name,description,rationale,inference_request,inference_response)
            VALUES($1,'Newer theme','newer','newer','{}','{}') RETURNING id
        """, newer)
        await self.connection.execute("INSERT INTO taxonomy_candidate_theme_topics VALUES($1,$2,$3,TRUE)", newer, newer_theme, await self.connection.fetchval("SELECT id FROM topic_revisions WHERE taxonomy_run_id=$1", newer))
        newer_reconciled = await self.connection.fetchval("""
            INSERT INTO taxonomy_reconciled_themes(taxonomy_run_id,canonical_candidate_theme_id,normalized_name,topic_set_sha256)
            VALUES($1,$2,'newer theme',repeat('e',64)) RETURNING id
        """, newer, newer_theme)
        await self.connection.execute("INSERT INTO taxonomy_reconciled_theme_antecedents VALUES($1,$2,$3,'canonical')", newer, newer_reconciled, newer_theme)
        await self.connection.execute("UPDATE taxonomy_runs SET status='ready_for_review',completed_at=CURRENT_TIMESTAMP WHERE id=$1", newer)
        newer_expected = await self.connection.fetchval("SELECT updated_at FROM taxonomy_runs WHERE id=$1", newer)
        await self.connection.execute("INSERT INTO taxonomy_release_attestations(taxonomy_run_id,metrics,thresholds,threshold_version,gate_passed,input_sha256) VALUES($1,'{}','{}','fixture-v1',TRUE,repeat('f',64))", newer)
        await self.connection.fetchval("SELECT publish_taxonomy_run($1,$2,'fixture')", newer, newer_expected)
        await self.connection.fetchval("SELECT rollback_taxonomy_run($1,'fixture','rollback proof')", run_id)
        self.assertEqual(await self.connection.fetchval("SELECT status FROM taxonomy_runs WHERE id=$1", run_id), "published")
        self.assertEqual(await self.connection.fetchval("SELECT status FROM taxonomy_runs WHERE id=$1", newer), "superseded")
        self.assertEqual(await self.connection.fetchval("SELECT count(*) FROM taxonomy_rollback_decisions WHERE from_run_id=$1 AND to_run_id=$2", newer, run_id), 1)
