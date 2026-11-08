"""C0-C3 isolate Counter selection, score transmission, and the P2 scorer."""
import copy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reproduce.path.c_ablation import environment
from minirag.operate import path2chunk, kwd2chunk
from minirag.path_rerank import score_reasoning_paths_weighted
from minirag.utils import cal_path_score_list, edge_vote_path
from test_path_score_flow import Graph


class CAblationTest(unittest.IsolatedAsyncioTestCase):
    def test_matrix_and_conflicting_flags_are_cleared(self):
        for arm, expected in {"C0":("0","0",""),"C1":("1","0",""),
                              "C2":("1","1",""),"C3":("1","1","weighted")}.items():
            e=environment(arm)
            self.assertEqual(tuple(e[n] for n in ("MINIRAG_PATH2CHUNK_FIX","MINIRAG_PATH_SCORE_FLOW","MINIRAG_PATH_SCORE")),expected)
            self.assertEqual(e["MINIRAG_GRAPH_FLOW"],"")
            self.assertEqual(e["MINIRAG_P2_ENHANCE"],"")
            self.assertEqual(e["MINIRAG_MAX_TOKEN_TEXT_UNIT"],"4000")

    async def test_c1_selects_all_path_counter_without_score_transmission(self):
        paths={"A":{"Score":0.6,"Path":{("A",):[0,0],("B",):[9,0]}}}
        results=[]
        for arm in ("C0","C1"):
            with patch.dict(os.environ,environment(arm)):
                data=await path2chunk(copy.deepcopy(paths),Graph(),{},"q",max_chunks=3)
            self.assertNotIn("PathChunkScores",data["A"])
            results.append(data["A"]["Path"])
        self.assertEqual(results,[["b"],["b","a"]])

    async def test_c2_transmits_scores_with_same_selected_ids_as_c1(self):
        paths={"A":{"Score":0.6,"Path":{("A",):[0,0]}},
               "B":{"Score":0.5,"Path":{("B",):[9,0]}}}
        ranks=[]; local=[]
        for arm in ("C1","C2"):
            with patch.dict(os.environ,environment(arm)):
                data=await path2chunk(copy.deepcopy(paths),Graph(),{},"q",max_chunks=3)
                local.append([e["Path"] for e in data.values()])
                ranks.append(kwd2chunk({"topic":list(data.values())},[],2))
        self.assertEqual(local[0],local[1])
        self.assertEqual(ranks,[["a","b"],["b","a"]])

    async def test_c3_changes_only_scorer_on_the_same_repaired_flow(self):
        candidates={"A":{"Score":0.6,"Path":[("A","A2","A3")]},
                    "B":{"Score":0.5,"Path":[("B","B2")]}}
        ranks=[]
        for arm in ("C2","C3"):
            with patch.dict(os.environ,environment(arm)):
                scorer=score_reasoning_paths_weighted if arm=="C3" else cal_path_score_list
                edged,pairs=edge_vote_path(scorer(candidates,["B2"]),[])
                data=await path2chunk(edged,Graph(),pairs,"q",max_chunks=3)
                self.assertTrue(all("PathChunkScores" in e for e in data.values()))
                ranks.append(kwd2chunk({"topic":list(data.values())},[],2))
        self.assertEqual(ranks,[["a","b"],["b","a"]])


if __name__ == "__main__":
    unittest.main()
