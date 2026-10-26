"""Run one MultiHop-RAG QA config as N parallel shards, then merge (amendment S1, 26/10/2026).

Superseded by phased_qa.py (amendment S2): kept as the record of the S1 runs.

MiniRAG's retrieval on the 18.5k-node MultiHop graph costs ~20 s of CPU per
question in one Python thread, so a single qa_run.py process uses under one
core while the paid GPU waits. This splits the question file into N shards
(round robin over rows), runs reproduce/research/run_mhr_qa.sh on each shard
in its own process -- same config, seed and per-process concurrency as
registered -- and merges the shards' answers back into input order.

Every config is run the same way, so conditions stay equal between configs.
What each request contains is unchanged; only how many run at once.

Output in <run-dir>:
    shard_K/            one complete run_mhr_qa.sh run per shard (note, manifest,
                        generation log, context log, answers)
    answers.csv         merged, same row order as <questions> -- judge_run.py input
    context.jsonl       merged retrieval log
    shard_summary.json  per-shard status and timing

--drop-snapshots deletes each shard's index_snapshot/ copy once that shard
completed; qa_run.py has already checked that the snapshot and the frozen
source index hash to the manifest value, so nothing unique is lost.

    python reproduce/research/shard_mhr_qa.py C0 dataset/MultiHop-RAG/splits/dev400.csv \
        runs/multihop_rag/dev400/c0_s101 101 --shards 8 --drop-snapshots
"""

import argparse
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def read_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def write_rows(path, fieldnames, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def split(rows, shards):
    """Round robin keeps every shard's mix of question types close to the whole."""
    return [rows[k::shards] for k in range(shards)]


def merge(rows, shard_rows, shard_answers):
    """Put each shard's answers back at their input positions; check questions line up."""
    merged = [None] * len(rows)
    shards = len(shard_rows)
    for k, (expected, got) in enumerate(zip(shard_rows, shard_answers)):
        if len(expected) != len(got):
            raise ValueError(f"shard {k}: {len(got)} answers for {len(expected)} questions")
        for j, (q, a) in enumerate(zip(expected, got)):
            if q["Question"] != a["Question"]:
                raise ValueError(f"shard {k} row {j}: answer does not match its question")
            merged[k + j * shards] = a
    return merged


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("config", choices=("C0", "C1", "C2", "C3"))
    p.add_argument("questions", type=Path)
    p.add_argument("run_dir", type=Path)
    p.add_argument("seed", type=int)
    p.add_argument("--shards", type=int, default=8)
    p.add_argument("--drop-snapshots", action="store_true")
    args = p.parse_args(argv)

    if args.run_dir.exists():
        raise SystemExit(f"{args.run_dir} exists; every run gets a new directory")
    fieldnames, rows = read_rows(args.questions)
    parts = split(rows, args.shards)
    args.run_dir.mkdir(parents=True)

    procs, started = [], time.time()
    for k, part in enumerate(parts):
        shard_dir = args.run_dir / f"shard_{k}"
        shard_dir.mkdir()
        write_rows(shard_dir / "questions.csv", fieldnames, part)
        log = open(shard_dir / "qa.log", "w", encoding="utf-8")
        procs.append((subprocess.Popen(
            # bash drops Windows backslashes, so paths go over as forward slashes.
            ["bash", "reproduce/research/run_mhr_qa.sh", args.config, (shard_dir / "questions.csv").as_posix(),
             shard_dir.as_posix(), str(args.seed)], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT), log))
    codes = []
    for proc, log in procs:
        codes.append(proc.wait())
        log.close()

    summary = {"config": args.config, "seed": args.seed, "shards": args.shards,
               "questions": str(args.questions), "wall_s": round(time.time() - started, 1), "per_shard": []}
    for k in range(args.shards):
        metrics_path = args.run_dir / f"shard_{k}" / "qa" / "metrics.json"
        metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}
        summary["per_shard"].append({"shard": k, "exit": codes[k], "status": metrics.get("status"),
                                     "n_ok": metrics.get("n_ok"), "n_expected": metrics.get("n_expected"),
                                     "wall_s": metrics.get("wall_s")})
    complete = all(s["status"] == "completed" for s in summary["per_shard"])
    summary["status"] = "completed" if complete else "incomplete"

    if complete:
        answers = [read_rows(args.run_dir / f"shard_{k}" / "qa" / "answers.csv")[1] for k in range(args.shards)]
        merged = merge(rows, parts, answers)
        write_rows(args.run_dir / "answers.csv", ["Question", "Gold Answer", "minirag"], merged)
        with open(args.run_dir / "context.jsonl", "w", encoding="utf-8") as out:
            for k in range(args.shards):
                log = args.run_dir / f"shard_{k}" / "context.jsonl"
                if log.exists():
                    out.write(log.read_text(encoding="utf-8"))
        if args.drop_snapshots:
            for k in range(args.shards):
                shutil.rmtree(args.run_dir / f"shard_{k}" / "qa" / "index_snapshot", ignore_errors=True)
            summary["snapshots_dropped"] = True
    (args.run_dir / "shard_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("status", "wall_s")}, indent=2))
    # An incomplete shard is resumed with qa_run.py --resume in its own shard_K/qa directory.
    return 0 if complete else 1


if __name__ == "__main__":
    sys.exit(main())
