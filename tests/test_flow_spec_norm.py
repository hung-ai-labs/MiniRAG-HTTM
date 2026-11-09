"""Graph repair phase 2 switches (reproduce/graph_repair/PHASE2_REGISTRATION.md); offline, no models."""
import copy
import os
import unittest
from unittest.mock import patch

from minirag.operate import kwd2chunk, path2chunk
from minirag.prompt import GRAPH_FIELD_SEP as SEP

SOURCES = {"S": ["s1"], "HUB": ["h1", "h2", "h3", "h4"], "SPEC": ["x"]}


class Graph:
    async def get_node(self, name):
        ids = SOURCES.get(name, [f"{name.lower()}c"])
        return {"source_id": SEP.join(ids), "description": SEP.join(f"{name} {i}" for i in ids)}


PATHS = {"S": {"Score": 0.5, "Path": {("S", "HUB"): [0, 0], ("S", "SPEC"): [0, 0]}}}


class FlowSpecNormTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"MINIRAG_PATH_SCORE_FLOW": "1", "MINIRAG_PATH2CHUNK_FIX": "0",
                                           "MINIRAG_FLOW_SPEC": "", "MINIRAG_FLOW_NORM": "",
                                           "MINIRAG_DIAG_PATH_SCORE": ""})
        self.env.start()
        self.addCleanup(self.env.stop)

    async def run_paths(self, paths=PATHS, spec="", norm=""):
        os.environ["MINIRAG_FLOW_SPEC"], os.environ["MINIRAG_FLOW_NORM"] = spec, norm
        return (await path2chunk(copy.deepcopy(paths), Graph(), {}, "q", max_chunks=3))["S"]

    async def test_off_counts_every_chunk_once_per_path(self):
        d = await self.run_paths()
        self.assertEqual(d["Path"][0], "s1")
        self.assertNotIn("x", d["Path"])  # hub chunks h1, h2 win the tie by insertion order
        self.assertEqual(d["PathChunkScores"], {"s1": 2, "h1": 1, "h2": 1})

    async def test_idf_prefers_chunks_of_specific_nodes(self):
        d = await self.run_paths(spec="idf")
        self.assertEqual(d["Path"], ["s1", "x", "h1"])
        self.assertEqual(d["PathChunkScores"], {"s1": 2.0, "x": 1.0, "h1": 0.25})

    async def test_max_norm_scales_best_chunk_to_one(self):
        d = await self.run_paths(spec="idf", norm="max")
        self.assertEqual(d["PathChunkScores"], {"s1": 1.0, "x": 0.5, "h1": 0.125})
        plain = await self.run_paths(norm="max")
        self.assertEqual(plain["Path"], (await self.run_paths())["Path"])  # norm never changes the picked IDs

    async def test_isolated_seed_with_idf(self):
        d = await self.run_paths({"S": {"Score": 0.5, "Path": {}}}, spec="idf", norm="max")
        self.assertEqual(d["PathChunkScores"], {"s1": 1.0})
        self.assertEqual(kwd2chunk({"k": [d]}, [], 3), ["s1"])

    async def test_norm_removes_path_count_scale_across_seeds(self):
        many = {("S", "HUB"): [0, 0]}
        many.update({("S", f"N{i}"): [0, 0] for i in range(50)})
        few = await self.run_paths(norm="max")
        lots = await self.run_paths({"S": {"Score": 0.5, "Path": many}}, norm="max")
        self.assertEqual(max(few["PathChunkScores"].values()), 1.0)
        self.assertEqual(max(lots["PathChunkScores"].values()), 1.0)


if __name__ == "__main__":
    unittest.main()
