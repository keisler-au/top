import inspect
import unittest

from triage_processor.taxonomy_themes import CandidateTopic, infer_run, neighbourhoods, validate_theme


class TaxonomyThemesTests(unittest.TestCase):
 def test_resumed_stage_does_not_infer_an_already_attempted_neighbourhood(self):
  source=inspect.getsource(infer_run)
  self.assertIn('already_attempted',source)
  self.assertIn('ON CONFLICT (taxonomy_run_id, neighbourhood_key) DO NOTHING',source)

 def test_subset_and_overlap(self):
  topics=[CandidateTopic(1,'A','a',2,(1.,0.)),CandidateTopic(2,'B','b',2,(.99,.1)),CandidateTopic(3,'C','c',2,(0.,1.))]
  self.assertEqual([len(x) for x in neighbourhoods(topics,.9)],[2,2,1])
  self.assertTrue(validate_theme({'create_theme':True,'name':'Theme','description':'d','rationale':'r','topic_revision_ids':[1]}, {1,2})[0])
 def test_rejects_out_of_scope_link(self):
  self.assertIn('outside', validate_theme({'create_theme':True,'name':'x','description':'x','rationale':'x','topic_revision_ids':[3]}, {1,2})[1][0])
