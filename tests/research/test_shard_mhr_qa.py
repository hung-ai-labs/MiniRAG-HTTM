"""Offline tests for splitting questions into shards and merging answers back."""

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("shard_mhr_qa", ROOT / "reproduce/research/shard_mhr_qa.py")
shard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shard)

ROWS = [{"Question": f"q{i}", "Gold Answer": "Yes"} for i in range(11)]


class ShardTests(unittest.TestCase):
    def test_split_then_merge_restores_input_order(self):
        parts = shard.split(ROWS, 4)
        self.assertEqual(sorted(r["Question"] for p in parts for r in p), sorted(r["Question"] for r in ROWS))
        answers = [[dict(r, minirag="a-" + r["Question"]) for r in p] for p in parts]
        merged = shard.merge(ROWS, parts, answers)
        self.assertEqual([m["minirag"] for m in merged], ["a-" + r["Question"] for r in ROWS])

    def test_merge_rejects_misaligned_or_short_shards(self):
        parts = shard.split(ROWS, 3)
        answers = [[dict(r, minirag="x") for r in p] for p in parts]
        answers[1][0], answers[1][1] = answers[1][1], answers[1][0]
        with self.assertRaisesRegex(ValueError, "does not match"):
            shard.merge(ROWS, parts, answers)
        answers = [[dict(r, minirag="x") for r in p] for p in parts]
        answers[2].pop()
        with self.assertRaisesRegex(ValueError, "answers for"):
            shard.merge(ROWS, parts, answers)


if __name__ == "__main__":
    unittest.main()
