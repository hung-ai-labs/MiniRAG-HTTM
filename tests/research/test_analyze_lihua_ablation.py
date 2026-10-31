"""Offline tests for the registered LiHua ablation v2 analysis on synthetic judged runs."""

import csv
import importlib.util
import json
from pathlib import Path
import random
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ala", ROOT / "reproduce/research/analyze_lihua_ablation.py")
ala = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ala)

N = 120
ACC = {"L-C0": 0.55, "L-B2": 0.80, "L-VEC": 0.70, "L-BM25": 0.78, "L-B1": 0.66, "L-NOENT": 0.79, "L-NOGRAPH": 0.79}


def build(tmp, seeds=(101, 202, 303), state="completed"):
    root = Path(tmp) / "run"
    questions, gold = Path(tmp) / "q.csv", Path(tmp) / "gold.jsonl"
    types = ["Single"] * 100 + ["Null"] * 20
    with open(questions, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Question", "Gold Answer", "Type", "query_id"])
        for i in range(N):
            w.writerow([f"q{i}", "Yes", types[i], f"lh-{i:04d}"])
    with open(gold, "w", encoding="utf-8") as f:
        for i in range(N):
            ev = None if types[i] == "Null" else ([] if i == 5 else [{"chunk_ids": [f"c{i}", f"d{i}"]}])
            f.write(json.dumps({"query_id": f"lh-{i:04d}", "evidence": ev}) + "\n")
    for s in seeds:
        (root).mkdir(parents=True, exist_ok=True)
        (root / f"judge_s{s}_SESSION.json").write_text(json.dumps({"state": state}))
        for arm, p in ACC.items():
            d = root / f"{arm}_s{s}" / "judge"
            d.mkdir(parents=True)
            rng = random.Random(f"{arm}{s}")
            with open(d / "per_question.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, lineterminator="\n")
                w.writerow(["query_id", "Type", "pass1", "pass2", "pass3", "majority"])
                for i in range(N):
                    label = "accurate" if rng.random() < p else "error"
                    w.writerow([f"lh-{i:04d}", types[i], label, label, label, label])
            with open(root / f"{arm}_s{s}" / "context.jsonl", "w", encoding="utf-8") as f:
                for i in range(N):
                    ids = [f"c{i}", f"d{i}"] if arm == "L-B2" else [f"c{i}"]
                    f.write(json.dumps({"query": f"q{i}", "chunk_ids": ids}) + "\n")
    return root, questions, gold


class AnalyzeTests(unittest.TestCase):
    def test_holm_matches_hand_computation(self):
        adj = ala.holm({"a": 0.01, "b": 0.04, "c": 0.03})
        self.assertAlmostEqual(adj["a"], 0.03)
        self.assertAlmostEqual(adj["c"], 0.06)
        self.assertAlmostEqual(adj["b"], 0.06)  # monotone: never below the previous step

    def test_registered_contrasts_decisions_and_recall(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, q, gold = build(tmp)
            r = ala.analyse(root, [101, 202, 303], q, gold)
            self.assertEqual(set(r["contrasts"]), {"L1", "L2", "L3", "L4", "L5", "L6", "L7"})
            self.assertTrue(r["decisions"]["L1"]["confirmed"])
            self.assertEqual(r["decisions"]["L1"]["direction"], "B2 better")
            for c in ala.FAMILY:
                for s in (101, 202, 303):
                    x = r["contrasts"][c]["per_seed"][s]["primary_accurate"]
                    self.assertGreaterEqual(x["p_holm"], x["p"])  # Holm never lowers a p-value
            self.assertIn("stage_d_direction_replicated", r["decisions"]["L4"])
            self.assertEqual(r["questions_without_mapped_evidence"], ["lh-0005"])
            rec = r["arms"]["L-B2"]["per_seed"][101]["evidence_recall"]
            self.assertEqual((rec["micro"], rec["full_evidence"], rec["n_questions"]), (100.0, 100.0, 99))
            self.assertEqual(r["arms"]["L-C0"]["per_seed"][101]["evidence_recall"]["micro"], 50.0)
            self.assertIn("L1", ala.report(r))

    def test_refuses_seeds_without_a_completed_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, q, gold = build(tmp, state="interrupted")
            with self.assertRaises(SystemExit):
                ala.analyse(root, [101, 202, 303], q, gold)
            ala.analyse(root, [101, 202, 303], q, gold, allow_incomplete=True)  # smoke only


if __name__ == "__main__":
    unittest.main()
