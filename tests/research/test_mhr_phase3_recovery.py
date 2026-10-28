"""Offline failure injection for the operational recovery controller."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "phase3_recovery", ROOT / "reproduce/research/recover_mhr_phase3_windows.py")
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)


def sharing_status():
    return {"completed_queries": 837, "workers": [
        {"error_type": "PermissionError", "error": "[WinError 5] Access is denied: STATUS.json.42.tmp -> STATUS.json"}]}


class RecoveryTests(unittest.TestCase):
    def test_atomic_status_retries_keep_old_file_until_replace(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "STATUS.json"
            p.write_text('{"old": true}', encoding="utf-8")
            real_replace = recovery.os.replace
            calls = []
            def replace(source, target):
                calls.append(1)
                if len(calls) <= 2:
                    self.assertTrue(json.loads(p.read_text())["old"])
                    raise PermissionError("sharing violation")
                return real_replace(source, target)
            with patch.object(recovery.os, "replace", side_effect=replace), patch.object(recovery.time, "sleep"):
                recovery.write_status(p, {"new": True})
            self.assertEqual(json.loads(p.read_text()), {"new": True})
            self.assertEqual(len(calls), 3)

    def test_status_retry_is_bounded(self):
        with tempfile.TemporaryDirectory() as d, patch.object(recovery.os, "replace", side_effect=PermissionError), patch.object(recovery.time, "sleep"):
            with self.assertRaises(PermissionError):
                recovery.write_status(Path(d) / "STATUS.json", {})
            self.assertEqual(recovery.os.replace.call_count, 10)

    def test_context_retry_preserves_completed_journal(self):
        with tempfile.TemporaryDirectory() as d:
            status, journal = Path(d) / "STATUS.json", Path(d) / "pairs.jsonl"
            journal.write_text('saved-checkpoint\n', encoding="utf-8")
            status.write_text(json.dumps(sharing_status()), encoding="utf-8")
            def operation():
                self.assertEqual(journal.read_text(), 'saved-checkpoint\n')
                return 1 if op.call_count == 1 else 0
            op, event = Mock(side_effect=operation), Mock()
            with patch.object(recovery.time, "sleep"):
                recovery.recover_contexts(op, status, event)
            self.assertEqual(op.call_count, 2)
            self.assertEqual(event.call_count, 1)

    def test_unexpected_context_failure_is_not_retried(self):
        with tempfile.TemporaryDirectory() as d:
            status = Path(d) / "STATUS.json"
            status.write_text(json.dumps({"workers": [{"error_type": "ValueError"}]}))
            op = Mock(return_value=1)
            with self.assertRaises(RuntimeError):
                recovery.recover_contexts(op, status, Mock())
            self.assertEqual(op.call_count, 1)

    def test_context_retry_limit_and_mixed_errors(self):
        with tempfile.TemporaryDirectory() as d:
            status = Path(d) / "STATUS.json"
            status.write_text(json.dumps(sharing_status()))
            op = Mock(return_value=1)
            with patch.object(recovery.time, "sleep"), self.assertRaises(RuntimeError):
                recovery.recover_contexts(op, status, Mock(), attempts=2)
            self.assertEqual(op.call_count, 2)
            mixed = sharing_status()
            mixed["workers"].append({"error_type": "ValueError"})
            self.assertFalse(recovery.status_sharing_failure(mixed))
            mixed["workers"][-1] = {"error_type":"PermissionError", "error":"index access denied"}
            self.assertFalse(recovery.status_sharing_failure(mixed))

    def test_live_consumer_is_adopted_without_spawn(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "judge_consumer").mkdir()
            (root / "judge_consumer/RUNNING.lock").write_text('{"pid":55}')
            args = SimpleNamespace(run_root=root)
            with patch.object(recovery, "alive", return_value=True), patch.object(recovery.subprocess, "Popen") as spawn:
                self.assertEqual(recovery.ensure_consumer(args, {"pid":55}, Mock()), 55)
                spawn.assert_not_called()
                with self.assertRaises(RuntimeError):
                    recovery.ensure_consumer(args, {"pid":99}, Mock())
                spawn.assert_not_called()

    def test_dead_consumer_restart_limit_refuses_spawn(self):
        with tempfile.TemporaryDirectory() as d:
            args = SimpleNamespace(run_root=Path(d))
            with patch.object(recovery.subprocess, "Popen") as spawn, self.assertRaises(RuntimeError):
                recovery.ensure_consumer(args, {"pid":55,"starts":3}, Mock())
            spawn.assert_not_called()

    def test_completed_ready_answers_cannot_change(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "test_internal.csv").write_text('synthetic question')
            (root / "READY_s101.json").write_text(json.dumps({
                "questions_sha256": recovery.sha(root / "test_internal.csv"),
                "answers": {"C0":"wrong", "C1":"wrong"}}))
            p = root / "qa/s101/C0_s101/answers.csv"
            p.parent.mkdir(parents=True)
            p.write_text('synthetic answer')
            with self.assertRaises(ValueError):
                recovery.ready_seed(SimpleNamespace(run_root=root), 101)

    def test_changed_frozen_code_refuses_recovery(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            old = {"source_hashes":{}, "engineering_hashes":{"common.py":"original"},
                   "seeds":[101,202,303], "configs":["C0","C1"]}
            (root / "RUN_MANIFEST.json").write_text(json.dumps(old))
            changed = old | {"engineering_hashes":{"common.py":"changed"}}
            args = SimpleNamespace(repo=root, validation=root / "validation.json", run_root=root)
            with patch.object(recovery.original, "verify_validation", return_value={}), patch.object(recovery.original, "plan", return_value=changed), self.assertRaises(ValueError):
                recovery.verify_frozen(args)
            self.assertEqual(json.loads((root / "RUN_MANIFEST.json").read_text()), old)

    def test_original_seed_plan_budget_and_final_analysis(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "run"
            root.mkdir()
            (root / "test_internal.csv").write_text('synthetic questions')
            (root / "RUN_MANIFEST.json").write_text('{}')
            (root / "JUDGE_STATUS.json").write_text('{"status":"completed","valid_votes":38808}')
            (root / "QA_FAILED.json").write_text('{}')
            args = SimpleNamespace(run_root=root, repo=ROOT, validation=root / "validation.json",
                audit_out=Path(d) / "audit", report_out=Path(d) / "report", dev_report_dir=Path(d) / "dev",
                status=Path(d) / "status.json", expected_consumer_pid=55, gpu_stage_budget_hours=8)
            manifest = {"configs":["C0","C1"], "source_hashes":{}, "engineering_hashes":{}}
            def gpu(command, cwd, log, budget, stage, limit):
                self.assertEqual(limit, 28800)
                if "answers" in command:
                    folder = Path(command[command.index("--out") + 1])
                    seed = command[command.index("--seed") + 1]
                    config = command[command.index("--config") + 1]
                    p = folder / f"{config}_s{seed}/answers.csv"
                    p.parent.mkdir(parents=True)
                    p.write_text('synthetic completed answer')
            def analysis(*args_):
                args.report_out.mkdir()
                (args.report_out / "ANALYSIS_COMPLETED.json").write_text('{"status":"completed","valid_votes":38808}')
            with patch.object(recovery, "verify_frozen", return_value=(manifest, root / "index")), patch.object(recovery, "source_hashes", return_value={}), patch.object(recovery, "ensure_consumer", return_value=55), patch.object(recovery, "ready_seed", side_effect=lambda args_, seed:seed == 101), patch.object(recovery.original, "gpu_child", side_effect=gpu) as gen, patch("reproduce.research.mhr_phase3.validate.run_pairs", return_value=0) as contexts, patch.object(recovery.original, "child", side_effect=analysis) as analyze:
                recovery.execute(args)
            self.assertEqual(gen.call_count, 6)
            self.assertEqual([c.args[2] for c in contexts.call_args_list], [root/'qa/s202/kw_s202.jsonl',root/'qa/s303/kw_s303.jsonl'])
            self.assertEqual(analyze.call_count, 1)
            self.assertEqual(json.loads(args.status.read_text())["status"], "completed")
            self.assertTrue(list(root.glob('QA_FAILED.recovered.*.json')))
            self.assertEqual(json.loads((root / "RUN_MANIFEST.json").read_text()), {})


if __name__ == "__main__":
    unittest.main()
