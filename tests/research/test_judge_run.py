"""Offline tests for judge_run.py: strict label contract, retries, resume, aggregates."""

import argparse
import asyncio
import contextlib
import csv
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("judge_run", ROOT / "reproduce/research/judge_run.py")
jr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jr)

PROMPT = "Q: {question}\nGold: {gold}\nPred: {pred}"


def scripted(replies):
    """complete() that returns, per prompt, the next scripted reply (or raises it)."""
    calls = []

    async def complete(prompt_text):
        calls.append(prompt_text)
        reply = replies(prompt_text, sum(1 for c in calls if c == prompt_text))
        if isinstance(reply, Exception):
            raise reply
        return reply

    return complete, calls


def write_inputs(directory, preds):
    q, a = directory / "questions.csv", directory / "answers.csv"
    with open(q, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Question", "Gold Answer", "Type", "query_id"])
        for i in range(len(preds)):
            w.writerow([f"q{i}", "Yes", "comparison" if i % 2 else "null", f"mhr-{i:04d}"])
    with open(a, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Question", "Gold Answer", "minirag"])
        for i, p in enumerate(preds):
            w.writerow([f"q{i}", "Yes", p])
    return q, a


def args_for(q, a, run_dir, resume=False):
    return argparse.Namespace(questions=q, answers=a, run_dir=run_dir, resume=resume, column="minirag",
                              judgemodel="fake", passes=3, seed=13, concurrency=2, invalid_tries=3,
                              api_tries=2, api_wait=0, prompt=PROMPT)


FAIL = "Sorry, I'm not able to provide an answer to that question."


def run(args, complete):
    with contextlib.redirect_stdout(io.StringIO()):
        return asyncio.run(jr.run(args, jr.load_rows(args.questions, args.answers, args.column, FAIL), complete))


class LabelContractTests(unittest.TestCase):
    def test_only_exact_labels_are_accepted(self):
        accepted = {"accurate": "accurate", "Accurate.": "accurate", " **error** ": "error", '"neither"': "neither"}
        for reply, label in accepted.items():
            self.assertEqual(jr.parse_label(reply), label, reply)
        for reply in ("inaccurate", "accurate, error", "", None, "The answer is accurate", "not accurate"):
            self.assertIsNone(jr.parse_label(reply), reply)

    def test_invalid_replies_are_retried_then_parse_failed_never_mapped(self):
        complete, calls = scripted(lambda p, n: "inaccurate")
        status, label, attempts = asyncio.run(jr.judge_one(complete, "p", invalid_tries=3, api_tries=2, api_wait=0))
        self.assertEqual((status, label, len(calls)), ("parse_failed", None, 3))
        self.assertEqual([a["raw"] for a in attempts], ["inaccurate"] * 3)

        complete, _ = scripted(lambda p, n: "inaccurate" if n == 1 else "Error.")
        self.assertEqual(asyncio.run(jr.judge_one(complete, "p", invalid_tries=3, api_tries=2, api_wait=0))[:2],
                         ("ok", "error"))

    def test_api_failures_become_judge_failed(self):
        complete, calls = scripted(lambda p, n: RuntimeError("quota"))
        status, label, attempts = asyncio.run(jr.judge_one(complete, "p", invalid_tries=3, api_tries=2, api_wait=0))
        self.assertEqual((status, label, len(calls)), ("judge_failed", None, 2))
        self.assertEqual(attempts[0]["error_type"], "RuntimeError")

    def test_majority_and_no_majority(self):
        self.assertEqual(jr.majority(["accurate", "error", "accurate"]), "accurate")
        self.assertEqual(jr.majority(["accurate", "error", "neither"]), "no_majority")

    def test_refuses_a_non_gemini_endpoint(self):
        with patch.dict(os.environ, {"GEMINI_API_BASE": "https://x--minirag-slm-serve.modal.run/v1"}):
            with self.assertRaisesRegex(ValueError, "not the Gemini endpoint"):
                jr.require_gemini_endpoint()


class RunTests(unittest.TestCase):
    def test_incomplete_run_writes_no_summary_and_resume_retries_only_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            q, a = write_inputs(Path(tmp), ["Yes", FAIL, "Maybe", "Yes"])
            run_dir = Path(tmp) / "judge"

            def first(prompt_text, n):  # q2 gets garbage on every pass
                return "garbage" if "q2" in prompt_text else ("accurate" if "Pred: Yes" in prompt_text else "error")

            complete, _ = scripted(first)
            self.assertEqual(run(args_for(q, a, run_dir), complete), 1)
            self.assertFalse((run_dir / "summary.json").exists())
            with open(run_dir / "per_question.csv", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[2]["majority"], "incomplete")

            complete, calls = scripted(lambda p, n: "neither")
            self.assertEqual(run(args_for(q, a, run_dir, resume=True), complete), 0)
            self.assertEqual(len(calls), 3)  # only q2, once per pass
            self.assertTrue(all("q2" in c for c in calls))

            summary = json.loads((run_dir / "summary.json").read_text())["groups"]
            self.assertEqual(summary["all"]["majority"]["accurate"], 50.0)
            self.assertEqual(summary["all"]["pass_mean_sd"]["accurate"], {"mean": 50.0, "sd": 0.0})
            self.assertEqual(summary["null"]["majority"]["n"], 2)
            self.assertEqual((summary["all"]["early_exit"], summary["comparison"]["early_exit"]), (1, 1))

    def test_resume_refuses_changed_answers_and_fresh_run_refuses_existing_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            q, a = write_inputs(Path(tmp), ["Yes", "No"])
            run_dir = Path(tmp) / "judge"
            complete, _ = scripted(lambda p, n: "accurate")
            self.assertEqual(run(args_for(q, a, run_dir), complete), 0)
            with self.assertRaisesRegex(ValueError, "use --resume"):
                run(args_for(q, a, run_dir), complete)
            write_inputs(Path(tmp), ["Yes", "Changed"])
            with self.assertRaisesRegex(ValueError, "refusing to resume"):
                run(args_for(q, a, run_dir, resume=True), complete)

    def test_torn_last_record_is_rejudged_but_corruption_inside_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "judge.jsonl"
            good = json.dumps({"query_id": "q0", "pass": 1, "status": "ok", "label": "accurate"})
            path.write_text(good + "\n" + '{"query_id": "q1", "pa', encoding="utf-8")
            self.assertEqual(list(jr.read_records(path)), [("q0", 1)])
            path.write_text('{"query_id": "q1", "pa\n' + good + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "corrupt record on line 1"):
                jr.read_records(path)

    def test_answers_must_line_up_with_questions(self):
        with tempfile.TemporaryDirectory() as tmp:
            q, a = write_inputs(Path(tmp), ["Yes", "No"])
            lines = a.read_text(encoding="utf-8").splitlines()
            a.write_text("\n".join([lines[0], lines[2], lines[1]]) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not line up"):
                jr.load_rows(q, a, "minirag")


if __name__ == "__main__":
    unittest.main()
