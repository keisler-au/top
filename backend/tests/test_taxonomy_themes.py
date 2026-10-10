import json
import unittest

from triage_processor.taxonomy_themes import (
    CandidateTopic, neighbourhoods, validate_theme, theme_request,
)


class TaxonomyThemesTests(unittest.TestCase):
    def topics(self):
        return [CandidateTopic(1,'Bus reliability','Reliability',2,(1.,0.)),
                CandidateTopic(2,'Bus fares','Fares',2,(.99,.1)),
                CandidateTopic(3,'Childcare','Childcare',2,(0.,1.))]

    def test_related_topics_form_one_group_and_isolated_topics_bypass_model(self):
        topics=self.topics()
        self.assertEqual([[x.revision_id for x in group] for group in neighbourhoods(topics,.9)],[[1,2]])
        self.assertEqual(neighbourhoods(topics[2:],.9),[])
        self.assertEqual(neighbourhoods(list(reversed(topics)),.9),neighbourhoods(topics,.9))

    def test_scale_neighborhoods_are_bounded_deterministic_and_include_every_anchor(self):
        topics=[CandidateTopic(i,str(i),'Description',2,(1.,0.)) for i in range(100)]
        groups=neighbourhoods(topics,.82)
        self.assertTrue(all(2<=len(group)<=5 for group in groups))
        self.assertEqual(groups,neighbourhoods(list(reversed(topics)),.82))
        self.assertEqual({x.revision_id for group in groups for x in group},set(range(100)))
        self.assertLessEqual(len(groups),100)

    def test_packet_keeps_whole_unicode_evidence_within_bound(self):
        topics=[CandidateTopic(i,'Concept','Description',2,(1.,0.),
                ({'evidence_id':i,'answer_text':'界'*20000},)) for i in range(5)]
        request=theme_request(topics)
        self.assertTrue(all(x['evidence']==[] for x in request['topics']))
        self.assertLessEqual(len(json.dumps(request,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()),32768)

    def test_theme_requires_two_distinct_supplied_canonical_topics(self):
        raw={'create_theme':True,'name':'Transport access','description':'d','rationale':'r','topic_revision_ids':[1,2]}
        self.assertTrue(validate_theme(raw,{1,2})[0])
        for ids in ([1],[1,1],[1,3],[True,2]):
            self.assertFalse(validate_theme({**raw,'topic_revision_ids':ids},{1,2})[0])
        self.assertTrue(validate_theme({**raw,'create_theme':False,'topic_revision_ids':[]},{1,2})[0])
        self.assertFalse(validate_theme({**raw,'create_theme':False},{1,2})[0])
