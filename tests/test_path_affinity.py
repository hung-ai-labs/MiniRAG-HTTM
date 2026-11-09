"""Query conditioning must retain absolute relevance and graph contributions."""
import copy
import os
import unittest
from unittest.mock import patch
from minirag.path_affinity import condition_evidence


class PathAffinityTest(unittest.TestCase):
    def test_relevance_can_rescue_evidence_before_original_local_cap(self):
        entries={'seed':{'Score':.6,'Path':['noise','answer'],'PathChunkScores':{'noise':.6,'answer':.4}}}
        saved=copy.deepcopy(entries)
        out=condition_evidence(entries,{'noise':.1,'answer':.9},max_chunks=1)
        self.assertEqual(out['seed']['Path'],['answer'])
        self.assertAlmostEqual(out['seed']['PathChunkScores']['answer'],.36)
        self.assertEqual(entries,saved)

    def test_absolute_affinity_does_not_cancel_in_disconnected_single_source_seeds(self):
        entries={s:{'Score':.6,'Path':[c],'PathChunkScores':{c:1.}} for s,c in [('A','a'),('B','b')]}
        out=condition_evidence(entries,{'a':.1,'b':.9})
        self.assertEqual(out['A']['PathChunkScores']['a'],.1)
        self.assertEqual(out['B']['PathChunkScores']['b'],.9)

    def test_graph_mass_remains_causal_with_identical_query_affinities(self):
        entries={'s':{'Score':.6,'Path':['a','b'],'PathChunkScores':{'a':.8,'b':.2}}}
        a=condition_evidence(entries,{'a':.5,'b':.5})
        entries['s']['PathChunkScores']={'a':.2,'b':.8}
        b=condition_evidence(entries,{'a':.5,'b':.5})
        self.assertEqual(a['s']['Path'],['a','b'])
        self.assertEqual(b['s']['Path'],['b','a'])
        self.assertLessEqual(sum(b['s']['PathChunkScores'].values()),1)

    def test_missing_or_invalid_vectors_fail_instead_of_implicit_fallback(self):
        entries={'s':{'Score':.6,'Path':['a'],'PathChunkScores':{'a':1.}}}
        with self.assertRaises(KeyError):condition_evidence(entries,{})
        for bad in (float('nan'),float('inf'),1.1):
            with self.assertRaises(ValueError):condition_evidence(entries,{'a':bad})


class PathAffinityIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_production_projection_keeps_both_provenance_channels_and_C1_interface(self):
        from minirag.operate import path2chunk
        from path_test_fixtures import Graph
        class Vectors:
            async def score_ids(self, query, ids):
                return [{'id': c, 'distance': {'a':.1, 'b':.9, 'ab':.2}[c]} for c in ids]
        entries={'A':{'Score':.6,'Path':{('A','B'):[1.,1]}}}
        env={'MINIRAG_PATH_PROJECTION':'affinity','MINIRAG_PATH2CHUNK_FIX':'1',
             'MINIRAG_PATH_SCORE_FLOW':'1','MINIRAG_P2_ENHANCE':'','MINIRAG_PATH_SCORE_NORMALIZATION':''}
        with patch.dict(os.environ,env):
            trace={}
            scored=await path2chunk(copy.deepcopy(entries),Graph(),{('A','B'):[('A','B')]},'q',3,
                valid_chunks={'a','b','ab'},chunk_vectors=Vectors(),diagnostics=trace)
            self.assertEqual(scored['A']['Path'],['b','ab','a'])
            self.assertEqual(trace['node_mass'],.5)
            self.assertEqual(trace['edge_mass'],.5)
            os.environ['MINIRAG_PATH_SCORE_FLOW']='0'
            unweighted=await path2chunk(copy.deepcopy(entries),Graph(),{('A','B'):[('A','B')]},'q',3,
                valid_chunks={'a','b','ab'},chunk_vectors=Vectors())
        self.assertEqual(unweighted['A']['Path'],scored['A']['Path'])
        self.assertNotIn('PathChunkScores',unweighted['A'])

    async def test_production_guard_rejects_discarded_graph_or_conflicting_mechanism(self):
        from minirag.operate import _build_mini_query_context
        from minirag.base import QueryParam
        base={'MINIRAG_PATH_PROJECTION':'affinity','MINIRAG_PATH2CHUNK_FIX':'1',
              'MINIRAG_PATH_SCORE':'weighted','MINIRAG_GRAPH_FLOW':'','MINIRAG_P2_ENHANCE':'',
              'MINIRAG_PATH_SCORE_NORMALIZATION':'','MINIRAG_PATH_PRUNE':'','MINIRAG_CHUNK_CUT':'',
              'MINIRAG_LEEF':'','MINIRAG_RERANK':'','MINIRAG_CHUNK_FUSION':''}
        for name,value in [('MINIRAG_GRAPH_FLOW','full'),('MINIRAG_CHUNK_FUSION','vector'),
                           ('MINIRAG_PATH_SCORE_NORMALIZATION','path_mean'),('MINIRAG_PATH2CHUNK_FIX','0')]:
            with patch.dict(os.environ,{**base,name:value}):
                with self.assertRaisesRegex(ValueError,'intact P0/P2 graph flows'):
                    await _build_mini_query_context([],[],'q',*([None]*7),QueryParam())


if __name__=='__main__':unittest.main()
