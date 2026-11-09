"""Người 2 -- MINIRAG_PACK_*: xếp lại theo điểm/token^alpha và first-fit. Dữ liệu giả, không model."""
from pathlib import Path
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from minirag.operate import _pack_alpha, _pack_fill, first_fit_indices, kwd2chunk, pack_reorder


class PackReorderTest(unittest.TestCase):
    def test_alpha_zero_effect_keeps_order_when_density_equal(self):
        ids = ["a", "b", "c"]
        self.assertEqual(pack_reorder(ids, {"a": 3, "b": 2, "c": 1}, {"a": 30, "b": 20, "c": 10}, 1.0), ids)

    def test_density_prefers_short_chunk_with_lower_score(self):
        scores = {"long": 10.0, "short": 6.0}
        tokens = {"long": 1000, "short": 100}
        self.assertEqual(pack_reorder(["long", "short"], scores, tokens, 1.0), ["short", "long"])

    def test_half_alpha_is_between_score_order_and_density(self):
        # x: 10 điểm / 200 token, y: 6 điểm / 100 token. alpha=0,5: 0,707 > 0,6 giữ x trước; alpha=1: 0,05 < 0,06 đưa y lên
        scores = {"x": 10.0, "y": 6.0}
        self.assertEqual(pack_reorder(["x", "y"], scores, {"x": 200, "y": 100}, 0.5), ["x", "y"])
        self.assertEqual(pack_reorder(["x", "y"], scores, {"x": 200, "y": 100}, 1.0), ["y", "x"])

    def test_stable_on_ties(self):
        ids = ["p", "q", "r"]
        out = pack_reorder(ids, {c: 1.0 for c in ids}, {c: 50 for c in ids}, 1.0)
        self.assertEqual(out, ids)

    def test_same_set_only_reordered(self):
        ids = ["a", "b", "c", "d"]
        out = pack_reorder(ids, {"a": 4, "b": 3, "c": 2, "d": 1}, {"a": 900, "b": 50, "c": 400, "d": 10}, 1.0)
        self.assertEqual(sorted(out), sorted(ids))

    def test_zero_tokens_do_not_divide_by_zero(self):
        self.assertEqual(pack_reorder(["a"], {"a": 1.0}, {"a": 0}, 1.0), ["a"])


class FirstFitTest(unittest.TestCase):
    def test_matches_prefix_cut_when_nothing_skippable(self):
        sizes = [100, 100, 100]
        keep = first_fit_indices(sizes, 1000)
        self.assertEqual(keep, [0, 1, 2])

    def test_skips_overflowing_chunk_and_continues(self):
        sizes = [300, 900, 200, 100]
        self.assertEqual(first_fit_indices(sizes, 700), [0, 2, 3])

    def test_never_exceeds_budget(self):
        sizes = [400, 350, 300, 250, 200]
        keep = first_fit_indices(sizes, 1000)
        self.assertLessEqual(sum(sizes[i] for i in keep), 1000)

    def test_zero_budget_keeps_nothing(self):
        self.assertEqual(first_fit_indices([1, 2], 0), [])


class SwitchTest(unittest.TestCase):
    def test_off_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MINIRAG_PACK_ALPHA", None)
            os.environ.pop("MINIRAG_PACK_FILL", None)
            self.assertIsNone(_pack_alpha())
            self.assertFalse(_pack_fill())

    def test_only_registered_values_accepted(self):
        for v, want in (("1", 1.0), ("0.5", 0.5)):
            with patch.dict(os.environ, {"MINIRAG_PACK_ALPHA": v}):
                self.assertEqual(_pack_alpha(), want)
        for bad in ("0.7", "2", "abc"):
            with patch.dict(os.environ, {"MINIRAG_PACK_ALPHA": bad}):
                with self.assertRaises(ValueError):
                    _pack_alpha()
        with patch.dict(os.environ, {"MINIRAG_PACK_FILL": "yes"}):
            with self.assertRaises(ValueError):
                _pack_fill()
        with patch.dict(os.environ, {"MINIRAG_PACK_FILL": "firstfit"}):
            self.assertTrue(_pack_fill())


class Kwd2ChunkScoreOutTest(unittest.TestCase):
    def _entities(self):
        d1 = {"Score": 0.8, "Path": ["c1", "c2"], "PathChunkScores": {"c1": 1.0, "c2": 1.0}}
        d2 = {"Score": 0.5, "Path": ["c3"], "PathChunkScores": {"c3": 1.0}}
        return {"kw": [d1, d2]}

    def test_score_out_does_not_change_returned_order(self):
        base = kwd2chunk(self._entities(), [], 3)
        out = {}
        again = kwd2chunk(self._entities(), [], 3, score_out=out)
        self.assertEqual(base, again)
        self.assertEqual(set(out), set(again))
        scores = [out[c] for c in again]
        self.assertEqual(scores, sorted(scores, reverse=True))


if __name__ == "__main__":
    unittest.main()
