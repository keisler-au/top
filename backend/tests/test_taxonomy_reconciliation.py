import asyncio
import unittest

from triage_processor.taxonomy_reconciliation import ThemeCandidate, reconcile_candidates, reconcile_run


class AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class ExistingReconciliationConnection:
    def __init__(self):
        self.execute_called = False

    async def fetch(self, query, *values):
        return []

    async def fetchval(self, query, *values):
        return 1

    async def execute(self, query, *values):
        self.execute_called = True

    def transaction(self):
        return AsyncContext(self)


class ExistingReconciliationPool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return AsyncContext(self.connection)


class TaxonomyReconciliationTests(unittest.TestCase):
    def test_reclaimed_stage_keeps_an_existing_reconciliation_immutable(self):
        connection = ExistingReconciliationConnection()
        result = asyncio.run(reconcile_run(ExistingReconciliationPool(connection), 9))
        self.assertEqual(result, ())
        self.assertFalse(connection.execute_called)

    def test_equivalent_candidates_consolidate_with_immutable_antecedents(self):
        plan = reconcile_candidates([
            ThemeCandidate(8, " Purchasing friction ", (4, 2, 4)),
            ThemeCandidate(3, "purchasing   friction", (2, 4)),
            ThemeCandidate(9, "Service quality", (7,)),
        ])
        self.assertEqual(len(plan), 2)
        purchasing = plan[0]
        self.assertEqual(purchasing.canonical_candidate_id, 3)
        self.assertEqual(purchasing.antecedent_candidate_ids, (3, 8))
        self.assertRegex(purchasing.topic_set_sha256, "^[0-9a-f]{64}$")

    def test_empty_identity_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "name and topic set"):
            reconcile_candidates([ThemeCandidate(1, " ", (1,))])
