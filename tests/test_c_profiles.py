"""Current profile naming and environment isolation; no model/API calls."""
import ast
import os
from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve().parents[1]/'reproduce/path'
sys.path.insert(0,str(HERE))
from c_profiles import PROFILES,profile_env,apply_profile
from benchmark_c import restore


class CurrentProfilesTest(unittest.TestCase):
    def test_only_current_names_and_new_C1_are_selectable(self):
        self.assertEqual(PROFILES,('C0','C1','C2','C3'))
        self.assertEqual(profile_env('C1')['MINIRAG_PATH_PROJECTION'],'affinity')
        for name in ('C1_old','C3_old','C3_path_mean','P2_fixed_raw','C1_affinity'):
            with self.assertRaises(ValueError):profile_env(name)

    def test_old_P2_is_removed_from_main_profiles(self):
        c2,c3=profile_env('C2'),profile_env('C3')
        self.assertTrue(all(profile_env(p)['MINIRAG_PATH_SCORE']=='' for p in PROFILES))
        self.assertEqual(c2['MINIRAG_PATH_SCORE_CALIBRATION'],'local_mean')
        self.assertEqual(c3['MINIRAG_PATH_SCORE_CALIBRATION'],'')
        self.assertEqual(c3['MINIRAG_PATH_PROJECTION'],'p0_relation_lift')
        self.assertEqual(c3['MINIRAG_PATH_SELECTION'],'c1_affinity')

    def test_profiles_clear_inherited_experiments_without_touching_credentials(self):
        env={'MINIRAG_CHUNK_FUSION':'rrf','MINIRAG_PATH_SCORE_NORMALIZATION':'path_mean',
             'MINIRAG_GRAPH_FLOW':'full','GEMINI_API_KEY':'private-value'}
        apply_profile('C1',env)
        for key in ('MINIRAG_CHUNK_FUSION','MINIRAG_PATH_SCORE_NORMALIZATION','MINIRAG_GRAPH_FLOW'):
            self.assertEqual(env[key],'')
        self.assertEqual(env['GEMINI_API_KEY'],'private-value')
        self.assertNotIn('GEMINI_API_KEY',profile_env('C1'))
        saved=env.copy()
        with self.assertRaises(ValueError):apply_profile('old',env)
        self.assertEqual(env,saved)

    def test_current_profiles_preserve_fixed_candidates_and_choose_correct_scores(self):
        data={'entries':{'A':{'Score':.6,'score_dtype':'float32','Path':['b','a'],
            'P0':{'b':.2,'a':.1},'P2':{'b':.3,'a':.05}}},'groups':{'topic':['A']}}
        c1,c2=[restore(data,p) for p in ('C1','C2')]
        self.assertEqual(c2['topic'][0]['Path'],['b','a'])
        self.assertNotIn('PathChunkScores',c1['topic'][0])
        self.assertEqual(c2['topic'][0]['PathChunkScores'],data['entries']['A']['P0'])
        with self.assertRaises(ValueError):restore(data,'C3')



if __name__=='__main__':unittest.main()
