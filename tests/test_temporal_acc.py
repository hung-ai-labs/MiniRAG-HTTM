import sys
from pathlib import Path
import csv
import json
import tempfile
from unittest.mock import patch
import unittest

ACC = Path(__file__).resolve().parents[1] / "reproduce/graph_repair/acc"
sys.path.insert(0, str(ACC))
import analyze
import run
import share_judge


class TemporalAccuracyTests(unittest.TestCase):
    def test_config_env(self):
        for arm, value in (("L-C0", "0"), ("L-T", "1")):
            self.assertEqual(run.env_for(arm)["MINIRAG_TEMPORAL"], value)
            self.assertEqual(run.env_for(arm)["PYTHONHASHSEED"], "13")
        sys.path.insert(0, str(ACC.parents[1] / "research"))
        import phased_qa
        self.assertEqual(phased_qa.config_env("L-T")["MINIRAG_TEMPORAL"], "1")
        self.assertEqual(phased_qa.config_env("L-C0")["MINIRAG_TEMPORAL"], "0")
        self.assertEqual(phased_qa.FUSION["L-T"], phased_qa.FUSION["L-C0"])
        with patch.dict("os.environ", {}, clear=True):
            phased_qa.apply_env("L-T", 101)
            import os
            self.assertEqual(os.environ["MINIRAG_TEMPORAL"], "1")
            phased_qa.apply_env("L-C0", 101)
            self.assertEqual(os.environ["MINIRAG_TEMPORAL"], "0")

    def test_exact_triple_mapping(self):
        q = [{"query_id": "a", "Question": "When?", "Gold Answer": "Tuesday", "Type": "Single"}]
        same = [{"Question": "When?", "Gold Answer": "Tuesday", "minirag": "Tuesday"}]
        other = [{"Question": "When?", "Gold Answer": "Tuesday", "minirag": " Tuesday"}]
        unique, mapping = share_judge.mapping_for([
            ("qwen", 101, "L-C0", q, same), ("qwen", 101, "L-T", q, same),
            ("qwen", 202, "L-T", q, other)])
        self.assertEqual(len(unique), 2)
        self.assertEqual(mapping[0]["unique_id"], mapping[1]["unique_id"])
        self.assertNotEqual(mapping[1]["unique_id"], mapping[2]["unique_id"])

    def test_crn_copy_and_refusals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            qpath = root / "questions.csv"
            questions = [{"query_id": f"q{i}", "Question": f"Question {i}",
                          "Gold Answer": "gold", "Type": "Single"} for i in range(435)]
            with qpath.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(questions[0]))
                w.writeheader()
                w.writerows(questions)
            model_dir = root / "qwen"
            model_dir.mkdir()
            gate = model_dir / "gate_s101.json"
            gate.write_text(json.dumps({"model": "qwen", "seed": 101, "baseline_identical": 435,
                                        "context_changed": ["q1"]}), encoding="utf-8")
            for arm in ("L-C0", "L-T"):
                folder = model_dir / f"{arm}_s101"
                folder.mkdir()
                with (folder / "answers.csv").open("w", encoding="utf-8", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=["Question", "Gold Answer", "minirag"])
                    w.writeheader()
                    w.writerows({"Question": q["Question"], "Gold Answer": "gold",
                                 "minirag": f"{arm}-{q['query_id']}"} for q in questions)
                (folder / "answers.jsonl").write_text(
                    "".join(json.dumps({"query_id": q["query_id"],
                                         "answer": f"{arm}-{q['query_id']}"}) + "\n" for q in questions),
                    encoding="utf-8")
            with patch.object(run, "OUT", root), patch.object(run, "QUESTIONS", qpath):
                manifest = run.crn("qwen", 101)
                self.assertEqual((manifest["from_c0"], manifest["from_lt"]), (434, 1))
                made = run.rows(model_dir / "L-TC_s101/answers.csv")
                self.assertEqual(made[0]["minirag"], "L-C0-q0")
                self.assertEqual(made[1]["minirag"], "L-T-q1")
                self.assertEqual(run.crn("qwen", 101), manifest)
                gate.write_text(json.dumps({"model": "qwen", "seed": 101, "baseline_identical": 434,
                                            "context_changed": ["q1"]}), encoding="utf-8")
                with self.assertRaises(ValueError):
                    run.crn("qwen", 101)
                gate.write_text(json.dumps({"model": "qwen", "seed": 101, "baseline_identical": 435,
                                            "context_changed": ["q1"]}), encoding="utf-8")
                lt = model_dir / "L-T_s101/answers.jsonl"
                lt.write_text("\n".join(lt.read_text(encoding="utf-8").splitlines()[:-1]) + "\n", encoding="utf-8")
                with self.assertRaises(ValueError):
                    run.crn("qwen", 101)

    def test_per_model_judge_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            q = [{"query_id": "q", "Question": "When?", "Gold Answer": "Tuesday", "Type": "Single"}]
            a = [{"Question": "When?", "Gold Answer": "Tuesday", "minirag": "Tuesday"}]
            with patch.object(share_judge, "OUT", root), \
                    patch.object(share_judge, "answer_sets", return_value=(
                        [("qwen", 101, "L-C0", q, a), ("qwen", 101, "L-TC", q, a)], {"input": "hash"})):
                manifest = share_judge.prepare("qwen")
                self.assertEqual((manifest["calls_with_sharing"], manifest["calls_saved"]), (3, 3))
                self.assertTrue((root / "judge_shared/qwen/mapping.json").exists())
                self.assertFalse((root / "judge_shared/phi").exists())
                self.assertEqual(share_judge.prepare("qwen"), manifest)

    def test_synthetic_analysis(self):
        questions = {f"q{i}": "Single" if i < 430 else "Null" for i in range(435)}
        mapping, verdicts = [], {}
        for model in ("qwen",):
            for seed in run.SEEDS:
                for arm in ("L-C0", "L-TC"):
                    for i, qid in enumerate(questions):
                        uid = f"{model}-{seed}-{arm}-{qid}" if arm == "L-TC" and i < 10 else f"{model}-{seed}-C0-{qid}"
                        label = "accurate" if arm == "L-TC" and i < 10 else "error" if i < 10 else "neither"
                        verdicts[uid] = {"majority": label, "pass1": label, "pass2": label, "pass3": label}
                        mapping.append({"model": model, "seed": seed, "arm": arm,
                                        "query_id": qid, "unique_id": uid})
        # Exercise the same CSV reader used by the final analysis, with a synthetic verdict file.
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "per_question.csv"
            with file.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["query_id", "majority", "pass1", "pass2", "pass3"])
                writer.writeheader()
                for uid, votes in verdicts.items():
                    writer.writerow({"query_id": uid} | votes)
            loaded = {r["query_id"]: r for r in run.rows(file)}
        changed = {("qwen", s): {f"q{i}" for i in range(10)} for s in run.SEEDS}
        result = analyze.analyze_rows(mapping, loaded, questions, changed)
        self.assertEqual(result["qwen"]["101"]["primary"]["all"]["acc"]["b_up"], 10)
        self.assertEqual(result["qwen"]["101"]["primary"]["all"]["err"]["net"], -10)
        self.assertEqual(result["qwen"]["303"]["primary"]["unchanged"]["acc"]["b_up"], 0)
        self.assertTrue(result["qwen"]["registered_verdict"]["acc_increase_all_3_p_lt_0_05"])
        self.assertAlmostEqual(analyze.exact_mcnemar(10, 0), 2 / 1024)
        # Force a different verdict for one unchanged TC item.
        altered = [dict(x) for x in mapping]
        next(x for x in altered if x["seed"] == 101 and x["arm"] == "L-TC" and x["query_id"] == "q10")["unique_id"] = "qwen-101-L-TC-q0"
        with self.assertRaises(AssertionError):
            analyze.analyze_rows(altered, loaded, questions, changed)


if __name__ == "__main__":
    unittest.main()
