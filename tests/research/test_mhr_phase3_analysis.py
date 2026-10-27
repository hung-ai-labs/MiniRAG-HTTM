"""Post-run analysis and budget guards with synthetic inputs; zero API calls."""
import csv
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from reproduce.research.mhr_phase3 import analysis, pipeline
from reproduce.research.mhr_phase3.common import read_json, sha, source_hashes, write_json


def csv_write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def jsonl_write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def setup_run(root):
    questions = [{"query_id": f"q{i}", "Question": f"Synthetic {i}?", "Gold Answer": f"gold{i}", "Type": t}
                 for i, t in enumerate(("inference", "comparison", "temporal", "null"))]
    csv_write(root / "test_internal.csv", questions)
    write_json(root / "TEST_INPUT.json", {"sha256": sha(root / "test_internal.csv")})
    index = root / "index"
    write_json(index / "kv_store_text_chunks.json", {"A": {"content": "source A"}, "B": {"content": "source B"}})
    write_json(index / "index_manifest.json", {"status": "completed", "file_sha256": {
        "kv_store_text_chunks.json": sha(index / "kv_store_text_chunks.json")}})
    write_json(root / "RUN_MANIFEST.json", {"configs": ["C0", "C1"], "seeds": [101, 202, 303],
        "source_hashes": source_hashes(ROOT), "index_path": str(index), "index_manifest_sha256": sha(index / "index_manifest.json")})
    gold = [{"query_id": "q0", "evidence": [{"chunk_ids": ["A"], "located": "inside"}]},
            {"query_id": "q1", "evidence": [{"chunk_ids": ["B"], "located": "inside"}]},
            {"query_id": "q2", "evidence": [{"chunk_ids": ["A", "B"], "located": "spans"}]},
            {"query_id": "q3", "evidence": []}]
    tree = ast.parse((ROOT / "reproduce/Step_2_evaluate.py").read_text(encoding="utf-8"))
    JUDGE_PROMPT = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == "JUDGE_PROMPT" for t in n.targets))
    for seed in (101, 202, 303):
        for c in ("C0", "C1"):
            folder = root / "qa" / f"s{seed}" / f"{c}_s{seed}"
            answers = [{"query_id": q["query_id"], "answer": f"Synthetic response {c} {i}"} for i, q in enumerate(questions)]
            jsonl_write(folder / "answers.jsonl", answers)
            csv_write(folder / "answers.csv", [{"Question": q["Question"], "Gold Answer": q["Gold Answer"],
                       "minirag": a["answer"]} for q, a in zip(questions, answers)])
            contexts, logs = [], []
            for i, q in enumerate(questions):
                ids = ["A"] if c == "C0" else ["A"] if i == 0 else ["B"] if i == 1 else ["A", "B"]
                buf = io.StringIO()
                writer = csv.writer(buf, lineterminator="\n")
                writer.writerow(["id", "content"])
                writer.writerows([[k, "source " + v] for k, v in enumerate(ids)])
                context = "\n-----Entities-----\n```csv\nentity,score,description\n```\n-----Sources-----\n```csv\n" + buf.getvalue().rstrip() + "\n```\n"
                contexts.append({"query_id": q["query_id"], "status": "ok", "context": context, "retrieval_s": 1})
                logs.append({"query": q["Question"], "context_sha256": hashlib.sha256(context.encode()).hexdigest(), "chunk_ids": ids})
            jsonl_write(folder / "contexts.jsonl", contexts)
            jsonl_write(folder / "context.jsonl", logs)
            labels = [["error"] * 3, ["neither"] * 3, ["accurate", "error", "neither"], ["accurate"] * 3] if c == "C0" else \
                     [["accurate"] * 3, ["accurate"] * 3, ["error"] * 3, ["error"] * 3]
            votes, per = [], []
            for q, labs in zip(questions, labels):
                for p, lab in enumerate(labs, 1):
                    votes.append({"query_id": q["query_id"], "pass": p, "type": q["Type"], "status": "ok", "label": lab,
                                  "attempts": [{"ok": True, "raw": lab, "label": lab, "requests": []}]})
                per.append({"query_id": q["query_id"], "Type": q["Type"], "pass1": labs[0], "pass2": labs[1], "pass3": labs[2],
                            "majority": labs[0] if len(set(labs)) == 1 else "no_majority"})
            jsonl_write(folder / "judge/judge.jsonl", votes)
            csv_write(folder / "judge/per_question.csv", per)
            write_json(folder / "judge/summary.json", {"status": "completed", "n_questions": 4, "passes": 3})
            write_json(folder / "judge/manifest.json", {"questions_sha256": sha(root / "test_internal.csv"),
                "answers_sha256": sha(folder / "answers.csv"), "judge_model": "gemini-flash-lite-latest", "passes": 3,
                "seed": 13, "invalid_tries": 3, "answer_column": "minirag", "label_contract": list(analysis.LABELS),
                "prompt_sha256": hashlib.sha256(JUDGE_PROMPT.encode()).hexdigest()})
    return gold


class AnalysisTests(unittest.TestCase):
    def run_case(self, root, gold):
        original = analysis.records
        def data(path):
            return iter(gold) if Path(path).name == "gold_chunks.jsonl" else original(path)
        with patch.object(analysis, "records", side_effect=data):
            return analysis.analyze(ROOT, root, root / "report", expected_n=4, expected_null=1)

    def test_known_scores_recall_and_three_seed_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gold = setup_run(root)
            result = self.run_case(root, gold)
            self.assertEqual(result["valid_votes"], 72)
            first = result["seeds"]["101"]
            self.assertEqual(first["quality"]["C0"]["all"]["majority"]["accurate"], 25)
            self.assertEqual(first["quality"]["C1"]["all"]["majority"]["accurate"], 50)
            self.assertEqual(first["paired_C1_vs_C0"]["all"]["primary_accurate"]["up"], 2)
            self.assertEqual(first["paired_C1_vs_C0"]["all"]["primary_accurate"]["down"], 1)
            self.assertAlmostEqual(first["evidence_recall"]["C0"]["all"]["micro_fact_recall_pct"], 100/3)
            self.assertEqual(first["evidence_recall"]["C1"]["all"]["micro_fact_recall_pct"], 100)
            self.assertIsNone(first["evidence_recall"]["C0"]["null"]["micro_fact_recall_pct"])
            self.assertFalse(result["registered_decisions"]["RQ2_improvement_confirmed"])
            self.assertEqual(result["generation_variability"]["C0"]["accurate"]["sd"], 0)
            self.assertEqual(read_json(root / "report/ANALYSIS_COMPLETED.json")["valid_votes"], 72)

    def test_missing_vote_refuses_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gold = setup_run(root)
            path = root / "qa/s101/C0_s101/judge/judge.jsonl"
            path.write_text("\n".join(path.read_text().splitlines()[:-1]) + "\n")
            with self.assertRaisesRegex(ValueError, "coverage"):
                self.run_case(root, gold)
            self.assertFalse((root / "report/ANALYSIS_COMPLETED.json").exists())

    def test_missing_usage_remains_unknown(self):
        result = analysis.request_summary([{"ok": True, "prompt_tokens": None}])
        self.assertIsNone(result["prompt_tokens"]["known_sum"])
        self.assertEqual(result["prompt_tokens"]["missing_requests"], 1)

    def test_noninferiority_uses_unrounded_registered_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gold = setup_run(root)
            original = analysis.load_module
            def module(repo, filename, name):
                loaded = original(repo, filename, name)
                if filename == "compare_mhr.py":
                    loaded.bootstrap_ci = lambda *a, **k: (-2.9999, 5.0)
                return loaded
            with patch.object(analysis, "load_module", side_effect=module):
                result = self.run_case(root, gold)
            self.assertEqual(result["seeds"]["101"]["paired_C1_vs_C0"]["all"]["primary_accurate"]["ci95"][0], -3.0)
            self.assertTrue(result["registered_decisions"]["RQ2_noninferiority_minus3_confirmed"])

    def test_unexpected_generation_model_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gold = setup_run(root)
            jsonl_write(root / "qa/s101/C0_s101/requests.jsonl", [{"ok": True, "response_model": "another-model"}])
            with self.assertRaisesRegex(ValueError, "Unexpected response model"):
                self.run_case(root, gold)


class BudgetTests(unittest.TestCase):
    def test_completed_child_records_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pipeline.gpu_child([sys.executable, "-c", "pass"], root, root / "child.log", root / "budget.json", "test", 10)
            result = read_json(root / "budget.json")
            self.assertGreater(result["consumed_stage_s"], 0)
            self.assertNotIn("active", result)

    def test_exhausted_budget_blocks_without_starting_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(root / "budget.json", {"consumed_stage_s": 10, "stages": []})
            with patch.object(subprocess, "Popen", side_effect=AssertionError("must not start")):
                with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
                    pipeline.gpu_child([], root, root / "log", root / "budget.json", "test", 10)

    def test_unclosed_stage_blocks_automatic_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(root / "budget.json", {"consumed_stage_s": 0, "stages": [], "active": {"stage": "old"}})
            with self.assertRaisesRegex(RuntimeError, "no end marker"):
                pipeline.gpu_child([], root, root / "log", root / "budget.json", "test", 10)

    def test_runtime_timeout_closes_our_child_and_records_consumption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(subprocess.TimeoutExpired):
                pipeline.gpu_child([sys.executable, "-c", "import time; time.sleep(30)"], root,
                                   root / "child.log", root / "budget.json", "test", 0.1)
            result = read_json(root / "budget.json")
            self.assertNotIn("active", result)
            self.assertGreater(result["consumed_stage_s"], 0)


class OrchestrationTests(unittest.TestCase):
    def test_complete_pipeline_calls_analysis_after_all_three_seed_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "index"
            write_json(index / "index_manifest.json", {"status": "completed", "file_sha256": {}})
            stages = []
            fixed = {"source_hashes": source_hashes(ROOT), "engineering_hashes": {}, "seeds": [101, 202, 303],
                     "configs": ["C0", "C1"]}
            def regular_child(command, cwd, log):
                if "--emit-test" in command:
                    csv_write(root / "test_internal.csv", [{"query_id": f"synthetic{i}", "Question": f"Toy {i}",
                        "Gold Answer": "toy", "Type": "inference"} for i in range(2156)])
                else:
                    self.assertIn("reproduce.research.mhr_phase3.analysis", command)
                    self.assertEqual(len(stages), 9)
                    write_json(root / "report/ANALYSIS_COMPLETED.json", {"status": "completed", "valid_votes": 38808})
            def gpu_child(command, cwd, log, budget, stage, limit):
                stages.append(stage)
                if "answers" in command:
                    folder = Path(command[command.index("--out") + 1])
                    c = command[command.index("--config") + 1]
                    s = command[command.index("--seed") + 1]
                    path = folder / f"{c}_s{s}/answers.csv"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("synthetic answers", encoding="utf-8")
            class Consumer:
                pid = 12345
                def __init__(self, *args, **kwargs):
                    pass
                def poll(self):
                    return None
                def wait(self):
                    write_json(root / "JUDGE_STATUS.json", {"status": "completed", "valid_votes": 38808})
                    return 0
            args = SimpleNamespace(repo=ROOT, validation=root / "validation.json", run_root=root,
                status=root / "STATUS.json", gpu_stage_budget_hours=8, dev_report_dir=None, report_out=root / "report")
            write_json(args.validation, {"synthetic": True})
            with patch.object(pipeline, "verify_validation", return_value={"identity": {"index_path": str(index)}}), \
                 patch.object(pipeline, "plan", return_value=fixed), patch.object(pipeline, "child", side_effect=regular_child), \
                 patch.object(pipeline, "gpu_child", side_effect=gpu_child), \
                 patch("reproduce.research.mhr_phase3.validate.run_pairs", return_value=0), \
                 patch.object(pipeline.subprocess, "Popen", Consumer):
                pipeline.execute(args)
            self.assertEqual(read_json(args.status)["status"], "completed")
            self.assertEqual(stages, [f"{kind}_s{s}" for s in (101, 202, 303)
                                     for kind in ("keywords", "answers_C0", "answers_C1")])


if __name__ == "__main__":
    unittest.main()
