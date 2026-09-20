"""Compose-facing public-library lifecycle proof.

The test intentionally writes a small, batch-only fixture to the disposable
PostgreSQL database and observes it only through the built public nginx edge.
It therefore catches a regression where the renderer or edge stops respecting
the approved-publication projection.
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import unittest

import asyncpg


DSN = os.environ.get("TRIAGE_TEST_DATABASE_URL")
EDGE = os.environ.get("PUBLIC_EDGE_BASE_URL")
API = os.environ.get("PUBLIC_API_BASE_URL", "http://api:8000")


@unittest.skipUnless(DSN and EDGE, "Compose PostgreSQL and public edge are required")
class PublicSiteEndToEndTests(unittest.IsolatedAsyncioTestCase):
    def edge(self, path: str) -> tuple[int, str]:
        try:
            with urlopen(f"{EDGE.rstrip('/')}{path}", timeout=5) as response:
                return response.status, response.read().decode()
        except HTTPError as error:
            return error.code, error.read().decode()

    def transition(self, article_id: int, action: str) -> None:
        request = Request(
            f"{API.rstrip('/')}/articles/{article_id}/{action}", data=b"{}",
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urlopen(request, timeout=5) as response:
            self.assertEqual(response.status, 200)

    async def test_01_no_publications_then_full_publication_lifecycle(self) -> None:
        # The fresh Compose database is deliberately empty: no internal or
        # draft material is allowed to appear before an approval occurs.
        self.assertEqual(self.edge("/insights")[0], 200)
        self.assertIn("No published insights", self.edge("/insights")[1])
        self.assertEqual(self.edge("/insights/not-published")[0], 404)

        connection = await asyncpg.connect(DSN)
        self.addAsyncCleanup(connection.close)
        run_id = await connection.fetchval("""
            INSERT INTO taxonomy_runs(
                source_cutoff, source_snapshot_sha256, configuration, configuration_sha256,
                embedding_model, embedding_representation, embedding_dimension,
                clustering_model, topic_model, theme_model, topic_prompt_version, theme_prompt_version
            ) VALUES(
                CURRENT_TIMESTAMP, repeat('e',64), '{}'::jsonb, repeat('f',64),
                'fixture', 'fixture', 2, 'fixture', 'fixture', 'fixture', 'fixture', 'fixture'
            ) RETURNING id
        """)
        candidate_id = await connection.fetchval("""
            INSERT INTO taxonomy_candidate_themes(taxonomy_run_id,name,description,rationale,inference_request,inference_response)
            VALUES($1,'Lifecycle theme','fixture','fixture','{}'::jsonb,'{}'::jsonb) RETURNING id
        """, run_id)
        reconciled_id = await connection.fetchval("""
            INSERT INTO taxonomy_reconciled_themes(taxonomy_run_id,canonical_candidate_theme_id,normalized_name,topic_set_sha256)
            VALUES($1,$2,'lifecycle theme',repeat('a',64)) RETURNING id
        """, run_id, candidate_id)
        theme_id = await connection.fetchval(
            "INSERT INTO theme_identities(created_in_run_id) VALUES($1) RETURNING id", run_id
        )
        await connection.execute("""
            INSERT INTO theme_revisions(theme_id,taxonomy_run_id,reconciled_theme_id,name,normalized_name,description)
            VALUES($1,$2,$3,'Lifecycle theme','lifecycle theme','fixture')
        """, theme_id, run_id, reconciled_id)
        await connection.execute("UPDATE taxonomy_runs SET status='running', started_at=CURRENT_TIMESTAMP WHERE id=$1", run_id)
        await connection.execute("UPDATE taxonomy_runs SET status='ready_for_review', completed_at=CURRENT_TIMESTAMP WHERE id=$1", run_id)
        await connection.execute("""
            UPDATE taxonomy_runs
            SET status='published', decision_by='fixture', decision_at=CURRENT_TIMESTAMP,
                published_at=CURRENT_TIMESTAMP
            WHERE id=$1
        """, run_id)

        article_id = await connection.fetchval(
            "INSERT INTO articles(title) VALUES('Lifecycle insight') RETURNING id"
        )
        revision_id = await connection.fetchval("""
            INSERT INTO article_revisions(article_id,revision_number,title,structured_content,rendered_html)
            VALUES($1,1,'Lifecycle insight','{}'::jsonb,'<p>Initial public snapshot.</p>') RETURNING id
        """, article_id)
        await connection.execute("UPDATE articles SET current_revision_id=$2 WHERE id=$1", article_id, revision_id)
        await connection.execute("""
            INSERT INTO article_themes(article_id,stable_theme_id,theme_name_snapshot)
            VALUES($1,$2,'Lifecycle theme')
        """, article_id, theme_id)
        evidence_id = await connection.fetchval(
            "INSERT INTO original_inputs(original_text,source,status) VALUES('Lifecycle evidence','fixture','completed') RETURNING id"
        )
        await connection.execute("""
            INSERT INTO article_evidence(revision_id,original_input_id,evidence_order,topic_key,taxonomy_run_id)
            VALUES($1,$2,0,'lifecycle',$3)
        """, revision_id, evidence_id, run_id)

        slug = f"lifecycle-insight-{article_id}"
        self.assertEqual(self.edge(f"/insights/{slug}")[0], 404)
        self.transition(article_id, "submit")
        self.transition(article_id, "approve")
        status, body = self.edge(f"/insights/{slug}")
        self.assertEqual(status, 200)
        self.assertIn("Initial public snapshot.", body)
        self.assertIn("Lifecycle theme", body)

        # Returning to draft immediately withdraws the projection. Reapproval
        # keeps the permanent URL but moves it to a new immutable revision.
        self.transition(article_id, "return-to-draft")
        self.assertEqual(self.edge(f"/insights/{slug}")[0], 404)
        revised_id = await connection.fetchval("""
            INSERT INTO article_revisions(article_id,revision_number,title,structured_content,rendered_html)
            VALUES($1,2,'Renamed editorial title','{}'::jsonb,'<p>Reapproved public snapshot.</p>') RETURNING id
        """, article_id)
        await connection.execute("UPDATE articles SET current_revision_id=$2 WHERE id=$1", article_id, revised_id)
        await connection.execute("UPDATE article_themes SET theme_name_snapshot='Renamed theme' WHERE article_id=$1", article_id)
        await connection.execute("""
            INSERT INTO article_evidence(revision_id,original_input_id,evidence_order,topic_key,taxonomy_run_id)
            VALUES($1,$2,0,'lifecycle',$3)
        """, revised_id, evidence_id, run_id)
        self.transition(article_id, "submit")
        self.transition(article_id, "approve")
        status, body = self.edge(f"/insights/{slug}")
        self.assertEqual(status, 200)
        self.assertIn("Renamed editorial title", body)
        self.assertIn("Reapproved public snapshot.", body)
        self.assertIn("Renamed theme", body)
        publication = await connection.fetchrow("""
            SELECT approved_revision_id, slug FROM article_publications WHERE article_id=$1
        """, article_id)
        self.assertEqual((publication["approved_revision_id"], publication["slug"]), (revised_id, slug))
        self.assertEqual(await connection.fetchval("""
            SELECT display_name FROM article_publication_themes
            WHERE article_id=$1 AND approved_revision_id=$2 AND stable_theme_id=$3
        """, article_id, revision_id, theme_id), "Lifecycle theme")

        self.transition(article_id, "archive")
        self.assertEqual(self.edge(f"/insights/{slug}")[0], 404)
        self.assertEqual(self.edge("/_site/insights")[0], 404)
        self.assertEqual(self.edge("/api/articles")[0], 404)

        # Publish a successor lineage containing every supported relationship,
        # then roll back. Neither operation may rewrite the historical article
        # projection captured above.
        await connection.execute("SELECT set_config('taxonomy.rollback','on',false)")
        await connection.execute("UPDATE taxonomy_runs SET status='superseded' WHERE id=$1", run_id)
        successor_run = await connection.fetchval("""
            INSERT INTO taxonomy_runs(
                source_cutoff,source_snapshot_sha256,configuration,configuration_sha256,
                embedding_model,embedding_representation,embedding_dimension,
                clustering_model,topic_model,theme_model,topic_prompt_version,theme_prompt_version
            ) VALUES(CURRENT_TIMESTAMP,repeat('1',64),'{}'::jsonb,repeat('2',64),
                'fixture','fixture',2,'fixture','fixture','fixture','fixture','fixture') RETURNING id
        """)
        await connection.execute("UPDATE taxonomy_runs SET status='running', started_at=CURRENT_TIMESTAMP WHERE id=$1", successor_run)
        await connection.execute("UPDATE taxonomy_runs SET status='ready_for_review', completed_at=CURRENT_TIMESTAMP WHERE id=$1", successor_run)
        successor_ids = [await connection.fetchval(
            "INSERT INTO theme_identities(created_in_run_id) VALUES($1) RETURNING id", successor_run
        ) for _ in range(3)]
        await connection.executemany("""
            INSERT INTO theme_lineage(taxonomy_run_id,predecessor_theme_id,successor_theme_id,relationship)
            VALUES($1,$2,$3,$4)
        """, [
            (successor_run, theme_id, theme_id, "rename"),
            (successor_run, theme_id, successor_ids[0], "split"),
            (successor_run, successor_ids[1], successor_ids[0], "merge"),
            (successor_run, successor_ids[2], None, "retired"),
        ])
        await connection.execute("""
            UPDATE taxonomy_runs SET status='published', decision_by='fixture',
            decision_at=CURRENT_TIMESTAMP, published_at=CURRENT_TIMESTAMP WHERE id=$1
        """, successor_run)
        self.assertEqual(await connection.fetchval("SELECT count(*) FROM theme_lineage WHERE taxonomy_run_id=$1", successor_run), 4)
        await connection.fetchval("SELECT rollback_taxonomy_run($1,'fixture','public snapshot proof')", run_id)
        self.assertEqual(await connection.fetchval("SELECT status FROM taxonomy_runs WHERE id=$1", run_id), "published")
        self.assertEqual(await connection.fetchval("""
            SELECT display_name FROM article_publication_themes
            WHERE article_id=$1 AND approved_revision_id=$2 AND stable_theme_id=$3
        """, article_id, revision_id, theme_id), "Lifecycle theme")
