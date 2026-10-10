import unittest
from unittest.mock import patch

from triage_processor.taxonomy_quality import (
    THRESHOLDS, THRESHOLD_VERSION, attestation_input_sha256, evaluate_computed_gate,
)
from triage_processor.taxonomy_stage_quality import QualityFacts


class TaxonomyQualityTests(unittest.TestCase):
    def metrics(self, **changes):
        return {"canonical_topic_count": 1, "evidence_count": 100,
                "evidence_with_topic_count": 2, "evidence_without_topic_count": 98,
                "integrity_failures": [], **changes}

    def test_partial_coverage_rejections_and_zero_themes_are_not_blockers(self):
        passed, failures = evaluate_computed_gate(self.metrics(
            reconciled_theme_count=0, noise_rate=.98, topic_acceptance_rate=.01,
            duplicate_topic_rate=.99, rejected_topic_count=99))
        self.assertTrue(passed)
        self.assertEqual(failures, ())
        self.assertEqual(THRESHOLDS["minimum_canonical_topic_count"], 1)

    def test_full_coverage_passes(self):
        self.assertEqual(evaluate_computed_gate(self.metrics(
            evidence_with_topic_count=100, evidence_without_topic_count=0)), (True, ()))

    def test_integrity_missing_topics_and_arithmetic_fail(self):
        passed, failures = evaluate_computed_gate(self.metrics(
            canonical_topic_count=0, evidence_without_topic_count=99,
            integrity_failures=["processing_unfinished", "model_trace_missing"]))
        self.assertFalse(passed)
        self.assertEqual(failures, ("processing_unfinished", "model_trace_missing",
                                    "canonical_topics_missing", "coverage_inconsistent"))

    def test_negative_missing_boolean_and_empty_counts_fail_closed(self):
        for changes in ({"evidence_with_topic_count": -1, "evidence_without_topic_count":101},
                        {"evidence_count": True}, {"evidence_count": None},
                        {"evidence_count":0,"evidence_with_topic_count":0,"evidence_without_topic_count":0}):
            with self.subTest(changes=changes):
                self.assertFalse(evaluate_computed_gate(self.metrics(**changes))[0])

    def test_counts_and_rates_keep_evidence_separate_from_attempts(self):
        facts = QualityFacts(10, 8, 2, 5, 1, 0, 0, canonical_topic_count=1,
                             evidence_with_topic_count=2, evidence_without_topic_count=8,
                             question_count=3, submission_count=2, rejected_topic_count=4)
        self.assertEqual(facts.signals()["topic_acceptance_rate"], .2)
        self.assertEqual(facts.signals()["evidence_without_topic_count"], 8)
        self.assertTrue(evaluate_computed_gate(facts.signals())[0])

    def test_attestation_hash_binds_every_input_policy_and_version(self):
        metrics = self.metrics()
        digest = attestation_input_sha256(metrics)
        self.assertEqual(digest, attestation_input_sha256(dict(reversed(list(metrics.items())))))
        for key, value in metrics.items():
            changed = ["model_trace_missing"] if isinstance(value,list) else value+1
            self.assertNotEqual(digest, attestation_input_sha256({**metrics,key:changed}))
        with patch("triage_processor.taxonomy_stage_quality.THRESHOLD_VERSION", "future"):
            self.assertNotEqual(digest, attestation_input_sha256(metrics))
        self.assertEqual(THRESHOLD_VERSION, "taxonomy-release-gate-v3")
