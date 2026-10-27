"""One persistent Gemini consumer, using the original judge prompt/parser/options."""
import argparse
import asyncio
import importlib.util
from pathlib import Path
import sys

from .common import DEFAULT_REPO, load_repo, now, read_json, run_lock, sha, write_json


def load_judge(repo):
    spec = importlib.util.spec_from_file_location("phase3_original_judge", repo / "reproduce/research/judge_run.py")
    judge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(judge)
    return judge


async def consume(args):
    load_repo(args.repo)
    from dotenv import load_dotenv
    load_dotenv(args.repo / ".env")
    from minirag.llm.gemini import gemini_complete_if_cache
    from minirag.prompt import PROMPTS
    from Step_2_evaluate import JUDGE_PROMPT
    import llm_trace
    llm_trace.install()
    judge = load_judge(args.repo)
    judge.require_gemini_endpoint()
    manifest = read_json(args.run_root / "RUN_MANIFEST.json")
    total = 0
    async def complete(prompt):
        return await gemini_complete_if_cache(manifest["judge_model"], prompt)
    for seed in manifest["seeds"]:
        ready_path = args.run_root / f"READY_s{seed}.json"
        while not ready_path.exists():
            if (args.run_root / "QA_FAILED.json").exists():
                raise RuntimeError("QA producer failed before this seed became ready")
            await asyncio.sleep(5)
        ready = read_json(ready_path)
        questions = args.run_root / "test_internal.csv"
        if ready["questions_sha256"] != sha(questions):
            raise ValueError("Ready signal refers to a different test input")
        for config in manifest["configs"]:
            folder = args.run_root / "qa" / f"s{seed}" / f"{config}_s{seed}"
            answers = folder / "answers.csv"
            if ready["answers"][config] != sha(answers):
                raise ValueError("Answer file changed after ready signal")
            directory = folder / "judge"
            argv = ["--questions", str(questions), "--answers", str(answers), "--run-dir", str(directory),
                    "--judgemodel", manifest["judge_model"], "--passes", str(manifest["judge_passes"]),
                    "--concurrency", str(manifest["judge_concurrency"]), "--invalid-tries", str(manifest["invalid_tries"])]
            parsed = judge.parser().parse_args(argv)
            parsed.prompt = JUDGE_PROMPT
            rows = judge.load_rows(questions, answers, parsed.column, PROMPTS["fail_response"])
            for cycle in range(manifest["outer_resume_limit"]):
                parsed.resume = (directory / "manifest.json").exists()
                write_json(args.run_root / "JUDGE_STATUS.json", {"status": "running", "at": now(),
                           "seed": seed, "config": config, "resume_cycle": cycle, "prior_valid_votes": total})
                code = await judge.run(parsed, rows, complete)
                if code == 0:
                    break
            else:
                raise RuntimeError("Fixed outer resume budget exhausted")
            total += len(rows) * manifest["judge_passes"]
            write_json(args.run_root / "JUDGE_STATUS.json", {"status": "running", "at": now(), "valid_votes": total,
                       "last_completed_seed": seed, "last_completed_config": config})
    if total != manifest["valid_judge_votes"]:
        raise ValueError("Final valid judge count differs from design")
    write_json(args.run_root / "JUDGE_STATUS.json", {"status": "completed", "at": now(), "valid_votes": total,
               "analysis_pending": True})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    p.add_argument("--run-root", type=Path, required=True)
    args = p.parse_args()
    with run_lock(args.run_root / "judge_consumer"):
        asyncio.run(consume(args))


if __name__ == "__main__":
    main()
