import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reproduce" / "graph_repair" / "sim"))
from c0_sim import rank, pack


class FakeEncoder:
    def encode(self, text):
        return list(text)


class C0SimulatorTest(unittest.TestCase):
    def test_boosted_contributions_and_stable_tie(self):
        diag = {"contributions": {
            "a": [{"contribution": 2}, {"contribution": 3}],
            "b": [{"contribution": 5}],
            "c": [{"contribution": 10}],
        }}
        self.assertEqual(rank(diag), ["c", "a", "b"])

    def test_prefix_stop_and_missing_chunk(self):
        chunks = {"a": {"content": "abc"}, "b": {"content": "abcd"}, "c": {"content": "z"}}
        self.assertEqual(pack(["absent", "a", "b", "c"], chunks, 5, FakeEncoder()), ["a"])


if __name__ == "__main__":
    unittest.main()
