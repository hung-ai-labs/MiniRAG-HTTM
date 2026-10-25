"""Offline tests for the frozen MultiHop-RAG dev / internal-test split."""

import contextlib
import csv
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("make_mhr_split", ROOT / "reproduce/research/make_mhr_split.py")
split = importlib.util.module_from_spec(spec)
spec.loader.exec_module(split)


def write_processed(directory, n_per_type):
    rows, gold = [], []
    i = 0
    for t, n in n_per_type.items():
        for _ in range(n):
            qid = f"mhr-{i:04d}"
            rows.append({"Question": f"q{i}", "Gold Answer": "Yes", "Type": t, "query_id": qid})
            evidence = [] if t == "null" else [{"doc_id": f"doc{i % 7}", "fact": "f"}]
            gold.append({"query_id": qid, "answer": "Yes", "evidence": evidence})
            i += 1
    with open(directory / "questions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Question", "Gold Answer", "Type", "query_id"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    (directory / "gold.jsonl").write_text("".join(json.dumps(g) + "\n" for g in gold), encoding="utf-8")


def run(*argv):
    with contextlib.redirect_stdout(io.StringIO()):
        return split.main(list(argv))


class SplitTests(unittest.TestCase):
    def test_quotas_are_proportional_and_sum_to_size(self):
        q = split.quotas({"comparison": 856, "inference": 816, "temporal": 583, "null": 301}, 400)
        self.assertEqual(q, {"comparison": 134, "inference": 128, "temporal": 91, "null": 47})

    def test_stratified_deterministic_disjoint_and_check_detects_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            processed, out = Path(tmp) / "p", Path(tmp) / "s"
            processed.mkdir()
            write_processed(processed, {"comparison": 300, "inference": 300, "temporal": 200, "null": 100})
            self.assertEqual(run("--processed", str(processed), "--out", str(out)), 0)
            dev = set((out / "dev400.ids").read_text().split())
            test = set((out / "test_internal.ids").read_text().split())
            self.assertEqual((len(dev), len(test), dev & test), (400, 500, set()))
            manifest = json.loads((out / "split_manifest.json").read_text())
            # 44.44 rounds up: after the floors, null has the second-largest remainder.
            self.assertEqual(manifest["counts"]["dev"]["null"], 45)
            self.assertNotIn(b"\r", (out / "dev400.csv").read_bytes())
            self.assertEqual(run("--processed", str(processed), "--out", str(out), "--check"), 0)

            write_processed(processed, {"comparison": 301, "inference": 300, "temporal": 200, "null": 100})
            self.assertEqual(run("--processed", str(processed), "--out", str(out), "--check"), 1)
            self.assertEqual(run("--processed", str(processed), "--out", str(out)), 1)  # never redrawn in place
            self.assertEqual(set((out / "dev400.ids").read_text().split()), dev)

    def test_committed_split_still_verifies(self):
        self.assertEqual(run("--check"), 0)


if __name__ == "__main__":
    unittest.main()
