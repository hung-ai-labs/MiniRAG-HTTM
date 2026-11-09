"""Offline causal checks for the opt-in path-score wiring; no models or APIs."""
import copy
import json
import os
import tempfile
import unittest
import numpy as np
from pathlib import Path
from unittest.mock import patch

from minirag.base import QueryParam
from minirag.operate import _build_mini_query_context, kwd2chunk, path2chunk
from minirag.path_rerank import score_reasoning_paths_weighted
from minirag.utils import cal_path_score_list, edge_vote_path


class Graph:
    async def get_node(self, name):
        return {"source_id": {"A": "a", "B": "b"}.get(name, ""),
                "description": f"Description of {name}"}

    async def get_neighbors_within_k_hops(self, name, hops):
        return {"A": [("A", "A2", "A3")], "B": [("B", "B2")]}[name]

    async def get_node_from_types(self, types):
        return [{"entity_name": "B2"}]


class Vector:
    def __init__(self, rows):
        self.rows = rows

    async def query(self, *args, **kwargs):
        return copy.deepcopy(self.rows)


class Chunks:
    async def get_by_id(self, cid):
        return {"content": ("alpha " if cid == "a" else "beta ") * 25}


class PathScoreFlowTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Keep the tests independent of any experiment settings in the shell.
        self.env = patch.dict(os.environ, {
            "MINIRAG_GRAPH_FLOW": "",
            "MINIRAG_PATH_SCORE_FLOW": "0", "MINIRAG_PATH2CHUNK_FIX": "0",
            "MINIRAG_PATH_SCORE": "", "MINIRAG_PATH_PRUNE": "",
            "MINIRAG_CHUNK_FUSION": "", "MINIRAG_CHUNK_CUT": "",
            "MINIRAG_LEEF": "", "MINIRAG_RERANK": "", "MINIRAG_CONTEXT_LOG": "",
            "MINIRAG_DIAG_LOG": "", "MINIRAG_DIAG_PATH_SCORE": "",
            "MINIRAG_TRUNCATE_SOURCES": "1", "MINIRAG_MAX_TOKEN_TEXT_UNIT": "30",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        # Synthetic tokens avoid tiktoken's first-run network download. The real
        # truncation function still runs, with identical token costs in both arms.
        for target in ("minirag.utils.encode_string_by_tiktoken",
                       "minirag.operate.encode_string_by_tiktoken"):
            tokenizer = patch(target, side_effect=lambda text, **kw: text.split())
            tokenizer.start()
            self.addCleanup(tokenizer.stop)

    async def project(self, paths, flow):
        os.environ["MINIRAG_PATH_SCORE_FLOW"] = str(int(flow))
        return await path2chunk(copy.deepcopy(paths), Graph(), {}, "question", max_chunks=3)

    async def test_last_path_bug_is_bypassed_only_when_enabled(self):
        paths = {"A": {"Score": 0.6, "Path": {("A",): [0, 0], ("B",): [9, 0]}}}
        legacy = await self.project(paths, False)
        repaired = await self.project(paths, True)
        self.assertEqual(legacy["A"]["Path"], ["b"])
        self.assertNotIn("PathChunkScores", legacy["A"])
        self.assertEqual(repaired["A"]["Path"], ["b", "a"])
        self.assertEqual(repaired["A"]["PathChunkScores"], {"b": 10, "a": 1})

    async def test_weights_change_global_rank_with_identical_local_ids(self):
        # Both seed lists have one unchanged ID: only their weights can affect rank.
        candidates = {
            "A": {"Score": 0.6, "Path": [("A", "A2", "A3")]},
            "B": {"Score": 0.5, "Path": [("B", "B2")]},
        }
        ranks, projected = [], []
        for scorer in (cal_path_score_list, score_reasoning_paths_weighted):
            edged, pairs = edge_vote_path(scorer(candidates, ["B2"]), [])
            data = await self.project(edged, True)
            projected.append([d["Path"] for d in data.values()])
            ranks.append(kwd2chunk({"topic": list(data.values())}, [], 2))
        self.assertEqual(projected[0], projected[1])
        self.assertEqual(ranks, [["a", "b"], ["b", "a"]])

    async def test_isolated_seed_has_fallback_scores(self):
        data = await self.project({"A": {"Score": 0.6, "Path": {}}}, True)
        self.assertEqual(data["A"]["PathChunkScores"], {"a": 1})
        self.assertEqual(kwd2chunk({"topic": [data["A"]]}, [], 3), ["a"])

    async def test_legacy_ignores_side_channel(self):
        data = {"topic": [{"Score": 1, "Path": ["a", "b"],
                           "PathChunkScores": {"a": 1, "b": 100}}]}
        self.assertEqual(kwd2chunk(data, [], 2), ["a", "b"])

    async def test_missing_scores_fail_instead_of_silently_losing_signal(self):
        os.environ["MINIRAG_PATH_SCORE_FLOW"] = "1"
        with self.assertRaises(KeyError):
            kwd2chunk({"topic": [{"Score": 1, "Path": ["a"]}]}, [], 2)

    async def context(self):
        return await _build_mini_query_context(
            ["topic"], ["PERSON"], "question", Graph(), None,
            Vector([{"entity_name": "A", "distance": np.float32(0.6)},
                    {"entity_name": "B", "distance": np.float32(0.5)}]),
            Vector([{"src_id": "unused", "tgt_id": "unused2"}]),
            Vector([]), Chunks(), None, QueryParam(),
        )

    async def test_scores_reach_sources_after_budget_cut_and_log(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "context.jsonl"
            os.environ.update({"MINIRAG_PATH_SCORE_FLOW": "1", "MINIRAG_CONTEXT_LOG": str(log)})
            p0 = await self.context()
            os.environ["MINIRAG_PATH_SCORE"] = "weighted"
            p2 = await self.context()
            records = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual([r["chunk_ids"] for r in records], [["a"], ["b"]])
        self.assertNotEqual(p0, p2)
        self.assertTrue(all(r["path_score_flow"] for r in records))
        self.assertGreater(records[1]["path_chunk_scores"]["B"]["b"],
                           records[0]["path_chunk_scores"]["B"]["b"])

    async def test_disabled_flow_preserves_legacy_context(self):
        p0 = await self.context()
        os.environ["MINIRAG_PATH_SCORE"] = "weighted"
        p2 = await self.context()
        self.assertEqual(p0, p2)
        self.assertIn("alpha", p0)
        self.assertNotIn("beta", p0)

    async def test_diagnostic_disabled_writes_nothing_and_keeps_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "diagnostic.jsonl"
            os.environ["MINIRAG_DIAG_LOG"] = ""
            first = await self.context()
            second = await self.context()
            self.assertEqual(first, second)
            self.assertFalse(path.exists())

    async def test_graph_discarding_fusion_is_rejected_before_retrieval(self):
        os.environ["MINIRAG_PATH_SCORE_FLOW"] = "1"
        for mode in ("vector", "vector_bm25"):
            os.environ["MINIRAG_CHUNK_FUSION"] = mode
            with self.assertRaisesRegex(ValueError, "discard graph ranking"):
                await self.context()


if __name__ == "__main__":
    unittest.main()
