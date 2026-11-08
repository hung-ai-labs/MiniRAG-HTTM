"""C0/C1/C2/C3 profiles shared by offline retrieval and QA commands."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ARMS = {
    "C0": ("0", "0", ""),
    "C1": ("1", "0", ""),
    "C2": ("1", "1", ""),
    "C3": ("1", "1", "weighted"),
}


def environment(arm, fusion="graph", budget=4000):
    if arm not in ARMS or fusion not in ("graph", "rrf", "rrf_bm25") or budget <= 0:
        raise ValueError("Invalid ablation arm, graph-preserving fusion, or budget")
    counter, flow, scorer = ARMS[arm]
    return {
        "MINIRAG_PATH2CHUNK_FIX": counter, "MINIRAG_PATH_SCORE_FLOW": flow,
        "MINIRAG_PATH_SCORE": scorer, "MINIRAG_ANSWER_TYPE_FIX": "1",
        "MINIRAG_PATH_PRUNE": "", "MINIRAG_CHUNK_CUT": "", "MINIRAG_RERANK": "",
        "MINIRAG_LEEF": "", "MINIRAG_GRAPH_FLOW": "", "MINIRAG_P2_ENHANCE": "",
        "MINIRAG_CHUNK_FUSION": "" if fusion == "graph" else fusion,
        "MINIRAG_TRUNCATE_SOURCES": "1", "MINIRAG_MAX_TOKEN_TEXT_UNIT": str(budget),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=ARMS, required=True)
    parser.add_argument("--fusion", choices=("graph", "rrf", "rrf_bm25"), default="graph")
    parser.add_argument("--sources-budget", type=int, default=4000)
    parser.add_argument("--kw-cache", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.sources_budget <= 0:
        parser.error("Sources budget must be positive")
    settings = environment(args.arm, args.fusion, args.sources_budget)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        print(json.dumps(settings, indent=2))
        return
    if not args.kw_cache or not args.kw_cache.is_file() or not args.manifest:
        parser.error("Commands require an existing --kw-cache and a separate --manifest per arm/run")
    settings.update(MINIRAG_KW_CACHE=str(args.kw_cache.resolve()), MINIRAG_KW_CACHE_ONLY="1")
    root = Path(__file__).resolve().parents[2]
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    plan = {"arm": args.arm, "environment": settings, "command": command, "git_commit": revision,
            "parser_sha256": hashlib.sha256(args.kw_cache.read_bytes()).hexdigest()}
    if args.manifest.exists() and json.loads(args.manifest.read_text()) != plan:
        parser.error("Manifest differs: use a new output/manifest for this configuration")
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(plan, indent=2))
    raise SystemExit(subprocess.call(command, cwd=Path.cwd(), env={**os.environ, **settings}))


if __name__ == "__main__":
    main()
