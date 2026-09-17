import unittest

from triage_processor.taxonomy_quality import (
    THRESHOLDS,
    THRESHOLD_VERSION,
    attestation_input_sha256,
    evaluate_computed_gate,
)


class TaxonomyQualityTests(unittest.TestCase):
    def test_computed_gate_accepts_exact_threshold_values(self):
        passed, failures = evaluate_computed_gate({
            "snapshot_completeness": THRESHOLDS["minimum_snapshot_completeness"],
            "noise_rate": THRESHOLDS["maximum_noise_rate"],
            "topic_acceptance_rate": THRESHOLDS["minimum_topic_acceptance_rate"],
            "duplicate_topic_rate": THRESHOLDS["maximum_duplicate_topic_rate"],
        })
        self.assertTrue(passed)
        self.assertEqual(failures, ())

    def test_computed_gate_reports_each_failed_aggregate(self):
        passed, failures = evaluate_computed_gate({
            "snapshot_completeness": .5,
            "noise_rate": .5,
            "topic_acceptance_rate": .5,
            "duplicate_topic_rate": .5,
        })
        self.assertFalse(passed)
        self.assertEqual(failures, (
            "snapshot_incomplete", "noise_rate_exceeded",
            "topic_acceptance_rate_low", "duplicate_topic_rate_exceeded",
        ))

    def test_attestation_hash_binds_metrics_policy_and_version(self):
        metrics = {
            "snapshot_completeness": 1.0, "noise_rate": .2,
            "topic_acceptance_rate": .9, "duplicate_topic_rate": .0,
        }
        self.assertEqual(attestation_input_sha256(metrics), attestation_input_sha256(dict(metrics)))
        self.assertNotEqual(
            attestation_input_sha256(metrics),
            attestation_input_sha256({**metrics, "noise_rate": .3}),
        )
        self.assertTrue(THRESHOLD_VERSION)
