from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "compose.yaml"
if not COMPOSE.exists():
    COMPOSE = Path("/compose.yaml")
MIGRATION = ROOT / "infrastructure/postgres/migrations/020_add_taxonomy_run_queue.sql"
if not MIGRATION.exists():
    MIGRATION = Path("/infrastructure/postgres/migrations/020_add_taxonomy_run_queue.sql")


class TaxonomySchedulerComposeTests(unittest.TestCase):
    def test_scheduler_waits_for_migrations_and_has_a_closed_health_contract(self):
        compose = COMPOSE.read_text()
        service = compose[compose.index("  taxonomy-scheduler:"):compose.index("  article-generation:")]
        self.assertIn('command: ["python", "-m", "triage_processor.taxonomy_scheduler"]', service)
        self.assertIn("condition: service_completed_successfully", service)
        self.assertIn('"--healthcheck"', service)
        self.assertIn("stop_grace_period: 2m", service)

    def test_scheduler_cadence_and_configuration_are_versioned(self):
        compose = COMPOSE.read_text()
        service = compose[compose.index("  taxonomy-scheduler:"):compose.index("  article-generation:")]
        for setting in (
            "TAXONOMY_POLL_INTERVAL", "TAXONOMY_LEASE_SECONDS", "TAXONOMY_MAX_ATTEMPTS",
            "TAXONOMY_RETRY_BASE_SECONDS", "TAXONOMY_RETRY_MAX_SECONDS",
            "TAXONOMY_SCHEDULER_CONFIGURATION_VERSION",
            "TAXONOMY_AUTOMATION_ENABLED", "TAXONOMY_AUTOMATION_POLICY_VERSION",
            "TAXONOMY_AUTOMATION_MINIMUM_EVIDENCE", "TAXONOMY_AUTOMATION_QUIET_SECONDS",
            "TAXONOMY_EMBEDDING_DIMENSION",
        ):
            with self.subTest(setting=setting):
                self.assertIn(setting, service)

    def test_legacy_taxonomy_workers_are_not_deployed(self):
        compose = COMPOSE.read_text()
        self.assertNotIn("  topics:\n", compose)
        self.assertNotIn("  themes:\n", compose)

    def test_retired_runtime_has_no_worker_modules_or_queue_types(self):
        source_root = ROOT / "backend/src/triage_processor"
        if not source_root.exists():
            source_root = Path("/app/src/triage_processor")
        self.assertFalse((source_root / "workers/topics.py").exists())
        self.assertFalse((source_root / "workers/themes.py").exists())
        manual_runner = ROOT / "infrastructure/postgres/manual_test.py"
        if not manual_runner.exists():
            manual_runner = Path("/infrastructure/postgres/manual_test.py")
        self.assertFalse(manual_runner.exists())
        queue = (source_root / "job_queue.py").read_text()
        self.assertNotIn('"topics",', queue)
        self.assertNotIn('"themes",', queue)
        articles = (source_root / "articles.py").read_text()
        self.assertNotIn("legacy_paths", articles)
        self.assertNotIn("FROM themes WHERE", articles)

    def test_compose_retains_one_active_candidate_enforcement_in_database(self):
        migration = MIGRATION.read_text()
        self.assertIn("taxonomy_run_jobs_one_active", migration)
        self.assertIn("status IN ('pending', 'processing')", migration)
