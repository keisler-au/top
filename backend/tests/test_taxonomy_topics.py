import inspect
import unittest

from triage_processor.taxonomy_topics import materialize_run, validate_topic_response


class TaxonomyTopicsTests(unittest.TestCase):
    def test_resumed_stage_does_not_name_an_already_attempted_cluster(self):
        source = inspect.getsource(materialize_run)
        self.assertIn("taxonomy_topic_naming_attempts AS attempt", source)
        self.assertIn("ON CONFLICT (taxonomy_run_id, cluster_candidate_id, attempt_number)", source)

    def test_accepts_literal_topic_shape(self):
        draft, errors = validate_topic_response({"name": "Cost barriers", "description": "Respondents mention cost as a barrier."}, set())
        self.assertEqual(draft.name, "Cost barriers")
        self.assertEqual(errors, ())

    def test_rejects_duplicate_or_blank_topic(self):
        draft, errors = validate_topic_response({"name": " Cost Barriers ", "description": "x"}, {"cost barriers"})
        self.assertIsNone(draft)
        self.assertIn("duplicates", errors[0])

    def test_requires_literal_support_and_bounded_granularity_when_examples_are_available(self):
        draft, errors = validate_topic_response(
            {"name": "Cost barriers", "description": "Respondents describe cost concerns."},
            set(), representative_texts=("The cost is too high",),
        )
        self.assertIsNotNone(draft)
        self.assertFalse(errors)
        draft, errors = validate_topic_response(
            {"name": "A very long topic name that exceeds the permitted granularity", "description": "Unrelated outcome claim."},
            set(), representative_texts=("The cost is too high",),
        )
        self.assertIsNone(draft)
        self.assertTrue(any("granular" in error for error in errors))
        self.assertTrue(any("literal support" in error for error in errors))

    def test_rejects_a_mixed_cluster_when_a_label_only_matches_one_representative(self):
        draft, errors = validate_topic_response(
            {"name": "Cost barriers", "description": "People report cost barriers."},
            set(), representative_texts=("The cost is too high", "Staff need more training"),
        )
        self.assertIsNone(draft)
        self.assertTrue(any("cluster is mixed" in error for error in errors))
