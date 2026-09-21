import unittest

from triage_processor.taxonomy_snapshots import (
    SnapshotRequest,
    _source_hash,
    _stage_input_hash,
    _validation_counts,
    validate_snapshot_request,
)


def request(**overrides):
    values = {
        "idempotency_key": "snapshot-1",
        "configuration": {"version": "v1", "clustering": {"min_cluster_size": 3}},
        "embedding_model": "embed-v1",
        "embedding_representation": "question-answer",
        "embedding_dimension": 3,
        "clustering_model": "hdbscan-v1",
        "topic_model": "topic-v1",
        "theme_model": "theme-v1",
        "topic_prompt_version": "topic-prompt-v1",
        "theme_prompt_version": "theme-prompt-v1",
    }
    values.update(overrides)
    return SnapshotRequest(**values)


class TaxonomySnapshotTests(unittest.TestCase):
    def test_snapshot_admits_the_current_ready_for_analysis_lifecycle_state(self):
        from triage_processor.taxonomy_snapshots import _CANONICAL_EVIDENCE_SQL

        self.assertIn("'ready_for_analysis'", _CANONICAL_EVIDENCE_SQL)
        self.assertIn("'completed'", _CANONICAL_EVIDENCE_SQL)
    def test_requires_explicit_versioned_configuration(self):
        with self.assertRaisesRegex(ValueError, "configuration.version"):
            validate_snapshot_request(request(configuration={"clustering": {}}))
        with self.assertRaisesRegex(ValueError, "configuration.clustering"):
            validate_snapshot_request(request(configuration={"version": "v1"}))
        with self.assertRaisesRegex(ValueError, "embedding_dimension"):
            validate_snapshot_request(request(embedding_dimension=0))

    def test_validation_counts_are_bounded_and_detect_all_admission_failures(self):
        rows = [
            {
                "original_input_id": 1,
                "segment_input_id": None,
                "embedding_id": 1,
                "embedding_model": "wrong-model",
                "embedding_representation": "answer-only",
                "embedding_dimension": 2,
            },
            {
                "original_input_id": 1,
                "segment_input_id": None,
                "embedding_id": 1,
                "embedding_model": "embed-v1",
                "embedding_representation": "question-answer",
                "embedding_dimension": 3,
            },
            {
                "original_input_id": 2,
                "segment_input_id": 3,
                "embedding_id": None,
                "embedding_model": None,
                "embedding_representation": None,
                "embedding_dimension": None,
            },
        ]
        counts = _validation_counts(rows, request())
        self.assertEqual(counts["canonical_evidence"], 3)
        self.assertEqual(counts["missing_embedding"], 1)
        self.assertEqual(counts["model_mismatch"], 1)
        self.assertEqual(counts["representation_mismatch"], 1)
        self.assertEqual(counts["dimension_mismatch"], 1)
        self.assertEqual(counts["duplicate_canonical_target"], 1)
        self.assertEqual(counts["duplicate_embedding"], 1)
        self.assertEqual(_validation_counts([], request())["zero_evidence"], 1)

    def test_source_hash_is_deterministic_and_does_not_depend_on_response_text(self):
        evidence = [
            {
                "original_input_id": 1,
                "segment_input_id": None,
                "embedding_id": 8,
                "embedding_model": "embed-v1",
                "embedding_representation": "question-answer",
                "embedding_dimension": 3,
            },
            {
                "original_input_id": 2,
                "segment_input_id": 9,
                "embedding_id": 10,
                "embedding_model": "embed-v1",
                "embedding_representation": "question-answer",
                "embedding_dimension": 3,
            },
        ]
        self.assertEqual(_source_hash(evidence), _source_hash(list(evidence)))
        self.assertRegex(_source_hash(evidence), "^[0-9a-f]{64}$")

    def test_stage_input_hash_binds_the_stage_to_source_and_configuration(self):
        source_hash = "a" * 64
        configuration_hash = "b" * 64
        self.assertEqual(
            _stage_input_hash(source_hash, configuration_hash, "clustering"),
            _stage_input_hash(source_hash, configuration_hash, "clustering"),
        )
        self.assertNotEqual(
            _stage_input_hash(source_hash, configuration_hash, "clustering"),
            _stage_input_hash(source_hash, configuration_hash, "quality"),
        )
