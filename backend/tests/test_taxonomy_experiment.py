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
    evaluate_representation,
    partition_agreement,
    read_dataset,
    select_representatives,
    theme_neighbourhood_requests,
    threshold_components,
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
