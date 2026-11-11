import unittest
from unittest.mock import patch
from minirag.production import profile_env, apply_profile, main
from minirag.temporal_rrf import validate_profile, budget_trace
from minirag.temporal import overlay, parse_query, rank_temporal
from minirag.operate import _rrf_fuse, kwd2chunk
from minirag.utils import encode_string_by_tiktoken, truncate_list_by_token_size


class ProductionProfileTests(unittest.TestCase):
    def test_default_profile_enables_exact_pilot_composition(self):
        env=profile_env();validate_profile(env,60,4000)
        self.assertEqual(env['MINIRAG_EXTRACTIVE_CONTEXT'],'neighbors')
        self.assertEqual(env['MINIRAG_PATH2CHUNK_FIX'],'0')
        self.assertEqual(env['MINIRAG_PATH_SCORE_FLOW'],'0')
        self.assertTrue(env['MINIRAG_RECOMP_MODEL_DIR'].endswith('/.models/recomp-hotpotqa'))

    def test_baseline_differs_only_in_selection(self):
        a=profile_env('baseline');b=profile_env('production')
        self.assertEqual([k for k in a if a[k]!=b[k]],['MINIRAG_EXTRACTIVE_CONTEXT'])
        self.assertEqual(profile_env('c0')['MINIRAG_CHUNK_FUSION'],'')
        self.assertEqual(profile_env('c0')['MINIRAG_TEMPORAL'],'0')

    def test_profile_clears_experimental_environment_and_preserves_backend(self):
        env={'MINIRAG_PATH_SCORE':'old','MINIRAG_GRAPH_ARM':'TS',
             'GEMINI_API_BASE':'local','MINIRAG_RECOMP_MODEL_DIR':'/model'}
        apply_profile(environ=env)
        self.assertEqual(env['MINIRAG_PATH_SCORE'],'')
        self.assertEqual(env['MINIRAG_GRAPH_ARM'],'')
        self.assertEqual(env['GEMINI_API_BASE'],'local')
        self.assertEqual(env['MINIRAG_RECOMP_MODEL_DIR'],'/model')
        with self.assertRaises(ValueError):apply_profile('bad',environ=env)

    def test_printing_profile_never_downloads_or_runs_qa(self):
        with patch('sys.argv',['profile']),patch('builtins.print'),\
             patch('minirag.production.prepare_model') as download,\
             patch('minirag.production.os.execvpe') as run:
            main();download.assert_not_called();run.assert_not_called()

    def test_incompatible_scorer_and_budget_are_rejected(self):
        env=profile_env()
        for k,v in [('MINIRAG_PATH_SCORE_FLOW','1'),('MINIRAG_SOURCE_EVENT_TIME','full'),
                    ('MINIRAG_CHUNK_FUSION','vector'),('MINIRAG_RERANK','ce1')]:
            with self.assertRaises(ValueError):validate_profile({**env,k:v},60,4000)
        with self.assertRaises(ValueError):validate_profile(env,30,4000)
        with self.assertRaises(ValueError):validate_profile(env,60,2000)


class CompositionTests(unittest.TestCase):
    def test_score_side_channel_does_not_change_c0_ranking(self):
        data={'Alice':[{'Score':.7,'Path':['a','b']},{'Score':.4,'Path':['b','c']}]}
        original=kwd2chunk(data,['a'],30);scores={}
        self.assertEqual(original,kwd2chunk(data,['a'],30,scores_out=scores))
        self.assertEqual(original,sorted(scores,key=scores.get,reverse=True))

    def test_source_time_uses_document_time_not_referenced_event_time(self):
        docs={'d':{'content':'Time: 20260501_10:00\nA: We meet on June 4.'}}
        chunks={'c':{'full_doc_id':'d'}}
        by,years=overlay(docs,chunks)
        self.assertEqual(by['time:day:2026-05-01'],['c'])
        self.assertNotIn('time:day:2026-06-04',by)
        self.assertEqual(parse_query('What happened on May 1?',years),('time:day:2026-05-01',))
        self.assertEqual(parse_query('What happened on May 1?',{2025,2026}),())

    def test_temporal_and_rrf_keep_both_branches_and_merge_ids(self):
        ids,selected=rank_temporal({'g':3},{'time:day:2026-05-01':['t']},
            ['time:day:2026-05-01'],{'t':2},['d'],limit=30)
        self.assertEqual(set(ids),{'g','t'})
        self.assertEqual(selected['time:day:2026-05-01'],['t'])
        fused=_rrf_fuse(ids,['g','d'])
        self.assertEqual(len(fused),3);self.assertIn('t',fused);self.assertIn('d',fused)
        self.assertEqual(len(_rrf_fuse([f'g{i}' for i in range(30)],
                                     [f'd{i}' for i in range(30)])),60)

    def test_budget_trace_matches_a1_prefix_even_after_overflow(self):
        texts={'a':'one two three','b':'one two three four five','c':'six'}
        budget=len(encode_string_by_tiktoken(texts['a']))+len(encode_string_by_tiktoken(texts['b']))-1
        t=budget_trace(['a','missing','b','c'],['a','b','c'],texts,
                       ['a','b'],['b','c'],['a'],['b'],budget)
        expected=truncate_list_by_token_size(['a','b','c'],key=lambda c:texts[c],max_token_size=budget)
        self.assertEqual(t['expected_A1_chunk_ids'],expected)
        self.assertEqual(expected,['a']);self.assertEqual(t['missing_text_ids'],['missing'])
        self.assertFalse(t['candidates'][-1]['kept_by_A1'])


if __name__=='__main__':unittest.main()
