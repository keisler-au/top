import unittest

from triage_processor.taxonomy_stage_quality import QualityFacts


class TaxonomyStageQualityTests(unittest.TestCase):
    def test_quality_signals_are_computed_from_counts(self):
        facts = QualityFacts(10, 7, 3, 4, 3, 2, 1)
        self.assertEqual(facts.signals()["noise_rate"], 0.3)
        self.assertEqual(facts.signals()["topic_acceptance_rate"], 0.75)

    def test_empty_counts_have_defined_rates(self):
        facts = QualityFacts(0, 0, 0, 0, 0, 0, 0)
        self.assertEqual(facts.signals()["noise_rate"], 0.0)
        self.assertEqual(facts.signals()["topic_acceptance_rate"], 0.0)
