"""Offline paired-context validation against frozen dev400, with resumable workers."""
import argparse
import csv
import os
from pathlib import Path
import subprocess
import sys
import time

from .common import DEFAULT_REPO, DEFAULT_OUTPUT, digest, load_repo, now, read_json, read_jsonl, run_lock, runtime_identity, sha, source_hashes, write_json


def index_check(index):
    manifest = read_json(Path(index) / "index_manifest.json")
    if manifest["status"] != "completed":
        raise ValueError("Frozen index is not completed")
    for name, expected in manifest["file_sha256"].items():
        if sha(Path(index) / name) != expected:
            raise ValueError("Frozen index changed: " + name)
    return sha(Path(index) / "index_manifest.json")


def write_questions(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run_pairs(repo, questions, kw, index, out, seed=101, workers=3, reference=None,
              status_path=None, extra_identity=None):
    """A single shared prefix per question; 3 process workers as in registered S2."""
    if workers != 3:
        raise ValueError("This version preserves the registered three CPU workers")
    repo, questions, kw, index, out = (Path(p).resolve() for p in (repo, questions, kw, index, out))
    reference = Path(reference).resolve() if reference else None
    phased = load_repo(repo)
    rows = phased.read_questions(questions)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    identity = {"questions_sha256": sha(questions), "keyword_sha256": sha(kw),
                "keyword_path": str(kw), "index_path": str(index),
                "index_manifest_sha256": index_check(index), "source_hashes": source_hashes(repo),
                "adapter_sha256": sha(Path(__file__).with_name("shared_context.py")),
                "common_sha256": sha(Path(__file__).with_name("common.py")),
                "runtime": runtime_identity(),
                "validator_sha256": sha(__file__), "workers": workers, "seed": seed,
                "reference": str(reference) if reference else None,
                "reference_hashes": {f"{c}_s{seed}/{name}": sha(reference / f"{c}_s{seed}/{name}")
                                     for c in ("C0", "C1") for name in ("contexts.jsonl", "context.jsonl")}
                                    if reference else None,
                "extra": extra_identity}
    manifest = out / "validation_manifest.json"
    if manifest.exists() and read_json(manifest) != identity:
        raise ValueError("Validation checkpoint identity changed")
    write_json(manifest, identity)
    status_path = Path(status_path).resolve() if status_path else out / "STATUS.json"
    processes, handles = [], []
    started = time.monotonic()
    env = os.environ | {"PYTHONHASHSEED": "13", "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1",
                        "PYTHONDONTWRITEBYTECODE": "1", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
    for i in range(workers):
        shard = rows[i::workers]
        folder = out / f"worker{i}"
        if not shard:
            continue
        folder.mkdir(parents=True, exist_ok=True)
        qfile = folder / "questions.csv"
        write_questions(qfile, shard)
        cmd = [sys.executable, "-m", "reproduce.research.mhr_phase3.shared_context",
               "--repo", str(repo), "--questions", str(qfile), "--kw", str(kw),
               "--index", str(index), "--out", str(folder), "--seed", str(seed)]
        if reference:
            cmd.extend(["--reference", str(reference)])
        handle = (folder / "worker.log").open("a", encoding="utf-8")
        handles.append(handle)
        processes.append(subprocess.Popen(cmd, cwd=DEFAULT_REPO, env=env, stdout=handle, stderr=subprocess.STDOUT))
    try:
        while True:
            snapshots = [read_json(out / f"worker{i}/STATUS.json")
                         for i in range(workers) if (out / f"worker{i}/STATUS.json").exists()]
            status = {"status": "running", "at": now(), "pid": os.getpid(),
                      "completed_queries": sum(s["completed_queries"] for s in snapshots),
                      "total_queries": len(rows), "configs": ["C0", "C1"],
                      "mismatches": [m for s in snapshots for m in s["mismatches"]],
                      "llm_calls": 0, "workers": snapshots,
                      "elapsed_this_invocation_s": round(time.monotonic() - started, 2)}
            codes = [p.poll() for p in processes]
            if all(code is not None for code in codes):
                break
            write_json(status_path, status)
            if any(code not in (None, 0) for code in codes):
                # Stop only our child context workers; these contain no LLM clients.
                for p in processes:
                    if p.poll() is None:
                        p.terminate()
                break
            time.sleep(5)
        codes = [p.wait() for p in processes]
        pairs = {}
        for i in range(workers):
            for qid, record in read_jsonl(out / f"worker{i}/pairs.jsonl").items():
                if qid in pairs:
                    raise ValueError("Duplicate query across context workers")
                pairs[qid] = record
        mismatches = [m for record in pairs.values() for m in record["mismatches"]]
        successful = all(c == 0 for c in codes) and set(pairs) == {r["query_id"] for r in rows} and not mismatches
        status.update(status="verified" if successful and reference else "completed" if successful else "failed",
                      at=now(), completed_queries=len(pairs), mismatches=mismatches,
                      elapsed_this_invocation_s=round(time.monotonic() - started, 2), exit_codes=codes,
                      identity=identity, logical_answer_contexts=len(pairs) * 2,
                      validation_scope="all_dev400" if reference and len(rows) == 400 else "subset" if reference else "production",
                      test_questions_opened=False if reference else None)
        if successful:
            for config in ("C0", "C1"):
                dest = out / f"{config}_s{seed}"
                dest.mkdir(exist_ok=True)
                with (dest / "contexts.jsonl").open("w", encoding="utf-8") as f:
                    for row in rows:
                        import json
                        f.write(json.dumps(pairs[row["query_id"]]["pair"][config], ensure_ascii=False) + "\n")
                with (dest / "context.jsonl").open("w", encoding="utf-8") as f:
                    for i in range(workers):
                        part = out / f"worker{i}/{config}_s{seed}/context.jsonl"
                        if part.exists():
                            f.write(part.read_text(encoding="utf-8"))
            if reference:
                old = {c: read_jsonl(Path(reference) / f"{c}_s{seed}/contexts.jsonl") for c in ("C0", "C1")}
                status["original_per_query_worker_seconds"] = sum(old[c][r["query_id"]]["retrieval_s"]
                                                                 for c in old for r in rows)
                status["shared_pair_worker_seconds"] = round(sum(p["wall_s"] for p in pairs.values()), 4)
                status["worker_time_ratio_old_over_new"] = round(status["original_per_query_worker_seconds"] /
                                                                max(status["shared_pair_worker_seconds"], 0.001), 3)
                status["timing_caveat"] = "Historical dev vs current run; not a controlled same-load timing experiment. CPU worker seconds are not wall seconds or GPU billing."
            status["output_hashes"] = {f"{c}_s{seed}/{name}": sha(out / f"{c}_s{seed}/{name}")
                                       for c in ("C0", "C1") for name in ("contexts.jsonl", "context.jsonl")}
        write_json(status_path, status)
        return 0 if successful else 1
    finally:
        for p in processes:
            if p.poll() is None:
                p.terminate()
                p.wait()
        for handle in handles:
            handle.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    p.add_argument("--index", type=Path, help="Frozen index; defaults to <repo>/indexes/multihop_rag-qwen-full609")
    p.add_argument("--keywords", type=Path, help="Existing seed101 keyword journal; no new LLM requests")
    p.add_argument("--reference", type=Path, help="Existing dev400 C0_s101/C1_s101 run folders")
    p.add_argument("--out", type=Path, default=DEFAULT_OUTPUT / "dev_validation")
    p.add_argument("--status", type=Path, default=DEFAULT_OUTPUT / "DEV_CONTEXT_VALIDATION.json")
    p.add_argument("--limit", type=int, help="Smoke only; cannot unlock test execution")
    args = p.parse_args()
    args.repo = args.repo.resolve()
    args.out = args.out.resolve()
    if args.limit is not None and args.limit < 1:
        p.error("--limit must be positive")
    args.out.mkdir(parents=True, exist_ok=True)
    phased = load_repo(args.repo)
    questions = args.repo / "dataset/MultiHop-RAG/splits/dev400.csv"
    if args.limit:
        rows = phased.read_questions(questions)[:args.limit]
        questions = args.out / "dev_subset.csv"
        write_questions(questions, rows)
    with run_lock(args.out):
        return run_pairs(args.repo, questions, args.keywords or args.repo / "runs/multihop_rag/dev400/kw_s101.jsonl",
                         args.index or args.repo / "indexes/multihop_rag-qwen-full609", args.out,
                         reference=args.reference or args.repo / "runs/multihop_rag/dev400",
                         status_path=args.status)


if __name__ == "__main__":
    raise SystemExit(main())
