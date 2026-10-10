import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from triage_processor.taxonomy_experiment import (
    DATASET_FORMAT,
    ClusterResult,
    EvidenceUnit,
    cluster_members,
    cosine_similarity,
    cluster_diagnostics,
    cluster_passes_policy,
    evaluate_representation,
    evaluate_question_scopes,
    partition_agreement,
    read_dataset,
    select_bounded_packet,
    select_representatives,
    theme_neighbourhood_requests,
    threshold_components,
    topic_relationship,
    write_dataset,
)


def unit(identifier, original_id, vector):
    return EvidenceUnit(
        evidence_id=identifier,
        original_input_id=original_id,
        segment_input_id=None,
        answer_text=identifier,
        question_text=None,
        created_at="2026-09-08T12:00:00+00:00",
        vectors={"question-answer": vector, "answer-only": vector},
    )


class TaxonomyExperimentTests(unittest.TestCase):
    def setUp(self):
        self.evidence = [
            unit("original:1", 1, [1.0, 0.0]),
            unit("original:2", 2, [0.99, 0.1]),
            unit("segment:3", 3, [0.0, 1.0]),
            unit("segment:4", 4, [0.1, 0.99]),
        ]

    def test_threshold_baseline_is_deterministic_and_keeps_components(self):
        result = threshold_components(
            [item.vectors["question-answer"] for item in self.evidence],
            minimum_similarity=0.95,
        )
        self.assertEqual(result.labels, (0, 0, 1, 1))
        self.assertEqual(cluster_members(result.labels), {0: [0, 1], 1: [2, 3]})

    def test_representatives_deduplicate_originals_and_include_diverse_member(self):
        evidence = [
            unit("segment:10", 1, [1.0, 0.0]),
            unit("segment:11", 1, [0.99, 0.1]),
            unit("original:2", 2, [0.9, 0.4]),
            unit("original:3", 3, [0.2, 0.98]),
        ]
        selected = select_representatives(
            evidence,
            [item.vectors["question-answer"] for item in evidence],
            [0, 1, 2, 3],
            central_count=2,
        )
        originals = {next(item.original_input_id for item in evidence if item.evidence_id == identifier) for identifier in selected}
        self.assertEqual(len(originals), len(selected))
        self.assertIn("original:3", selected)

    def test_dataset_round_trip_preserves_versioned_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dataset.json"
            from datetime import datetime, timezone

            write_dataset(
                path,
                cutoff=datetime(2026, 9, 8, 12, tzinfo=timezone.utc),
                embedding_model="test-model",
                source_representation="question-answer",
                evidence=self.evidence,
            )
            metadata, loaded = read_dataset(path)
        self.assertEqual(metadata["format"], DATASET_FORMAT)
        self.assertEqual(loaded, self.evidence)

    def test_evaluation_records_noise_and_repeatability(self):
        baseline = threshold_components(
            [item.vectors["question-answer"] for item in self.evidence],
            minimum_similarity=0.95,
        )
        hdbscan_result = ClusterResult("hdbscan", baseline.labels, {"min_cluster_size": 2})
        with patch(
            "triage_processor.taxonomy_experiment.hdbscan_clusters",
            return_value=hdbscan_result,
        ):
            report = evaluate_representation(
                self.evidence,
                "question-answer",
                threshold=0.95,
                min_cluster_size=2,
                min_samples=1,
            )
        self.assertEqual(len(report["methods"]), 2)
        self.assertEqual(report["methods"][0]["cluster_count"], 2)
        self.assertEqual(report["methods"][1]["rerun_agreement"], 1.0)
        packets = theme_neighbourhood_requests(report, minimum_similarity=0.5)
        self.assertEqual(len(packets), 2)
        self.assertEqual(packets[0]["topics"][0]["representative_evidence"][0]["evidence_id"], "original:1")

    def test_similarity_and_partition_agreement_validate_inputs(self):
        self.assertAlmostEqual(cosine_similarity([1, 0], [1, 0]), 1.0)
        self.assertEqual(partition_agreement([0, 0, 1], [4, 4, 2]), 1.0)
        with self.assertRaisesRegex(ValueError, "dimensions differ"):
            cosine_similarity([1], [1, 0])

    def test_selected_packet_uses_all_up_to_forty_and_thirty_plus_ten_after(self):
        evidence = [unit(f"original:{index:02}", index, [1.0, index / 100]) for index in range(45)]
        vectors = [item.vectors["answer-only"] for item in evidence]
        small = select_bounded_packet(evidence, vectors, list(range(40)))
        large = select_bounded_packet(evidence, vectors, list(range(45)))
        self.assertTrue(small["eligible"])
        self.assertEqual(len(small["evidence_ids"]), 40)
        self.assertEqual(small["selection_kinds"], ["all"] * 40)
        self.assertTrue(large["eligible"])
        self.assertEqual(large["selection_kinds"].count("central"), 30)
        self.assertEqual(large["selection_kinds"].count("diverse"), 10)

    def test_selected_packet_deduplicates_originals_and_fails_closed_on_bound(self):
        evidence = [
            unit("segment:1", 1, [1.0, 0.0]),
            unit("segment:2", 1, [0.9, 0.1]),
            unit("original:2", 2, [0.8, 0.2]),
        ]
        vectors = [item.vectors["answer-only"] for item in evidence]
        packet = select_bounded_packet(evidence, vectors, [0, 1, 2])
        self.assertEqual(packet["evidence_ids"], ["original:2", "segment:1"])
        exhausted = select_bounded_packet(evidence, vectors, [0, 1, 2], maximum_bytes=2)
        self.assertFalse(exhausted["eligible"])
        self.assertEqual(exhausted["reason"], "complete_packet_exceeds_serialized_bound")

    def test_cluster_diagnostics_distinguish_shape_probability_and_stability(self):
        diagnostics = cluster_diagnostics(
            [[1.0, 0.0], [0.98, 0.02], [0.0, 1.0], [0.02, 0.98]],
            [0, 0, 1, 1],
            [0.9, 0.8, 0.7, 0.4],
            [[0, 0, 1, 1], [3, 3, 4, -1]],
            [0.75, 0.25],
        )
        self.assertGreater(diagnostics[0]["cohesion_mean_cosine"], 0.99)
        self.assertGreater(diagnostics[0]["centroid_separation"], 0.9)
        self.assertEqual(diagnostics[0]["membership_p10"], 0.8)
        self.assertEqual(diagnostics[0]["stability_pair_retention"], 1.0)
        self.assertEqual(diagnostics[0]["density_persistence"], 0.75)
        self.assertEqual(diagnostics[1]["membership_p10"], 0.4)
        self.assertEqual(diagnostics[1]["stability_pair_retention"], 0.0)

    def test_dense_identical_vectors_keep_cohesion_inside_policy_range(self):
        vectors = [[float(axis % 17 + 1) for axis in range(768)]] * 3
        diagnostics = cluster_diagnostics(vectors, [0, 0, 0], [1.0] * 3, [[0, 0, 0]], [1.0])
        self.assertLessEqual(diagnostics[0]["cohesion_mean_cosine"], 1.0)
        self.assertEqual(cluster_passes_policy(diagnostics[0]), (True, ()))
        self.assertTrue(math.isnan(cosine_similarity([float("nan"), 1], [1, 1])))

    def test_equivalence_rubric_preserves_views_but_merges_the_same_concept(self):
        self.assertEqual(topic_relationship("bus-frequency", "increase", "transport", "bus-frequency", "decrease", "transport"), "equivalent")
        self.assertEqual(topic_relationship("bus-frequency", "increase", "transport", "bus-cost", "lower", "transport"), "related-not-equivalent")
        self.assertEqual(topic_relationship("bus-frequency", "increase", "transport", "housing-cost", "lower", "housing"), "distinct")

    def test_cluster_policy_reports_each_failed_metric_without_hiding_small_clusters(self):
        passing = {
            "cohesion_mean_cosine": 0.96,
            "centroid_separation": 0.09,
            "membership_p10": 0.61,
            "density_persistence": 0.06,
        }
        self.assertEqual(cluster_passes_policy(passing), (True, ()))
        for key, reason in (
            ("cohesion_mean_cosine", "cohesion_below_minimum"),
            ("centroid_separation", "separation_below_minimum"),
            ("membership_p10", "membership_below_minimum"),
            ("density_persistence", "stability_below_minimum"),
        ):
            failing = {**passing, key: 0.0}
            self.assertEqual(cluster_passes_policy(failing), (False, (reason,)))
        self.assertEqual(
            cluster_passes_policy({**passing, "density_persistence": None}),
            (False, ("stability_below_minimum",)),
        )

    def test_question_scope_evaluation_never_mixes_questions_or_exposes_text(self):
        evidence = [
            EvidenceUnit(**{**item.__dict__, "question_text": "Question one"})
            for item in self.evidence[:2]
        ] + [
            EvidenceUnit(**{**item.__dict__, "question_text": "Question two"})
            for item in self.evidence[2:]
        ]
        with patch(
            "triage_processor.taxonomy_experiment.hdbscan_clusters",
            side_effect=[
                ClusterResult("hdbscan", (0, 0), {"min_cluster_size": 2}, (0.9, 0.8)),
                ClusterResult("hdbscan", (0, 0), {"min_cluster_size": 2}, (0.7, 0.7)),
            ],
        ):
            report = evaluate_question_scopes(
                evidence, "answer-only", parameter_grid=[(2, 1)]
            )
        self.assertEqual([scope["evidence_count"] for scope in report["scopes"]], [2, 2])
        self.assertNotIn("Question one", str(report))
