"""Prepare or execute shared three-phase QA; default only prints the commands.

Generation only: choose the dataset's judge separately after reviewing its protocol.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import qa_run


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset-id", required=True)
    p.add_argument("--index", type=Path, required=True)
    p.add_argument("--questions", type=Path, required=True)
    p.add_argument("--registration", type=Path, required=True)
    p.add_argument("--serving-config", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--configs", nargs="+", choices=("C0", "C1", "C2", "C3", "C_orig"), required=True)
    p.add_argument("--workers", type=qa_run.positive, default=3)
    p.add_argument("--llm-max-async", type=qa_run.positive, default=32)
    p.add_argument("--execute", action="store_true", help="Actually call the paid Modal endpoint")
    return p


def commands(args):
    common = ["--dataset-id", args.dataset_id, "--index", str(args.index.resolve()),
              "--questions", str(args.questions.resolve()), "--registration", str(args.registration.resolve()),
              "--serving-config", str(args.serving_config.resolve()), "--out", str(args.out.resolve()),
              "--seed", str(args.seed), "--llm-max-async", str(args.llm_max_async)]
    runner = [sys.executable, "-u", str(Path(__file__).with_name("phased_qa.py"))]
    result = []
    if any(c != "C3" for c in args.configs):
        result.append(runner + ["keywords"] + common)
    for config in args.configs:
        result.append(runner + ["contexts", "--config", config, "--workers", str(args.workers)] + common)
        result.append(runner + ["answers", "--config", config] + common)
    return result


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    if len(set(args.configs)) != len(args.configs):
        p.error("Configurations must be unique")
    if args.llm_max_async > 32:
        p.error("--llm-max-async must be at most 32 for the shared Modal deployment")
    planned = commands(args)
    print(json.dumps({"execute": args.execute, "commands": planned}, indent=2), flush=True)
    if not args.execute:
        return 0
    env = os.environ | {"PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1", "PYTHONHASHSEED": "13"}
    for command in planned:
        result = subprocess.run(command, cwd=qa_run.ROOT, env=env)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
