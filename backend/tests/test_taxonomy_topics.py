import hashlib
import inspect
import json
import unittest

from triage_processor.taxonomy_stages import MAX_AUDIT_JSON_BYTES, bounded_audit_object
from triage_processor.taxonomy_topics import (
    MAX_STRUCTURAL_ATTEMPTS,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    _request_context,
    materialize_run,
    validate_topic_response,
)


class TaxonomyTopicsTests(unittest.TestCase):
    def response(self, **overrides):
        value = {
            "name": "Access fees",
            "description": "Charges that limit access.",
            "evidence_ids": [11, 12],
        }
        value.update(overrides)
        return value

    def test_prompt_has_versioned_concept_and_traceability_contract(self):
        prompt = " ".join(SYSTEM_PROMPT.split())
        self.assertEqual(PROMPT_VERSION, "partial-topic-naming/v1")
        self.assertIn("concept, not whether respondents support, oppose", prompt)
        self.assertIn("Do not broaden the concept into a theme", prompt)
        self.assertIn("exact ordered evidence_ids", prompt)

    def test_synonyms_and_inflections_are_not_lexically_rejected(self):
        draft, errors = validate_topic_response(
            self.response(), set(), expected_evidence_ids=(11, 12)
        )
        self.assertEqual(draft.name, "Access fees")
        self.assertEqual(draft.description, "Charges that limit access.")
        self.assertEqual(errors, ())

    def test_rejects_malformed_blank_oversized_duplicate_and_wrong_links(self):
        cases = (
            ({"name": "Only two fields", "description": "Missing links"}, "response_fields_mismatch"),
            (self.response(name=" "), "name_blank"),
            (self.response(name="word " * 9), "name_word_count_out_of_bounds"),
            (self.response(description="x" * 2001), "description_too_long"),
            (self.response(name=" Access Fees "), "duplicate_topic"),
            (self.response(evidence_ids=[12, 11]), "evidence_ids_mismatch"),
            (self.response(evidence_ids=[11, True]), "evidence_ids_not_integer_list"),
        )
        for response, expected in cases:
            with self.subTest(expected=expected):
                draft, errors = validate_topic_response(
                    response, {"access fees"}, expected_evidence_ids=(11, 12)
                )
                self.assertIsNone(draft)
                self.assertIn(expected, errors)

    def test_bounded_retry_and_provisional_storage_are_explicit(self):
        source = inspect.getsource(materialize_run)
        self.assertEqual(MAX_STRUCTURAL_ATTEMPTS, 2)
        self.assertIn("taxonomy_provisional_topics", source)
        self.assertNotIn("INSERT INTO topics", source)
        self.assertNotIn("_content_terms", source)

    def test_maximum_packet_audit_retains_verifiable_hash_when_truncated(self):
        representatives = [
            {"evidence_id": index, "answer_text": "é" * 600, "selection_kind": "all"}
            for index in range(1, 41)
        ]
        request = _request_context(
            {
                "cluster_key": "question:1:hdbscan:0",
                "policy_version": "partial-topic-policy/v1",
                "member_count": 40,
                "packet_serialized_bytes": 32768,
                "question_id": 1,
                "question_source": "fixture",
                "form_key": "form",
                "question_key": "question",
                "question_version": 1,
                "question_text": "What should change?",
            },
            representatives,
            attempt_number=1,
            prior_errors=(),
        )
        encoded = json.dumps(
            request, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        bounded = bounded_audit_object(request)
        self.assertLessEqual(
            len(json.dumps(bounded, ensure_ascii=False, separators=(",", ":")).encode("utf-8")),
            MAX_AUDIT_JSON_BYTES,
        )
        self.assertTrue(bounded["_audit_truncated"])
        self.assertEqual(bounded["original_sha256"], hashlib.sha256(encoded).hexdigest())
