"""Prepare (or explicitly execute) the same 100 QA rows at fixed concurrency levels."""

import json
import os
from pathlib import Path
import subprocess
import sys

try:
    from .qa_run import ROOT, load_questions, parser, atomic_json
except ImportError:
    from qa_run import ROOT, load_questions, parser, atomic_json


def main():
    p = parser()
    p.description = __doc__ + " Default: print commands only; --execute incurs API/GPU usage."
    p.add_argument("--execute", action="store_true", help="Actually invoke the paid backend")
    p.add_argument("--levels", nargs="+", type=int, choices=(1, 2, 4, 8, 16), default=[1, 2, 4],
                   help="Default: conservative sweep 1 2 4; explicitly add 8 or 16 for stress tests")
    p.set_defaults(limit=100, warmup=5)
    args = p.parse_args()
    if args.resume or args.limit != 100:
        p.error("Benchmark uses a fresh run directory and exactly the first 100 rows")
    if len(load_questions(args.questions, 100)) != 100:
        p.error("Benchmark requires at least 100 input questions")
    if len(set(args.levels)) != len(args.levels):
        p.error("Concurrency levels must be unique")
    if args.execute and (not args.serving_config or not args.serving_config.is_file()):
        p.error("Live benchmark requires --serving-config with the actual pinned serving setup")
    if args.execute and not os.environ.get("MINIRAG_SLM_SEED", "").strip().isdigit():
        p.error("Live benchmark requires the same fixed MINIRAG_SLM_SEED for every level")
    output = args.run_dir.resolve()
    commands = []
    for level in args.levels:
        command = [sys.executable, str(Path(__file__).with_name("qa_run.py")),
                   "--questions", str(args.questions.resolve()),
                   "--workingdir", str(args.workingdir.resolve()),
                   "--run-dir", str(output / f"c{level}"), "--limit", "100",
                   "--warmup", str(args.warmup),
                   "--concurrency", str(level), "--llm-max-async", str(level),
                   "--backend", args.backend, "--model", args.model,
                   "--embedmodel", args.embedmodel, "--mode", args.mode]
        for flag, value in (("--topk", args.topk), ("--maxtokentextunit", args.maxtokentextunit),
                            ("--responsetype", args.responsetype)):
            if value:
                command.extend([flag, str(value)])
        if args.serving_config:
            command.extend(["--serving-config", str(args.serving_config.resolve())])
        commands.append(command)
    env = os.environ.copy()
    env.setdefault("PYTHONHASHSEED", "13")
    print(json.dumps({"execute": args.execute, "python_hash_seed": env["PYTHONHASHSEED"],
                      "commands": commands}, indent=2))
    if not args.execute:
        return 0
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for command, level in zip(commands, args.levels):
        result = subprocess.run(command, cwd=ROOT, env=env, check=False)
        metric_file = output / f"c{level}" / "metrics.json"
        metrics = json.loads(metric_file.read_text(encoding="utf-8")) if metric_file.exists() else {}
        results.append({"concurrency": level, "returncode": result.returncode, "metrics": metrics})
        atomic_json(output / "benchmark.json", {"runs": results})
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
