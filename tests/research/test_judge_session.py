"""Offline tests for judge_session.py: one session per seed, fault tolerance, the interrupted-session rule."""

import argparse
import asyncio
import collections
import contextlib
import csv
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reproduce/research"))
spec = importlib.util.spec_from_file_location("judge_session", ROOT / "reproduce/research/judge_session.py")
js = importlib.util.module_from_spec(spec)
spec.loader.exec_module(js)

PROMPT = "Q: {question}\nGold: {gold}\nPred: {pred}"
CONFIGS = ("L-C0", "L-B2")


def setup(tmp, n=3):
    root, questions = Path(tmp) / "run", Path(tmp) / "q.csv"
    with open(questions, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Question", "Gold Answer", "Type", "query_id"])
        for i in range(n):
            w.writerow([f"q{i}", "Yes", "Single", f"lh-{i:04d}"])
    for c in CONFIGS:
        d = root / f"{c}_s101"
        d.mkdir(parents=True)
        with open(d / "answers.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["Question", "Gold Answer", "minirag"])
            for i in range(n):
                w.writerow([f"q{i}", "Yes", f"{c} answer {i}"])
    return root, questions


def cfg_for(root, questions, archive=False):
    return argparse.Namespace(root=root, seed=101, questions=questions, configs=CONFIGS, judgemodel="pinned",
                              registration="860f20f", archive_partial=archive, concurrency=2, api_tries=1,
                              api_wait=0, prompt=PROMPT, fail_response="Sorry", provenance={"head_commit": "x"})


def run(cfg, complete, sleeps=None):
    async def fake_sleep(s):
        if sleeps is not None:
            sleeps.append(s)

    with contextlib.redirect_stdout(io.StringIO()):
        return asyncio.run(js.run_session(cfg, complete, sleep=fake_sleep))


def journal(root, config):
    return [json.loads(line) for line in (root / f"{config}_s101" / "judge" / "judge.jsonl").read_text().splitlines()]


class SessionTests(unittest.TestCase):
    def test_completed_session_records_provenance_and_every_arm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, q = setup(tmp)

            async def complete(prompt):
                return "accurate"

            self.assertEqual(run(cfg_for(root, q), complete), 0)
            s = json.loads((root / "judge_s101_SESSION.json").read_text())
            self.assertEqual((s["state"], s["judge_model"], s["registration_commit"]), ("completed", "pinned", "860f20f"))
            self.assertEqual(set(s["arms"]), set(CONFIGS))
            self.assertEqual(set(s["answers_sha256"]), set(CONFIGS))
            for c in CONFIGS:
                self.assertTrue((root / f"{c}_s101" / "judge" / "summary.json").exists())
            with self.assertRaises(SystemExit):  # a completed session is never redone
                run(cfg_for(root, q), complete)

    def test_quota_exhaustion_waits_inside_the_session_without_duplicate_verdicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, q = setup(tmp)
            calls = collections.Counter()

            async def complete(prompt):
                calls["n"] += 1
                if calls["n"] <= 4:  # quota gone, then back
                    raise RuntimeError("429 quota")
                return "error"

            sleeps = []
            self.assertEqual(run(cfg_for(root, q), complete, sleeps), 0)
            self.assertTrue(sleeps)  # it waited instead of exiting
            for c in CONFIGS:
                ok = collections.Counter((r["query_id"], r["pass"]) for r in journal(root, c) if r["status"] == "ok")
                self.assertEqual(len(ok), 3 * 3)
                self.assertTrue(all(n == 1 for n in ok.values()))  # no slot judged twice

    def test_stubborn_parse_failures_become_blank_votes_after_three_cycles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, q = setup(tmp)

            async def complete(prompt):
                return "Let me think... error" if "L-B2 answer 1" in prompt else "accurate"

            self.assertEqual(run(cfg_for(root, q), complete), 0)
            s = json.loads((root / "judge_s101_SESSION.json").read_text())
            self.assertEqual(len(s["arms"]["L-B2"]["abstained"]), 3)  # three passes of that one question
            self.assertEqual(s["arms"]["L-B2"]["cycles"], 3)

    def test_interrupted_session_is_refused_then_archived_unread_and_redone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, q = setup(tmp)

            async def dies(prompt):
                raise KeyboardInterrupt  # the machine went down mid-session

            with self.assertRaises(KeyboardInterrupt):
                run(cfg_for(root, q), dies)
            self.assertEqual(json.loads((root / "judge_s101_SESSION.json").read_text())["state"], "interrupted")
            with self.assertRaises(SystemExit):  # partial judging exists: refuse
                run(cfg_for(root, q), dies)

            async def fine(prompt):
                return "neither"

            self.assertEqual(run(cfg_for(root, q, archive=True), fine), 0)
            s = json.loads((root / "judge_s101_SESSION.json").read_text())
            self.assertTrue(s["archived_partial_unread"])
            self.assertTrue(any(p.name.startswith("judge_partial_unread_") for p in (root / "L-C0_s101").iterdir()))
            self.assertTrue(list(root.glob("judge_s101_SESSION_interrupted_*.json")))
            # The new session judged everything itself; nothing was carried over from the archived part.
            self.assertTrue(all(r["label"] == "neither" for c in CONFIGS for r in journal(root, c)))

    def test_status_write_survives_windows_sharing_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            target, fails = Path(tmp) / "s.json", {"n": 0}
            real = js.qa_run.atomic_json

            def flaky(path, value):
                if fails["n"] < 2:
                    fails["n"] += 1
                    raise PermissionError("WinError 5")
                real(path, value)

            js.qa_run.atomic_json = flaky
            try:
                self.assertTrue(js.write_status(target, {"a": 1}))
            finally:
                js.qa_run.atomic_json = real
            self.assertEqual(json.loads(target.read_text()), {"a": 1})


if __name__ == "__main__":
    unittest.main()
