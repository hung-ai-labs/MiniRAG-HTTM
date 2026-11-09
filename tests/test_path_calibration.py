"""Scale-free scores on fixed C1 candidates, retaining original graph signals."""
import copy
import math
import os
import unittest
from unittest.mock import patch
from minirag.path_calibration import local_mean_factors
from minirag.operate import kwd2chunk


class PathCalibrationTest(unittest.TestCase):
    def test_conserved_budget_scale_invariance_and_empty_singleton(self):
        path=['a','b','c'];scores={'a':2.,'b':3.,'c':5.}
        factors=local_mean_factors(path,scores)
        self.assertAlmostEqual(math.fsum(factors.values()),len(path))
        self.assertTrue(all(0<=v<=len(path) for v in factors.values()))
        for scale in (1e-200,1e200):
            scaled=local_mean_factors(path,{c:s*scale for c,s in scores.items()})
            for c in path:self.assertAlmostEqual(scaled[c],factors[c])
        self.assertEqual(local_mean_factors([],{}),{})
        self.assertEqual(local_mean_factors(['a'],{'a':1e-300}),{'a':1.})

    def test_invalid_or_missing_scores_do_not_silently_fall_back(self):
        for values in ({'a':0.},{'a':-1.},{'a':float('nan')},{'a':float('inf')}):
            with self.assertRaises(ValueError):local_mean_factors(['a'],values)
        with self.assertRaises(KeyError):local_mean_factors(['a'],{})
        with self.assertRaises(ValueError):local_mean_factors(['a','a'],{'a':1.})

    def test_equal_scores_recover_C1_despite_arbitrary_seed_units(self):
        groups={'topic':[{'Score':.6,'Path':['a','b'],'PathChunkScores':{'a':1e-9,'b':1e-9}},
                         {'Score':.5,'Path':['c'],'PathChunkScores':{'c':1e9}}]}
        original=copy.deepcopy(groups)
        env={'MINIRAG_PATH_SCORE_CALIBRATION':'','MINIRAG_PATH_SCORE_FLOW':'0','MINIRAG_CHUNK_CUT':''}
        with patch.dict(os.environ,env):
            baseline=kwd2chunk(groups,[],3)
            os.environ.update(MINIRAG_PATH_SCORE_FLOW='1',MINIRAG_PATH_SCORE_CALIBRATION='local_mean')
            calibrated=kwd2chunk(groups,[],3)
        self.assertEqual(baseline,['a','b','c'])
        self.assertEqual(calibrated,baseline)
        self.assertEqual(groups,original)

    def test_relative_scores_change_ranks_and_original_boost_scope_stays_active(self):
        groups={'topic':[{'Score':.6,'Path':['a','b'],'PathChunkScores':{'a':1.,'b':9.}},
                         {'Score':.5,'Path':['c'],'PathChunkScores':{'c':.001}}]}
        with patch.dict(os.environ,{'MINIRAG_PATH_SCORE_FLOW':'1','MINIRAG_PATH_SCORE_CALIBRATION':'local_mean',
                                    'MINIRAG_CHUNK_CUT':''}):
            self.assertEqual(kwd2chunk(groups,[],3),['b','c','a'])
            self.assertEqual(kwd2chunk(groups,['a'],3),['b','a','c'])
            groups['topic'][0]['PathChunkScores']={'a':9.,'b':1.}
            self.assertEqual(kwd2chunk(groups,[],3),['a','c','b'])

    def test_score_flow_is_required(self):
        with patch.dict(os.environ,{'MINIRAG_PATH_SCORE_FLOW':'0','MINIRAG_PATH_SCORE_CALIBRATION':'local_mean'}):
            with self.assertRaisesRegex(ValueError,'PATH_SCORE_FLOW'):kwd2chunk({},[],3)


class FixedC1SelectionTest(unittest.IsolatedAsyncioTestCase):
    async def test_P2_reweights_reference_IDs_without_reordering_them(self):
        from minirag.path_affinity import project_with_affinity
        from path_test_fixtures import Graph
        class Vectors:
            async def score_ids(self, query, ids):return [{'id':c,'distance':.5} for c in ids]
        entries={'A':{'Score':.6,'Path':{('A','B'):[1.,1],('A','C'):[20.,1]}}}
        pairs={('A','B'):[('A','B')],('A','C'):[('A','C')]}
        kw={'valid':{'a','b','c','ab','ac'},'chunk_vectors':Vectors()}
        original=await project_with_affinity(copy.deepcopy(entries),Graph(),pairs,'q',2,**kw)
        trace={}
        fixed=await project_with_affinity(copy.deepcopy(entries),Graph(),pairs,'q',2,
            reference_answers=['B'],diagnostics=trace,**kw)
        self.assertEqual(original['A']['Path'],['ac','a'])
        self.assertEqual(fixed['A']['Path'],['ab','a'])
        self.assertEqual(fixed['A']['Path'],trace['reference_candidates']['A'])
        self.assertLess(fixed['A']['PathChunkScores']['ab'],fixed['A']['PathChunkScores']['a'])

    async def test_pipeline_guard_rejects_calibration_without_fixed_selection(self):
        from minirag.operate import _build_mini_query_context
        from minirag.base import QueryParam
        with patch.dict(os.environ,{'MINIRAG_PATH_SCORE_CALIBRATION':'local_mean',
                                    'MINIRAG_PATH_SELECTION':'','MINIRAG_PATH_SCORE_FLOW':'1'}):
            with self.assertRaisesRegex(ValueError,'fixed C1-affinity selection'):
                await _build_mini_query_context([],[],'q',*([None]*7),QueryParam())


if __name__=='__main__':unittest.main()
