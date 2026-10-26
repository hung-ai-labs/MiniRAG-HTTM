"""Offline tests for the registered paired comparison."""

import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("compare_mhr", ROOT / "reproduce/research/compare_mhr.py")
cmp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cmp)


def rows(majorities, types=None):
    return {f"q{i}": {"query_id": f"q{i}", "Type": (types or ["comparison"] * len(majorities))[i], "majority": m}
            for i, m in enumerate(majorities)}


class CompareTests(unittest.TestCase):
    def test_discordant_pairs_and_secondary_direction(self):
        a = rows(["accurate", "error", "neither", "accurate", "no_majority", "error"])
        b = rows(["accurate", "accurate", "accurate", "error", "accurate", "neither"])
        r = cmp.compare(a, b)
        prim, sec = r["primary_accurate"], r["secondary_error"]
        # up: q1 error->accurate, q2 neither->accurate, q4 no_majority->accurate (no_majority is not
        # accurate); q5 error->neither stays not accurate. down: q3.
        self.assertEqual((prim["up"], prim["down"]), (3, 1))
        self.assertEqual(prim["p"], cmp.mcnemar_p(3, 1))
        self.assertEqual((sec["fewer_errors"], sec["more_errors"]), (2, 1))  # q1, q5 fewer; q3 more
        self.assertEqual(prim["diff"], round(100 * 4 / 6, 2) - round(100 * 2 / 6, 2))

    def test_bootstrap_is_seeded_paired_and_brackets_the_difference(self):
        a = rows(["accurate"] * 50 + ["error"] * 50)
        b = rows(["accurate"] * 70 + ["error"] * 30)
        r1, r2 = cmp.compare(a, b), cmp.compare(a, b)
        lo, hi = r1["primary_accurate"]["ci95"]
        self.assertEqual(r1, r2)
        self.assertTrue(lo <= 20 <= hi)
        self.assertTrue(r1["primary_accurate"]["noninferior_at_-3"])
        same = cmp.compare(a, a)["primary_accurate"]
        self.assertEqual((same["ci95"], same["p"]), ([0.0, 0.0], 1.0))  # identical runs: no spread at all

    def test_type_filter_and_refusals(self):
        a = rows(["accurate", "error"], ["null", "comparison"])
        b = rows(["error", "error"], ["null", "comparison"])
        self.assertEqual(cmp.compare(a, b, ["null"])["n"], 1)
        with self.assertRaisesRegex(ValueError, "same questions"):
            cmp.compare(a, rows(["accurate"]))
        with tempfile.TemporaryDirectory() as tmp:
            with open(Path(tmp) / "per_question.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["query_id", "Type", "pass1", "pass2", "pass3", "majority"])
                w.writerow(["q0", "null", "accurate", "parse_failed", "accurate", "incomplete"])
            with self.assertRaisesRegex(ValueError, "without a complete verdict"):
                cmp.load(tmp)


if __name__ == "__main__":
    unittest.main()
