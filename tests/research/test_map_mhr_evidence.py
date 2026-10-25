"""Offline tests for locating evidence facts in chunks."""

import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("map_mhr_evidence", ROOT / "reproduce/research/map_mhr_evidence.py")
mapper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mapper)

CHUNKS = [("c1", mapper.norm("Alpha beta gamma delta. Shared overlap text")),
          ("c2", mapper.norm("shared overlap text. Epsilon zeta eta theta."))]


class LocateTests(unittest.TestCase):
    def test_inside_one_or_both_chunks(self):
        self.assertEqual(mapper.locate("beta  GAMMA", CHUNKS), (["c1"], "inside"))
        self.assertEqual(mapper.locate("Shared overlap", CHUNKS), (["c1", "c2"], "inside"))

    def test_straddling_fact_lists_both_chunks(self):
        self.assertEqual(mapper.locate("gamma delta. shared overlap text. epsilon zeta", CHUNKS),
                         (["c1", "c2"], "spans"))

    def test_absent_fact_is_reported_not_guessed(self):
        self.assertEqual(mapper.locate("iota kappa", CHUNKS), ([], "missing"))


if __name__ == "__main__":
    unittest.main()
