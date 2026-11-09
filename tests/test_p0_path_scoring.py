import copy
import unittest
from minirag.p0_path_scoring import p0_path_weights,prepare_scoring,rank_scoring


class Graph:
    async def get_node(self,n):return {'source_id':n.lower(),'description':'node '+n}
    async def get_edge(self,u,v):return {'source_id':''.join(sorted((u,v))).lower()}


class Relations:
    async def score_pairs(self,query,pairs):
        scores={('A','B'):.2,('A','C'):.8}
        return [{'src_id':u,'tgt_id':v,'distance':scores[(u,v)]} for u,v in pairs]


class Chunks:
    async def score_ids(self,query,ids):return [{'id':c,'distance':.5} for c in ids]


class P0WeightsTest(unittest.TestCase):
    def test_indexed_votes_preserve_order_duplicates_and_orientation(self):
        from minirag.utils import edge_vote_path
        paths = {'A': {'Score': .6, 'Path': {('A', 'B', 'C'): [2], ('A', 'C'): [1]}}}
        rows = [{'src_id': u, 'tgt_id': v} for u, v in
                [('B', 'A'), ('A', 'B'), ('A', 'B'), ('B', 'C'), ('C', 'A')]]
        self.assertEqual(edge_vote_path(paths, rows), edge_vote_path(paths, rows, indexed=True))

    def test_all_hops_participate_without_removing_paths(self):
        e={'A':{'Score':.6,'Path':{('A','B','C'):[0,0],('A','D'):[0,0]}}}
        w,bg,meta=p0_path_weights(e,{('A','B'):.9,('B','C'):.1,('A','D'):.6})
        self.assertAlmostEqual(w['A'][('A','B','C')],.3)
        self.assertAlmostEqual(w['A'][('A','D')],.6)
        self.assertEqual(set(w['A']),set(e['A']['Path']))
        self.assertEqual(set(bg['A'].values()),{1.})

    def test_zero_relation_fallback_is_explicit_P0(self):
        e={'A':{'Score':.6,'Path':{('A','B'):[2,1]}}}
        w,bg,meta=p0_path_weights(e,{('A','B'):0.})
        self.assertEqual(w['A'][('A','B')],4.)
        self.assertEqual(meta['fallback_seeds'],1)
        with self.assertRaises(KeyError):p0_path_weights(e,{})
        with self.assertRaises(ValueError):p0_path_weights(e,{('A','B'):float('nan')})

    def test_background_cancels_source_multiplicity_when_quality_is_equal(self):
        e={'S':{'Score':.6,'Path':['x','y'],'PathChunkScores':{'x':.9,'y':.1}}}
        bundle={'prior':copy.deepcopy(e),'background':copy.deepcopy(e),'conditioned':copy.deepcopy(e),
                'affinities':{'x':.5,'y':.5}}
        lifted=rank_scoring(bundle,2)['S']['PathChunkScores']
        raw=rank_scoring(bundle,2,'no_background')['S']['PathChunkScores']
        self.assertEqual(lifted,{'x':.5,'y':.5})
        self.assertEqual(raw,{'x':.45,'y':.05})


class P0ProjectionTest(unittest.IsolatedAsyncioTestCase):
    async def bundle(self,a=1,v=1):
        e={'A':{'Score':.6,'Path':{('A','B'):[a,v],('A','C'):[0,1]}}}
        pairs={('A','B'):[('A','B')],('A','C'):[('A','C')]}
        return await prepare_scoring(e,Graph(),pairs,'q',valid={'a','b','c','ab','ac'},
                                     chunk_vectors=Chunks(),relation_vectors=Relations())

    async def test_type_votes_and_relation_support_are_causal(self):
        bundle=await self.bundle();no_type=await self.bundle(a=0);extra_vote=await self.bundle(v=3)
        weights=rank_scoring(bundle,5)['A']['PathChunkScores']
        self.assertGreater(weights['ac'],weights['ab'])
        self.assertGreater(rank_scoring(bundle,5,'no_relation')['A']['PathChunkScores']['ab'],
                           rank_scoring(bundle,5,'no_relation')['A']['PathChunkScores']['ac'])
        self.assertNotEqual(weights,rank_scoring(no_type,5)['A']['PathChunkScores'])
        self.assertNotEqual(weights,rank_scoring(extra_vote,5)['A']['PathChunkScores'])
        for key in ('prior','background','conditioned'):
            self.assertAlmostEqual(sum(bundle[key]['A']['PathChunkScores'].values()),1.)
        self.assertIn('a',weights);self.assertIn('ab',weights)
        self.assertAlmostEqual(bundle['metadata']['node_mass'],.5)
        self.assertAlmostEqual(bundle['metadata']['edge_mass'],.5)

    async def test_all_ablation_candidate_lists_are_exact_C1_order(self):
        bundle=await self.bundle()
        paths=[rank_scoring(bundle,3,m)['A']['Path'] for m in ('full','no_relation','no_background','affinity_only')]
        self.assertTrue(all(p==paths[0] for p in paths))

    async def test_isolated_node_fallback_survives(self):
        e={'A':{'Score':.6,'Path':{}}}
        bundle=await prepare_scoring(e,Graph(),{},'q',valid={'a'},chunk_vectors=Chunks(),relation_vectors=Relations())
        self.assertEqual(rank_scoring(bundle)['A']['PathChunkScores'],{'a':.5})

    async def test_missing_relation_vectors_fail(self):
        class Missing:
            async def score_pairs(self,query,pairs):return []
        with self.assertRaisesRegex(ValueError,'missing its existing vector'):
            await prepare_scoring({'A':{'Score':.6,'Path':{('A','B'):[0,0]}}},Graph(),{},'q',
                valid={'a','b'},chunk_vectors=Chunks(),relation_vectors=Missing())


if __name__=='__main__':unittest.main()
