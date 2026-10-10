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


def unit(evidence_id, original_input_id, vector, *, question_id=1):
    return ClusterEvidence(
        evidence_id,
        original_input_id,
        question_id,
        f"Question {question_id}",
        f"Answer {evidence_id}",
        vector,
    )


class TaxonomyClusteringTests(unittest.TestCase):
    def test_clusters_each_question_scope_independently(self):
        evidence = [
            unit(1, 1, (1.0, 0.0), question_id=10),
            unit(2, 2, (0.99, 0.01), question_id=10),
            unit(3, 3, (0.0, 1.0), question_id=20),
            unit(4, 4, (0.01, 0.99), question_id=20),
        ]
        result = ClusterResult(
            "hdbscan", (0, 0), {}, (0.9, 0.9), (0.8,)
        )
        with patch(
            "triage_processor.taxonomy_clustering.hdbscan_clusters",
            side_effect=[result, result],
        ) as clusterer:
            plan = make_cluster_plan(
                evidence, min_cluster_size=2, min_samples=1
            )

        self.assertEqual(clusterer.call_count, 2)
        self.assertEqual(
            {cluster.question_id for cluster in plan.clusters}, {10, 20}
        )
        self.assertTrue(all(cluster.eligible for cluster in plan.clusters))

    def test_large_cluster_selects_thirty_central_and_ten_diverse(self):
        evidence = [
            unit(index, index, (1.0, index / 10_000))
            for index in range(1, 46)
        ]
        result = ClusterResult(
            "hdbscan", tuple([0] * 45), {}, tuple([0.9] * 45), (0.8,)
        )
        with patch(
            "triage_processor.taxonomy_clustering.hdbscan_clusters",
            return_value=result,
        ):
            plan = make_cluster_plan(
                evidence, min_cluster_size=2, min_samples=1
            )

        cluster = plan.clusters[0]
        kinds = [kind for _, kind in cluster.representatives]
        self.assertEqual(kinds.count("central"), 30)
        self.assertEqual(kinds.count("diverse"), 10)
        self.assertTrue(cluster.eligible)
        self.assertLessEqual(cluster.packet_serialized_bytes, 32_768)

    def test_failed_geometry_is_durable_and_not_eligible_for_naming(self):
        evidence = [
            unit(1, 1, (1.0, 0.0)),
            unit(2, 2, (0.0, 1.0)),
        ]
        result = ClusterResult(
            "hdbscan", (0, 0), {}, (0.9, 0.9), (0.8,)
        )
        with patch(
            "triage_processor.taxonomy_clustering.hdbscan_clusters",
            return_value=result,
        ):
            cluster = make_cluster_plan(
                evidence, min_cluster_size=2, min_samples=1
            ).clusters[0]

        self.assertFalse(cluster.eligible)
        self.assertIn("cohesion_below_minimum", cluster.failure_reasons)

    def test_automatic_minimum_two_rows_can_reach_real_clusterer(self):
        evidence = [
            unit(1, 1, (1.0, 0.0)),
            unit(2, 2, (0.95, 0.05)),
        ]
        plan = make_cluster_plan(evidence, min_cluster_size=2, min_samples=1)
        self.assertEqual(
            sum(len(cluster.member_indexes) for cluster in plan.clusters) + len(plan.noise_indexes),
            2,
        )

    def test_persisted_plan_is_a_noop_when_a_stage_is_reclaimed(self):
        connection = ExistingPlanConnection()
        asyncio.run(persist_cluster_plan(connection, 9, [], ClusterPlan((), (), ())))
        self.assertFalse(connection.execute_called)

    def test_plan_records_noise_and_deduplicated_representatives(self):
        evidence = [
            unit(1, 10, (1.0, 0.0)),
            unit(2, 10, (0.99, 0.1)),
            unit(3, 11, (0.9, 0.4)),
            unit(4, 12, (0.8, 0.6)),
            unit(5, 13, (0.7, 0.7)),
            unit(6, 14, (0.0, 1.0)),
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
        self.assertTrue(all(kind == "all" for _, kind in plan.clusters[0].representatives))

    def test_rejects_inconsistent_dimensions(self):
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            make_cluster_plan(
                [unit(1, 1, (1.0,)), unit(2, 2, (1.0, 0.0))],
                min_cluster_size=2,
                min_samples=1,
            )

    def test_rejects_a_zero_vector_before_calling_the_clusterer(self):
        with self.assertRaisesRegex(ValueError, "zero-length"):
            make_cluster_plan(
                [unit(1, 1, (0.0, 0.0)), unit(2, 2, (1.0, 0.0))],
                min_cluster_size=2, min_samples=1,
            )

    def test_singleton_cluster_is_persisted_as_noise(self):
        with patch(
            "triage_processor.taxonomy_clustering.hdbscan_clusters",
            return_value=ClusterResult("hdbscan", (0, -1), {}, (0.9, 0.0)),
        ):
            plan = make_cluster_plan(
                [unit(1, 1, (1.0, 0.0)), unit(2, 2, (0.0, 1.0))],
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
                [unit(1, 1, (1.0, 0.0)), unit(2, 2, (0.0, 1.0))],
                min_cluster_size=2, min_samples=1,
            )
