import inspect
import os
import unittest
from unittest.mock import patch

from triage_processor.taxonomy_scheduler import SchedulerSettings, check_health, process_stage, required_migration_filenames


class _HealthConnection:
    def __init__(self, *, migrations=True, vector=True, claim=True, database=True):
        self.migrations = migrations
        self.vector = vector
        self.claim = claim
        self.database = database

    async def fetch(self, _query):
        if not self.database:
            raise OSError("database unavailable")
        return [{"filename": name} for name in required_migration_filenames()] if self.migrations else []

    async def fetchval(self, query):
        if "pg_extension" in query:
            return self.vector
        return self.claim


class _Acquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *_args):
        return None


class _HealthPool:
    def __init__(self, connection):
        self.connection = connection
        self.closed = False

    def acquire(self):
        return _Acquire(self.connection)

    async def close(self):
        self.closed = True


class TaxonomySchedulerTests(unittest.TestCase):
    def test_health_check_verifies_the_durable_stage_schema(self):
        source = inspect.getsource(check_health)
        self.assertIn("taxonomy_run_stages", source)
        self.assertIn("schema_migrations", source)
        self.assertIn("pg_extension", source)
        self.assertIn("taxonomy_run_jobs", source)

    def test_failure_logs_only_the_bounded_error_class(self):
        source = inspect.getsource(process_stage)
        self.assertIn("bounded_error_class(error)", source)
        self.assertNotIn("exc_info=", source)

    def test_default_settings_are_valid(self):
        SchedulerSettings().validate()

    def test_rejects_invalid_scheduler_settings(self):
        with self.assertRaisesRegex(ValueError, "MAX_ATTEMPTS"):
            SchedulerSettings(max_attempts=0).validate()
        with self.assertRaisesRegex(ValueError, "RETRY_MAX"):
            SchedulerSettings(retry_base_seconds=10, retry_max_seconds=5).validate()

    def test_reads_versioned_worker_settings_from_environment(self):
        with patch.dict(os.environ, {
            "TAXONOMY_POLL_INTERVAL": "2",
            "TAXONOMY_LEASE_SECONDS": "45",
            "TAXONOMY_MAX_ATTEMPTS": "4",
            "TAXONOMY_RETRY_BASE_SECONDS": "3",
            "TAXONOMY_RETRY_MAX_SECONDS": "30",
        }, clear=False):
            self.assertEqual(
                SchedulerSettings.from_env(),
                SchedulerSettings(2, 45, 4, 3, 30),
            )


class TaxonomySchedulerHealthTests(unittest.IsolatedAsyncioTestCase):
    async def _assert_health_failure(self, expected, **connection_settings):
        pool = _HealthPool(_HealthConnection(**connection_settings))
        async def create_pool(*_args, **_kwargs):
            return pool
        with patch("triage_processor.taxonomy_scheduler.asyncpg.create_pool", create_pool):
            with self.assertRaisesRegex((RuntimeError, OSError), expected):
                await check_health()
        self.assertTrue(pool.closed)

    async def test_health_rejects_missing_migration(self):
        await self._assert_health_failure("migrations", migrations=False)

    async def test_health_rejects_unavailable_pgvector(self):
        await self._assert_health_failure("pgvector", vector=False)

    async def test_health_rejects_database_loss(self):
        await self._assert_health_failure("database unavailable", database=False)

    async def test_health_rejects_inability_to_claim_work(self):
        await self._assert_health_failure("cannot claim", claim=False)
