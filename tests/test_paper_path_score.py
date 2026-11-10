"""Small synthetic checks for opt-in Eq. (3); no index or network."""
import copy
import os
import unittest
from unittest.mock import patch

import networkx as nx

from minirag.operate import path2chunk
from minirag.paper_edge_score import edge_vote_path_paper
from minirag.paper_path_score import select_paper_paths
from minirag.utils import edge_vote_path


class Graph:
    async def get_node(self, name):
        return {"source_id": {"A": "a", "B": "b", "C": "c", "D": "d"}[name],
                "description": name}


class PaperPathScoreTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"MINIRAG_PATH_SELECT": "", "MINIRAG_PATH_SCORE_FLOW": "0",
                                   "MINIRAG_PATH2CHUNK_FIX": "0", "MINIRAG_FLOW_SPEC": "",
                                   "MINIRAG_FLOW_NORM": "", "MINIRAG_PATH_SELECT_LOG": ""})
        env.start()
        self.addCleanup(env.stop)

    def test_top_k_ties_factor_and_determinism(self):
        original = {"A": {"Score": 0.25, "Path": {
            ("A", "C"): [1, 0], ("A", "B"): [1, 0], ("A", "D"): [0, 0]}}}
        saved = copy.deepcopy(original)
        first, _ = select_paper_paths(original, {}, k=2)
        second, _ = select_paper_paths(original, {}, k=2)
        self.assertEqual(first, second)
        self.assertEqual(original, saved)
        self.assertEqual(list(first["A"]["Path"]), [("A", "B"), ("A", "C")])
        self.assertEqual(list(first["A"]["PathPaperScores"].values()), [0.5, 0.5])

    async def test_off_uses_last_path_on_uses_all_selected_weighted_paths(self):
        paths = {"A": {"Score": 0.5, "Path": {
            ("A", "B"): [0, 0], ("A", "C"): [2, 0]}}}
        legacy = await path2chunk(copy.deepcopy(paths), Graph(), {}, "q", max_chunks=3)
        self.assertEqual(legacy["A"]["Path"], ["a", "c"])
        self.assertNotIn("PathPaperScores", legacy["A"])
        os.environ["MINIRAG_PATH_SELECT"] = "paper"
        selected, edges = select_paper_paths(paths, {}, k=2)
        paper = await path2chunk(selected, Graph(), edges, "q", max_chunks=3)
        self.assertEqual(paper["A"]["Path"][0], "a")
        self.assertEqual(paper["A"]["Path"], ["a", "c", "b"])

    def test_composes_with_eq2_weighted_edges(self):
        graph = nx.Graph([("A", "B"), ("A", "C")])
        paths = {"A": {"Score": 0.6, "Path": {("A", "B"): [0], ("A", "C"): [0]}}}
        code, _ = edge_vote_path(paths, [{"src_id": "A", "tgt_id": "B"}])
        code_sel, _ = select_paper_paths(code, {}, k=2)
        eq2, eq2_edges = edge_vote_path_paper(paths, graph, ["A", "B"], n_select=1, k=1)
        paper_sel, kept_edges = select_paper_paths(eq2, eq2_edges, k=2)
        self.assertEqual(code_sel["A"]["PathPaperScores"][("A", "B")], 1.2)
        self.assertAlmostEqual(paper_sel["A"]["PathPaperScores"][("A", "B")], 1.8)
        self.assertIn(("A", "B"), kept_edges)


if __name__ == "__main__":
    unittest.main()
