"""Prepare a plan, or explicitly execute the frozen Phase 3 with QA/judge overlap.

Default invocation is offline: no test export, LLM or GPU call. --execute-test
is the distinct execution entry point after full dev equivalence succeeds.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

from .common import DEFAULT_REPO, DEFAULT_OUTPUT, alive, now, read_json, run_lock, runtime_identity, sha, source_hashes, write_json

SEEDS = (101, 202, 303)


def verify_validation(repo, report_path):
    report = read_json(report_path)
    if not (report.get("status") == "verified" and report.get("validation_scope") == "all_dev400"
            and report.get("completed_queries") == report.get("total_queries") == 400
            and report.get("logical_answer_contexts") == 800 and not report.get("mismatches")
            and report.get("llm_calls") == 0):
        raise ValueError("Full dev400 context equivalence is not yet verified")
    identity = report["identity"]
    if identity["source_hashes"] != source_hashes(repo):
        raise ValueError("Repository source changed since context validation")
    for key, filename in (("adapter_sha256", "shared_context.py"), ("validator_sha256", "validate.py"), ("common_sha256", "common.py")):
        if identity[key] != sha(Path(__file__).with_name(filename)):
            raise ValueError("Context implementation changed since validation")
    if identity["runtime"] != runtime_identity():
        raise ValueError("Python/package versions changed since validation")
    if identity["questions_sha256"] != sha(Path(repo) / "dataset/MultiHop-RAG/splits/dev400.csv"):
        raise ValueError("Validation used different dev questions")
    if identity["keyword_sha256"] != sha(Path(identity["keyword_path"])):
        raise ValueError("Validation keyword cache changed")
    from .validate import index_check
    if identity["index_manifest_sha256"] != index_check(Path(identity["index_path"])):
        raise ValueError("Validated index changed")
    for name, expected in identity["reference_hashes"].items():
        if sha(Path(identity["reference"]) / name) != expected:
            raise ValueError("Frozen dev reference changed: " + name)
    return report


def plan(repo, validation):
    try:
        verify_validation(repo, validation)
        context_status = "verified_all_dev400"
    except (FileNotFoundError, ValueError, KeyError) as exc:
        context_status = str(exc) if not isinstance(exc, FileNotFoundError) else "validation_not_completed"
    return {"status": "prepared" if context_status == "verified_all_dev400" else "preparing",
            "at": now(), "repo": str(repo), "validation_report": str(validation),
            "context_validation": context_status, "seeds": list(SEEDS), "configs": ["C0", "C1"],
            "test_queries": 2156, "answer_records": 12936, "valid_judge_votes": 38808,
            "qa_workers": 3, "qa_concurrency": 32,
            "judge_model": "gemini-flash-lite-latest", "judge_passes": 3,
            "judge_concurrency": 4, "invalid_tries": 3, "outer_resume_limit": 32,
            "shared_keywords_within_seed": True, "shared_retrieval_prefix_within_pair": True,
            "schedule": "QA producer sequentially prepares seed101,202,303; one persistent judge consumer handles C0 then C1 per seed while producer advances.",
            "human_validation_gate": "Deferred by user; original V1 kept and its limitations must be disclosed.",
            "test_opened_by_plan": False, "llm_calls_by_plan": 0,
            "source_hashes": source_hashes(repo),
            "engineering_hashes": {p.name: sha(p) for p in Path(__file__).parent.glob("*.py") if not p.name.startswith("test_")}}


def child(command, cwd, log):
    env = os.environ | {"PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1",
                        "PYTHONHASHSEED": "13"}
    with Path(log).open("a", encoding="utf-8") as handle:
        subprocess.run(command, cwd=cwd, env=env, stdout=handle, stderr=subprocess.STDOUT, check=True)


def execute(args):
    from .validate import index_check, run_pairs
    validation = verify_validation(args.repo, args.validation)
    frozen = plan(args.repo, args.validation)
    index = Path(validation["identity"]["index_path"])
    frozen["index_manifest_sha256"] = index_check(index)
    args.run_root.mkdir(parents=True, exist_ok=True)
    with run_lock(args.run_root):
        consumer_lock = args.run_root / "judge_consumer/RUNNING.lock"
        if consumer_lock.exists() and alive(read_json(consumer_lock)["pid"]):
            raise RuntimeError("Prior judge consumer is still alive; do not duplicate it")
        failed_signal = args.run_root / "QA_FAILED.json"
        if failed_signal.exists():
            failed_signal.rename(args.run_root / ("QA_FAILED.previous." + str(__import__('time').time_ns()) + ".json"))
        manifest = args.run_root / "RUN_MANIFEST.json"
        if manifest.exists():
            old = read_json(manifest)
            for key in ("source_hashes", "engineering_hashes", "seeds", "configs", "index_manifest_sha256"):
                if old[key] != frozen[key]:
                    raise ValueError("Cannot resume Phase 3 with changed identity: " + key)
        else:
            frozen.update(execution_started_at=now(), validation_report_sha256=sha(args.validation))
            write_json(manifest, frozen)
        # Open the frozen test only here, using the registered split generator.
        questions = args.run_root / "test_internal.csv"
        if not questions.exists():
            child([sys.executable, str(args.repo / "reproduce/research/make_mhr_split.py"),
                   "--out", str(args.run_root / "split_copy"), "--emit-test", str(questions)],
                  args.run_root, args.run_root / "split.log")
        with questions.open(encoding="utf-8", newline="") as handle:
            import csv
            if sum(1 for _ in csv.DictReader(handle)) != 2156:
                raise ValueError("Wrong frozen test size")
        qhash = sha(questions)
        qmanifest = args.run_root / "TEST_INPUT.json"
        if qmanifest.exists() and read_json(qmanifest)["sha256"] != qhash:
            raise ValueError("Test input changed during resume")
        write_json(qmanifest, {"sha256": qhash, "n": 2156})
        # One consumer process shares the backend key pool across every config.
        env = os.environ | {"PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        judge_handle = (args.run_root / "judge_worker.log").open("a", encoding="utf-8")
        judge = subprocess.Popen([sys.executable, "-m", "reproduce.research.mhr_phase3.judge_worker",
                                  "--repo", str(args.repo), "--run-root", str(args.run_root)],
                                 cwd=DEFAULT_REPO, env=env, stdout=judge_handle, stderr=subprocess.STDOUT)
        try:
            for seed in SEEDS:
                if source_hashes(args.repo) != frozen["source_hashes"]:
                    raise ValueError("Repository source changed during Phase 3")
                if judge.poll() not in (None, 0):
                    raise RuntimeError("Judge consumer failed; inspect judge_worker.log")
                folder = args.run_root / "qa" / f"s{seed}"
                folder.mkdir(parents=True, exist_ok=True)
                write_json(args.status, {"status": "running", "at": now(), "stage": "keywords", "seed": seed})
                child([sys.executable, str(args.repo / "reproduce/research/phased_qa.py"), "keywords",
                       "--questions", str(questions), "--seed", str(seed), "--out", str(folder)],
                      args.run_root, folder / "keywords.log")
                write_json(args.status, {"status": "running", "at": now(), "stage": "shared_contexts", "seed": seed})
                code = run_pairs(args.repo, questions, folder / f"kw_s{seed}.jsonl", index, folder, seed=seed,
                                 status_path=args.run_root / f"CONTEXT_STATUS_s{seed}.json")
                if code:
                    raise RuntimeError("Context workers failed")
                ready = {"seed": seed, "questions_sha256": qhash, "answers": {}}
                for config in ("C0", "C1"):
                    write_json(args.status, {"status": "running", "at": now(), "stage": "answers", "seed": seed, "config": config})
                    child([sys.executable, str(args.repo / "reproduce/research/phased_qa.py"), "answers",
                           "--config", config, "--questions", str(questions), "--seed", str(seed), "--out", str(folder)],
                          args.run_root, folder / f"answers_{config}.log")
                    ready["answers"][config] = sha(folder / f"{config}_s{seed}/answers.csv")
                write_json(args.run_root / f"READY_s{seed}.json", ready)
            write_json(args.status, {"status": "judging", "at": now(), "stage": "all_qa_completed"})
            code = judge.wait()
            if code:
                raise RuntimeError("Judge consumer incomplete; resume without changing the run identity")
            final = read_json(args.run_root / "JUDGE_STATUS.json")
            write_json(args.status, {"status": "raw_runs_completed_analysis_pending", "at": now(),
                                    "judge": final, "run_root": str(args.run_root)})
        except Exception as exc:
            write_json(args.run_root / "QA_FAILED.json", {"at": now(), "error_type": type(exc).__name__})
            write_json(args.status, {"status": "needs_attention", "at": now(), "error_type": type(exc).__name__,
                                    "run_root": str(args.run_root), "judge_pid": judge.pid,
                                    "note": "Consumer finishes its current seed pair, then notices QA_FAILED. Do not start a duplicate consumer."})
            raise
        finally:
            judge_handle.close()


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    p.add_argument("--validation", type=Path, default=DEFAULT_OUTPUT / "DEV_CONTEXT_VALIDATION.json")
    p.add_argument("--run-root", type=Path, default=DEFAULT_REPO / "runs/multihop_rag/test_phase3")
    p.add_argument("--status", type=Path, default=DEFAULT_OUTPUT / "PHASE3_STATUS.json")
    p.add_argument("--plan-out", type=Path, default=DEFAULT_OUTPUT / "EXECUTION_PLAN.json")
    p.add_argument("--execute-test", action="store_true")
    args = p.parse_args()
    args.repo = args.repo.resolve()
    args.run_root = args.run_root.resolve()
    if args.execute_test:
        execute(args)
    else:
        result = plan(args.repo, args.validation)
        write_json(args.plan_out, result)
        print(json.dumps({k: result[k] for k in ("status", "context_validation", "test_opened_by_plan", "llm_calls_by_plan")}))


if __name__ == "__main__":
    main()
