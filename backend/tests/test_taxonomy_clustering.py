import asyncio
import unittest
from unittest.mock import patch

from triage_processor.taxonomy_clustering import (
    ClusterEvidence,
    ClusterPlan,
    make_cluster_plan,
    persist_cluster_plan,
)


class ExistingPlanConnection:
    def __init__(self):
        self.execute_called = False

    async def fetchval(self, query, *values):
        return 1

    async def execute(self, query, *values):
        self.execute_called = True

from triage_processor.taxonomy_experiment import ClusterResult


class TaxonomyClusteringTests(unittest.TestCase):
    def test_automatic_minimum_three_rows_can_reach_real_clusterer(self):
        evidence = [
            ClusterEvidence(1, 1, (1.0, 0.0)),
            ClusterEvidence(2, 2, (0.95, 0.05)),
            ClusterEvidence(3, 3, (0.9, 0.1)),
        ]
        plan = make_cluster_plan(evidence, min_cluster_size=3, min_samples=2)
        self.assertEqual(
            sum(len(cluster.member_indexes) for cluster in plan.clusters) + len(plan.noise_indexes),
            3,
        )

    def test_persisted_plan_is_a_noop_when_a_stage_is_reclaimed(self):
        connection = ExistingPlanConnection()
        asyncio.run(persist_cluster_plan(connection, 9, [], ClusterPlan((), (), ())))
        self.assertFalse(connection.execute_called)

    def test_plan_records_noise_and_deduplicated_representatives(self):
        evidence = [
            ClusterEvidence(1, 10, (1.0, 0.0)),
            ClusterEvidence(2, 10, (0.99, 0.1)),
            ClusterEvidence(3, 11, (0.9, 0.4)),
            ClusterEvidence(4, 12, (0.8, 0.6)),
            ClusterEvidence(5, 13, (0.7, 0.7)),
            ClusterEvidence(6, 14, (0.0, 1.0)),
        ]
        with patch(
            "triage_processor.taxonomy_clustering.hdbscan_clusters",
            return_value=ClusterResult("hdbscan", (0, 0, 0, 0, 0, -1), {}),
        ):
            plan = make_cluster_plan(evidence, min_cluster_size=2, min_samples=1)
        self.assertEqual(plan.noise_indexes, (5,))
        self.assertEqual(plan.membership_probabilities, (1.0, 1.0, 1.0, 1.0, 1.0, 0.0))
        self.assertEqual(plan.clusters[0].member_indexes, (0, 1, 2, 3, 4))
        selected = [evidence[index].original_input_id for index, _ in plan.clusters[0].representatives]
        self.assertEqual(len(selected), len(set(selected)))
        self.assertEqual(plan.clusters[0].representatives[-1][1], "diverse")

    def test_rejects_inconsistent_dimensions(self):
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            make_cluster_plan(
                [ClusterEvidence(1, 1, (1.0,)), ClusterEvidence(2, 2, (1.0, 0.0))],
                min_cluster_size=2,
                min_samples=1,
            )

    def test_rejects_a_zero_vector_before_calling_the_clusterer(self):
        with self.assertRaisesRegex(ValueError, "zero-length"):
            make_cluster_plan(
                [ClusterEvidence(1, 1, (0.0, 0.0)), ClusterEvidence(2, 2, (1.0, 0.0))],
                min_cluster_size=2, min_samples=1,
            )

    def test_singleton_cluster_is_persisted_as_noise(self):
        with patch(
            "triage_processor.taxonomy_clustering.hdbscan_clusters",
            return_value=ClusterResult("hdbscan", (0, -1), {}, (0.9, 0.0)),
        ):
            plan = make_cluster_plan(
                [ClusterEvidence(1, 1, (1.0, 0.0)), ClusterEvidence(2, 2, (0.0, 1.0))],
                min_cluster_size=2, min_samples=1,
            )
        self.assertEqual(plan.clusters, ())
        self.assertEqual(plan.noise_indexes, (0, 1))

    def test_rejects_invalid_probability_shape(self):
        with patch(
            "triage_processor.taxonomy_clustering.hdbscan_clusters",
            return_value=ClusterResult("hdbscan", (0, 0), {}, (0.5,)),
        ), self.assertRaisesRegex(ValueError, "probabilities"):
            make_cluster_plan(
                [ClusterEvidence(1, 1, (1.0, 0.0)), ClusterEvidence(2, 2, (0.0, 1.0))],
                min_cluster_size=2, min_samples=1,
            )
