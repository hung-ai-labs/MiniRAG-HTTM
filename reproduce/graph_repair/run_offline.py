"""Run the frozen offline evaluator in independent shards, with local caches only."""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "logs" / "graph_repair"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--top-k", type=int, default=60)
    ap.add_argument("--diag", action="store_true")
    ap.add_argument("--path-score", choices=("zero", "shuffle"))
    ap.add_argument("--answer-type-fix", choices=("0", "1"), default="1")
    ap.add_argument("--arm", choices=("C0", "C1", "C2", "C3"), default="C0")
    ap.add_argument("--flow-norm", choices=("max",))
    ap.add_argument("--flow-spec", choices=("idf",))
    ap.add_argument("--phase", default="phase1")
    ap.add_argument("--env", action="append", default=[], metavar="KEY=VALUE",
                    help="extra MINIRAG_* switch for this run (repeatable), e.g. MINIRAG_PACK_X=1")
    ap.add_argument("--index", type=Path, default=ROOT / "LiHua-World-qwen-modal",
                    help="index folder, read only; in a worktree pass the main checkout's copy (CRLF graphml)")
    ap.add_argument("--tiktoken-cache", type=Path, default=ROOT / "data-gym-cache")
    args = ap.parse_args()
    if not (args.index / "graph_chunk_entity_relation.graphml").is_file():
        raise SystemExit(f"Not an index folder: {args.index}")
    # eval_offline re-applies c_ablation.environment(), which resets these keys: --env cannot set them.
    reset = {"MINIRAG_PATH2CHUNK_FIX", "MINIRAG_PATH_SCORE_FLOW", "MINIRAG_PATH_SCORE", "MINIRAG_ANSWER_TYPE_FIX",
             "MINIRAG_PATH_PRUNE", "MINIRAG_CHUNK_CUT", "MINIRAG_RERANK", "MINIRAG_LEEF", "MINIRAG_GRAPH_FLOW",
             "MINIRAG_P2_ENHANCE", "MINIRAG_CHUNK_FUSION", "MINIRAG_TRUNCATE_SOURCES", "MINIRAG_MAX_TOKEN_TEXT_UNIT"}
    for kv in args.env:
        if kv.partition("=")[0] in reset:
            raise SystemExit(f"--env {kv!r}: eval_offline overrides this key; use --arm/--top-k instead")
    out = BASE / args.phase / args.name
    out.mkdir(parents=True, exist_ok=True)
    cache = args.tiktoken_cache
    for name in ("9b5ad71b2ce5302211f9c61530b329a4922fc6a4",
                 "fb374d419588a4632f3f557e76b4b70aebbca790"):
        if not (cache / name).is_file():
            raise SystemExit(f"Missing local tokenizer cache: {cache / name}")
    tmp = BASE / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(PYTHONIOENCODING="utf-8", MINIRAG_KW_CACHE_ONLY="1",
               HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
               TIKTOKEN_CACHE_DIR=str(cache), TMP=str(tmp), TEMP=str(tmp),
               MINIRAG_ANSWER_TYPE_FIX=args.answer_type_fix)
    env.pop("MINIRAG_DIAG_LOG", None)
    env.pop("MINIRAG_DIAG_PATH_SCORE", None)
    env.pop("MINIRAG_FLOW_NORM", None)
    env.pop("MINIRAG_FLOW_SPEC", None)
    if args.flow_norm:
        env["MINIRAG_FLOW_NORM"] = args.flow_norm
    if args.flow_spec:
        env["MINIRAG_FLOW_SPEC"] = args.flow_spec
    for kv in args.env:
        key, sep, value = kv.partition("=")
        if not sep or not key.startswith("MINIRAG_"):
            raise SystemExit(f"--env expects MINIRAG_KEY=VALUE, got {kv!r}")
        env[key] = value
    run_env = {"arm": args.arm, "top_k": args.top_k, "extra": args.env, "index": str(args.index),
               "minirag": {k: v for k, v in env.items() if k.startswith("MINIRAG_")}}
    (out / "run_env.json").write_text(json.dumps(run_env, indent=2) + "\n", encoding="utf-8")
    if args.path_score:
        env["MINIRAG_DIAG_PATH_SCORE"] = args.path_score

    shard_count = 2  # RAM limit: never run more than two offline workers.
    shard_size = 90

    def shard(i):
        folder = out / f"shard_{i}"
        folder.mkdir(exist_ok=True)
        (folder / "diag.jsonl").unlink(missing_ok=True)
        local_env = env.copy()
        if args.diag:
            local_env["MINIRAG_DIAG_LOG"] = str(folder / "diag.jsonl")
        cmd = [sys.executable, str(ROOT / "reproduce" / "path" / "eval_offline.py"),
               "--arm", args.arm, "--fusion", "graph", "--top-k", str(args.top_k),
               "--answer-type-fix", args.answer_type_fix,
               "--offset", str(i * shard_size), "--limit", str(shard_size),
               "--workingdir", str(args.index), "--output-dir", str(folder)]
        with (folder / "console.txt").open("w", encoding="utf-8") as log:
            code = subprocess.call(cmd, cwd=ROOT, env=local_env, stdout=log, stderr=subprocess.STDOUT)
        return i, code

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(shard, range(shard_count)))
    if any(code for _, code in results):
        raise SystemExit(f"Shard failures: {results}")
    records = f"{args.arm}_records.jsonl"
    for filename in (records, "diag.jsonl") if args.diag else (records,):
        with (out / filename).open("w", encoding="utf-8") as merged:
            for i in range(shard_count):
                merged.write((out / f"shard_{i}" / filename).read_text(encoding="utf-8"))
    rows = [json.loads(x) for x in (out / records).read_text(encoding="utf-8").splitlines()]
    if len(rows) != 180 or len({r["question"] for r in rows}) != 180:
        raise SystemExit(f"Expected 180 unique {args.arm} records")
    print(f"{args.name}: 180 records, arm={args.arm}, norm={args.flow_norm}, spec={args.flow_spec}, top_k={args.top_k}, diag={args.diag}")


if __name__ == "__main__":
    main()
