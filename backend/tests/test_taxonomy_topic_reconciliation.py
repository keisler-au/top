import json
import unittest

from triage_processor.taxonomy_topic_reconciliation import (
    MAX_PACKET_TOPICS,
    MAX_AUDIT_JSON_BYTES,
    _bounded_request,
    ProvisionalTopic,
    ReconciliationDraft,
    ReconciliationGroup,
    SYSTEM_PROMPT,
    canonical_partition,
    isolated_topic_ids,
    shortlist_packets,
    validate_reconciliation_response,
)


def topic(identifier, question_id, name, centroid):
    return ProvisionalTopic(
        id=identifier,
        question_id=question_id,
        name=name,
        description=f"Description for {name}",
        support_count=2,
        centroid=tuple(centroid),
    )


class TopicShortlistTests(unittest.TestCase):
    def test_only_cross_question_plausible_neighbors_enter_packets(self):
        topics = [
            topic(1, 10, "Affordable housing", (1.0, 0.0)),
            topic(2, 11, "Housing affordability", (0.99, 0.01)),
            topic(3, 10, "Public parks", (0.0, 1.0)),
            topic(4, 12, "Bus reliability", (-1.0, 0.0)),
        ]
        packets = shortlist_packets(topics)
        self.assertEqual(packets, ((1, 2),))
        self.assertEqual(isolated_topic_ids(topics, packets), (3, 4))

    def test_packets_are_deterministic_and_bounded_for_many_questions(self):
        topics = [
            topic(identifier, identifier, "Shared concept", (1.0, 0.0))
            for identifier in range(1, 301)
        ]
        forward = shortlist_packets(topics)
        reverse = shortlist_packets(list(reversed(topics)))
        self.assertEqual(forward, reverse)
        self.assertGreater(len(forward), 0)
        self.assertLessEqual(len(forward), 300)
        self.assertTrue(all(2 <= len(packet) <= MAX_PACKET_TOPICS for packet in forward))
        self.assertGreaterEqual(len({topic.question_id for topic in topics}), 50)

    def test_same_name_can_shortlist_when_contextual_geometry_differs(self):
        packets = shortlist_packets([
            topic(1, 1, "Childcare costs", (1.0, 0.0)),
            topic(2, 2, "Childcare costs", (0.0, 1.0)),
        ])
        self.assertEqual(packets, ((1, 2),))

    def test_serialized_packets_keep_whole_utf8_evidence_within_bound(self):
        topics = [ProvisionalTopic(
            id=i, question_id=i, name=f"Concept {i}", description="Description",
            support_count=2, centroid=(1.0, 0.0), question_text="What matters?",
            evidence=({"evidence_id": i, "answer_text": "界" * 20000},
                      {"evidence_id": i + 100, "answer_text": "Small answer"}),
        ) for i in range(1, 13)]
        packet = _bounded_request(topics)
        self.assertLessEqual(len(json.dumps(packet, ensure_ascii=False, sort_keys=True,
            separators=(",", ":")).encode()), MAX_AUDIT_JSON_BYTES)
        self.assertEqual(packet, _bounded_request(topics))
        self.assertTrue(all(t["evidence"] == [] for t in packet["topics"]))

    def test_metadata_overflow_fails_closed(self):
        oversized = ProvisionalTopic(1, 1, "Concept", "Description", 2, (1.0, 0.0),
            question_text="界" * 20000)
        with self.assertRaisesRegex(ValueError, "serialized bound"):
            _bounded_request([oversized])


class ReconciliationValidationTests(unittest.TestCase):
    def test_valid_fields_cannot_exceed_the_complete_audit_bound(self):
        groups = [{"provisional_topic_ids": [i, i + 1], "name": f"Concept {i}",
                   "description": "界" * 2000, "rationale": "界" * 2000}
                  for i in range(1, 13, 2)]
        draft, errors = validate_reconciliation_response(
            {"groups": groups, "no_merge_topic_ids": []}, set(range(1, 13)))
        self.assertIsNone(draft)
        self.assertIn("response_serialized_bound_exceeded", errors)

    def test_structural_shape_rejects_boolean_ids_bad_names_and_extra_fields(self):
        responses = [
            {"groups": [], "no_merge_topic_ids": [True, 2]},
            {"groups": [], "no_merge_topic_ids": [1, 2], "extra": "unsafe"},
            {"groups": [{"provisional_topic_ids": [1, 2], "name": "word " * 9,
                "description": "Description", "rationale": "Rationale"}], "no_merge_topic_ids": []},
        ]
        for response in responses:
            self.assertIsNone(validate_reconciliation_response(response, {1, 2})[0])

    def test_valid_equivalent_group_and_explicit_non_merge(self):
        draft, errors = validate_reconciliation_response(
            {
                "groups": [{
                    "provisional_topic_ids": [2, 1],
                    "name": "Childcare affordability",
                    "description": "The affordability of childcare.",
                    "rationale": "Both topics concern the same specific service cost.",
                }],
                "no_merge_topic_ids": [3],
            },
            {1, 2, 3},
        )
        self.assertEqual(errors, ())
        self.assertEqual(draft.groups[0].provisional_topic_ids, (1, 2))

    def test_related_homonymous_and_opposing_positions_are_model_decisions(self):
        self.assertIn("Opposing", SYSTEM_PROMPT)
        self.assertIn("related concepts", SYSTEM_PROMPT)
        self.assertIn("different meanings", SYSTEM_PROMPT)
        draft, errors = validate_reconciliation_response(
            {"groups": [], "no_merge_topic_ids": [1, 2, 3]}, {1, 2, 3}
        )
        self.assertIsNotNone(draft)
        self.assertEqual(errors, ())

    def test_unknown_duplicate_overlap_and_incomplete_partitions_fail(self):
        cases = [
            ({"groups": [], "no_merge_topic_ids": [1, 9]}, "unknown_provisional_topic"),
            ({"groups": [{
                "provisional_topic_ids": [1, 2], "name": "One concept",
                "description": "Description", "rationale": "Rationale",
            }], "no_merge_topic_ids": [2, 3]}, "duplicate_provisional_topic"),
            ({"groups": [], "no_merge_topic_ids": [1]}, "incomplete_partition"),
        ]
        for response, expected in cases:
            with self.subTest(expected=expected):
                draft, errors = validate_reconciliation_response(response, {1, 2, 3})
                self.assertIsNone(draft)
                self.assertIn(expected, errors)

    def test_transitive_contradiction_fails_before_materialization(self):
        merge_12 = ReconciliationDraft((ReconciliationGroup(
            (1, 2), "Concept", "Description", "Rationale"
        ),), (3,))
        merge_23 = ReconciliationDraft((ReconciliationGroup(
            (2, 3), "Concept", "Description", "Rationale"
        ),), (1,))
        with self.assertRaisesRegex(ValueError, "transitive"):
            canonical_partition((1, 2, 3), (merge_12, merge_23))

    def test_non_overlapping_groups_form_complete_partition(self):
        draft = ReconciliationDraft(
            (ReconciliationGroup((1, 2), "Concept", "Description", "Rationale"),),
            (3,),
        )
        self.assertEqual(canonical_partition((1, 2, 3), (draft,)), ((1, 2), (3,)))


if __name__ == "__main__":
    unittest.main()
