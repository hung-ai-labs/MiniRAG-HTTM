import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'reproduce/path'))
from c_profiles import apply_profile,PROFILES,profile_env
from benchmark_c import restore


class P0ProfileTest(unittest.IsolatedAsyncioTestCase):
    async def test_main_profiles_never_select_old_weighted_P2(self):
        self.assertTrue(all(profile_env(p)['MINIRAG_PATH_SCORE']=='' for p in PROFILES))
        self.assertEqual(profile_env('C3')['MINIRAG_PATH_PROJECTION'],'p0_relation_lift')

    async def test_new_C3_rejects_old_P2_configuration_before_retrieval(self):
        from minirag.operate import _build_mini_query_context
        from minirag.base import QueryParam
        with patch.dict(os.environ):
            apply_profile('C3');os.environ['MINIRAG_PATH_SCORE']='weighted'
            with self.assertRaisesRegex(ValueError,'requires P0'):
                await _build_mini_query_context([],[],'q',*([None]*7),QueryParam())

    async def test_new_C3_replay_uses_new_method_scores(self):
        data={'path_method':'p0_relation_lift','entries':{'A':{'Score':.6,'score_dtype':'float32',
            'Path':['a'],'PathChunkScores':{'a':.8}}},'groups':{'topic':['A']}}
        self.assertEqual(restore(data,'C3')['topic'][0]['PathChunkScores'],{'a':.8})
        data.pop('path_method')
        with self.assertRaises(ValueError):restore(data,'C3')


if __name__=='__main__':unittest.main()
