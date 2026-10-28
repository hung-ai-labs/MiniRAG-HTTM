"""Resume the frozen Phase 3 after a Windows status-file sharing failure.

The frozen mhr_phase3 package and its manifest are never changed. An existing
judge consumer is adopted; only a dead consumer may be restarted. Context retries
reuse journals and are limited to the observed STATUS.json sharing failure.
"""
import argparse
import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from reproduce.research.mhr_phase3 import pipeline as original
from reproduce.research.mhr_phase3.common import alive, now, read_json, run_lock, sha, source_hashes


def write_status(path, data):
    """Retry this controller's atomic metadata writes, without changing bytes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for attempt in range(10):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.1 * (attempt + 1))


def status_sharing_failure(status):
    errors = [w for w in status.get("workers", []) if w.get("error_type")]
    return bool(errors) and all(w.get("error_type") == "PermissionError"
               and "STATUS.json" in w.get("error", "")
               and ".tmp" in w.get("error", "")
               and "WinError 5" in w.get("error", "")
               for w in errors)


def recover_contexts(operation, status_path, record_event, attempts=5):
    for attempt in range(1, attempts + 1):
        if operation() == 0:
            return
        status = read_json(status_path)
        if not status_sharing_failure(status) or attempt == attempts:
            raise RuntimeError("Context recovery failed; preserved checkpoint needs inspection")
        record_event({"at": now(), "event": "retry_status_sharing_failure", "attempt": attempt,
                      "completed_queries": status.get("completed_queries")})
        time.sleep(2)


def verify_frozen(args):
    validation = original.verify_validation(args.repo, args.validation)
    manifest = read_json(args.run_root / "RUN_MANIFEST.json")
    planned = original.plan(args.repo, args.validation)
    for key in ("source_hashes", "engineering_hashes", "seeds", "configs"):
        if manifest[key] != planned[key]:
            raise ValueError("Frozen Phase 3 identity changed: " + key)
    if manifest["gpu_stage_budget_hours"] != args.gpu_stage_budget_hours:
        raise ValueError("Original GPU stage budget changed")
    for name, expected in manifest["dev_report_hashes"].items():
        if sha(args.dev_report_dir / name) != expected:
            raise ValueError("Frozen dev report changed: " + name)
    if sha(args.run_root / "test_internal.csv") != read_json(args.run_root / "TEST_INPUT.json")["sha256"]:
        raise ValueError("Frozen test input changed")
    if read_json(args.run_root / "GPU_STAGE_BUDGET.json").get("active"):
        raise ValueError("Unclosed GPU stage must be reconciled before recovery")
    return manifest, Path(validation["identity"]["index_path"])


def ready_seed(args, seed):
    path = args.run_root / f"READY_s{seed}.json"
    if not path.exists():
        return False
    ready = read_json(path)
    if ready["questions_sha256"] != sha(args.run_root / "test_internal.csv"):
        raise ValueError("Ready signal refers to changed test questions")
    for config in ("C0", "C1"):
        path = args.run_root / "qa" / f"s{seed}" / f"{config}_s{seed}/answers.csv"
        if ready["answers"][config] != sha(path):
            raise ValueError("Completed answers changed after ready signal")
    return True


def ensure_consumer(args, state, event):
    lock = args.run_root / "judge_consumer/RUNNING.lock"
    if lock.exists():
        pid = read_json(lock)["pid"]
        if alive(pid):
            if state.get("pid") not in (None, pid):
                raise RuntimeError("Unexpected live judge owner; refusing duplicate")
            state["pid"] = pid
            return pid
    if state.get("starts", 0) >= 3:
        raise RuntimeError("Judge process restart limit reached")
    with (args.run_root / "judge_worker.log").open("a", encoding="utf-8") as log:
        proc = subprocess.Popen([sys.executable, "-m", "reproduce.research.mhr_phase3.judge_worker",
                                 "--repo", str(args.repo), "--run-root", str(args.run_root)],
                                cwd=original.DEFAULT_REPO,
                                env=os.environ | {"PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1",
                                                  "PYTHONDONTWRITEBYTECODE": "1"},
                                stdout=log, stderr=subprocess.STDOUT)
    state.update(pid=None, starts=state.get("starts", 0) + 1)
    event({"at": now(), "event": "start_dead_judge_consumer", "launcher_pid": proc.pid})
    for _ in range(60):
        if lock.exists():
            pid = read_json(lock)["pid"]
            if alive(pid):
                state["pid"] = pid
                return pid
        if proc.poll() is not None:
            raise RuntimeError("Judge consumer failed before acquiring its lock")
        time.sleep(1)
    raise RuntimeError("Judge consumer did not acquire its lock in time")


@contextlib.contextmanager
def keep_awake():
    kernel = None
    if sys.platform == "win32":
        import ctypes
        kernel = ctypes.WinDLL("kernel32")
        kernel.SetThreadExecutionState(0x80000001)
    try:
        yield
    finally:
        if kernel:
            kernel.SetThreadExecutionState(0x80000000)


def execute(args):
    from reproduce.research.mhr_phase3.validate import run_pairs
    args.audit_out.mkdir(parents=True, exist_ok=True)
    events = []
    def event(value):
        events.append(value)
        write_status(args.audit_out / "RECOVERY_EVENTS.json", events)
    with run_lock(args.run_root), keep_awake():
        manifest, index = verify_frozen(args)
        state = {"pid": args.expected_consumer_pid, "starts": 0}
        pid = ensure_consumer(args, state, event)
        write_status(args.audit_out / "RECOVERY_PROVENANCE.json", {
            "at": now(), "controller": str(Path(__file__).resolve()), "controller_sha256": sha(__file__),
            "original_manifest_sha256": sha(args.run_root / "RUN_MANIFEST.json"),
            "original_engineering_hashes": manifest["engineering_hashes"],
            "adopted_consumer_pid": pid, "frozen_package_modified": False,
            "reason": "WinError5 replacing worker STATUS.json; retry unchanged context checkpoints only"})
        failed = args.run_root / "QA_FAILED.json"
        if failed.exists():
            failed.rename(args.run_root / f"QA_FAILED.recovered.{time.time_ns()}.json")
        write_status(args.audit_out / "RECOVERY_STATUS.json", {"status": "running", "at": now(),
                     "pid": os.getpid(), "judge_consumer_pid": pid})
        try:
            for seed in original.SEEDS:
                if source_hashes(args.repo) != manifest["source_hashes"]:
                    raise ValueError("Frozen source changed during recovery")
                ensure_consumer(args, state, event)
                if ready_seed(args, seed):
                    event({"at": now(), "event": "reuse_completed_seed", "seed": seed})
                    continue
                folder = args.run_root / "qa" / f"s{seed}"
                folder.mkdir(parents=True, exist_ok=True)
                questions = args.run_root / "test_internal.csv"
                budget = args.run_root / "GPU_STAGE_BUDGET.json"
                limit = args.gpu_stage_budget_hours * 3600
                write_status(args.status, {"status": "running", "at": now(), "stage": "keywords", "seed": seed})
                original.gpu_child([sys.executable, str(args.repo / "reproduce/research/phased_qa.py"),
                    "keywords", "--questions", str(questions), "--seed", str(seed), "--out", str(folder)],
                    args.run_root, folder / "keywords.log", budget, f"keywords_s{seed}", limit)
                write_status(args.status, {"status": "running", "at": now(), "stage": "shared_contexts", "seed": seed})
                context_status = args.run_root / f"CONTEXT_STATUS_s{seed}.json"
                recover_contexts(lambda: run_pairs(args.repo, questions, folder / f"kw_s{seed}.jsonl",
                    index, folder, seed=seed, status_path=context_status), context_status, event)
                ready = {"seed": seed, "questions_sha256": sha(questions), "answers": {}}
                for config in manifest["configs"]:
                    ensure_consumer(args, state, event)
                    write_status(args.status, {"status": "running", "at": now(), "stage": "answers", "seed": seed, "config": config})
                    original.gpu_child([sys.executable, str(args.repo / "reproduce/research/phased_qa.py"),
                        "answers", "--config", config, "--questions", str(questions), "--seed", str(seed),
                        "--out", str(folder)], args.run_root, folder / f"answers_{config}.log", budget,
                        f"answers_{config}_s{seed}", limit)
                    ready["answers"][config] = sha(folder / f"{config}_s{seed}/answers.csv")
                write_status(args.run_root / f"READY_s{seed}.json", ready)
            write_status(args.status, {"status": "judging", "at": now(), "stage": "all_qa_completed"})
            while True:
                final = read_json(args.run_root / "JUDGE_STATUS.json")
                if final.get("status") == "completed" and final.get("valid_votes") == 38808:
                    break
                ensure_consumer(args, state, event)
                time.sleep(20)
            write_status(args.status, {"status": "analyzing", "at": now()})
            original.child([sys.executable, "-m", "reproduce.research.mhr_phase3.analysis",
                "--repo", str(args.repo), "--run-root", str(args.run_root), "--out", str(args.report_out),
                "--dev-report-dir", str(args.dev_report_dir)], original.DEFAULT_REPO, args.run_root / "analysis.log")
            final = read_json(args.report_out / "ANALYSIS_COMPLETED.json")
            if final.get("status") != "completed" or final.get("valid_votes") != 38808:
                raise RuntimeError("Final audit did not complete")
            write_status(args.status, {"status": "completed", "at": now(), "report_out": str(args.report_out)})
            write_status(args.audit_out / "RECOVERY_STATUS.json", {"status": "completed", "at": now(), "valid_votes": 38808})
        except Exception as exc:
            write_status(args.run_root / "QA_FAILED.json", {"at": now(), "error_type": type(exc).__name__})
            write_status(args.status, {"status": "needs_attention", "at": now(), "error_type": type(exc).__name__})
            write_status(args.audit_out / "RECOVERY_STATUS.json", {"status": "needs_attention", "at": now(),
                         "error_type": type(exc).__name__, "reason": str(exc)})
            raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "validation", "run-root", "status", "report-out", "dev-report-dir", "audit-out"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--expected-consumer-pid", type=int, required=True)
    p.add_argument("--gpu-stage-budget-hours", type=float, default=8)
    p.add_argument("--execute-test", action="store_true")
    args = p.parse_args()
    if not args.execute_test:
        p.error("Recovery execution requires --execute-test")
    execute(args)


if __name__ == "__main__":
    main()
