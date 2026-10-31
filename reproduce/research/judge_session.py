"""One judging session for one generation seed of the LiHua ablation v2 (amendment LA1).

All arms of the seed are judged one after another by this single long-lived process, with
judge_run.py's own runner (prompt, label contract, three passes, journal, resume and S4 blank votes are
not re-implemented here). What this adds is what makes a session complete and reproducible:

  fault tolerance   Quota exhaustion does not end the session: judge_failed records are retried in the
                    same session after a growing wait (at most an hour each, 36 hours in total), and
                    parse_failed records are asked again for up to three cycles before they become blank
                    votes (--abstain-after 3). Verdicts are appended and fsynced by judge_run, status
                    writes retry Windows sharing errors, and a per-seed OS lock forbids two sessions.
  session rule      If any arm of the seed already has a judge/ directory, an earlier session was cut
                    short: the session refuses to start. --archive-partial renames those directories to
                    judge_partial_unread_<time> without reading them, and the seed is judged from scratch.
  reproducibility   The session refuses to run with uncommitted changes in the judging code; SESSION.json
                    records the commit, sha256 of every judging source file, the pinned judge model, the
                    questions and every answer file, plus per-arm timing, cycles, waits and the models
                    that actually answered. Every number can be recomputed offline from the journals.
                    (Re-calling Gemini is not bit-reproducible; recomputation from the saved replies is.)

    python reproduce/research/judge_session.py --root runs/lihua_world/ablation_v2 --seed 101 \
        --questions dataset/LiHua-World/splits/nondev435.csv --judgemodel gemini-3.5-flash-lite \
        L-C0 L-B2 L-VEC L-BM25 L-B1 L-NOENT L-NOGRAPH
"""

import argparse
import asyncio
import collections
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import judge_run  # noqa: E402
import qa_run  # noqa: E402

JUDGING_SOURCES = ("reproduce/research/judge_run.py", "reproduce/research/judge_session.py",
                   "reproduce/research/llm_trace.py", "reproduce/Step_2_evaluate.py",
                   "minirag/llm/gemini.py", "minirag/prompt.py")
MAX_WAIT_S, TOTAL_WAIT_S, ABSTAIN_AFTER = 3600, 36 * 3600, 3


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_status(path, value, tries=10):
    """Atomic replace; Windows can briefly refuse it (WinError 5/32) while a reader holds the file."""
    for attempt in range(tries):
        try:
            qa_run.atomic_json(path, value)
            return True
        except PermissionError:
            time.sleep(0.2 * (attempt + 1))
    print(f"warning: could not write {path} after {tries} tries; verdicts are unaffected")
    return False


def provenance(repo=ROOT):
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", *JUDGING_SOURCES], cwd=repo,
                           capture_output=True, text=True).stdout.split("\n")
    return {"head_commit": head, "dirty_judging_sources": [d[3:] for d in dirty if d.strip()],
            "source_sha256": {p: sha_file(repo / p) for p in JUDGING_SOURCES}}


def statuses(run_dir):
    latest = judge_run.read_records(Path(run_dir) / "judge.jsonl")
    return collections.Counter(r["status"] for r in latest.values())


def arm_args(cfg, answers, run_dir, resume):
    return argparse.Namespace(
        questions=cfg.questions, answers=answers, run_dir=run_dir, resume=resume, column="minirag",
        judgemodel=cfg.judgemodel, passes=3, seed=13, concurrency=cfg.concurrency, invalid_tries=3,
        api_tries=cfg.api_tries, api_wait=cfg.api_wait, abstain_after=ABSTAIN_AFTER, prompt=cfg.prompt)


async def judge_arm(cfg, config, complete, rows, status, save, sleep):
    """Run judge_run cycles for one arm until complete; returns the arm's record for SESSION.json."""
    run_dir = cfg.root / f"{config}_s{cfg.seed}" / "judge"
    answers = cfg.root / f"{config}_s{cfg.seed}" / "answers.csv"
    record = {"config": config, "started_at": qa_run.utc_now(), "cycles": 0, "waits_s": []}
    status["arms"][config] = record
    waited, failure_streak = sum(sum(a.get("waits_s", [])) for a in status["arms"].values()), 0
    while True:
        record["cycles"] += 1
        args = arm_args(cfg, answers, run_dir, resume=run_dir.joinpath("manifest.json").exists())
        task = asyncio.ensure_future(judge_run.run(args, rows, complete))
        while not task.done():
            await asyncio.wait({task}, timeout=60)
            status["heartbeat_at"] = qa_run.utc_now()
            save()
        code = task.result()
        counts = statuses(run_dir)
        record["statuses"] = dict(counts)
        if code == 0:
            summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            record.update(finished_at=qa_run.utc_now(), response_models=summary.get("response_models", {}),
                          abstained=summary.get("abstained", []), summary_sha256=sha_file(run_dir / "summary.json"))
            save()
            return record
        if counts.get("judge_failed"):  # quota or network: wait inside the session, never exit
            failure_streak += 1
            wait = min(MAX_WAIT_S, 60 * 2 ** min(failure_streak, 6))
            if waited + wait > TOTAL_WAIT_S:
                raise TimeoutError(f"{config}: judge still failing after {waited / 3600:.1f} h of waiting")
            record["waits_s"].append(wait)
            waited += wait
            status["state"] = f"waiting_quota ({config}, {wait} s)"
            save()
            await sleep(wait)
            status["state"] = "running"
        elif counts.get("parse_failed"):
            failure_streak = 0  # ask again now; a slot still failing after ABSTAIN_AFTER cycles is a blank vote
        else:
            raise RuntimeError(f"{config}: judge_run incomplete without failed records: {dict(counts)}")


async def run_session(cfg, complete, sleep=asyncio.sleep):
    session_path = cfg.root / f"judge_s{cfg.seed}_SESSION.json"
    previous = json.loads(session_path.read_text(encoding="utf-8")) if session_path.exists() else None
    if previous and previous.get("state") == "completed":
        raise SystemExit(f"seed {cfg.seed} already has a completed session; nothing to do")
    leftovers = [c for c in cfg.configs if (cfg.root / f"{c}_s{cfg.seed}" / "judge").exists()]
    stamp = time.strftime("%Y%m%dT%H%M%S")
    archived = []
    if leftovers:
        if not cfg.archive_partial:
            raise SystemExit(f"seed {cfg.seed}: partial judging from an interrupted session in {leftovers}; "
                             "rerun with --archive-partial to set it aside unread and judge the seed again")
        for c in leftovers:  # renamed, never opened: the registered session rule
            src = cfg.root / f"{c}_s{cfg.seed}" / "judge"
            dst = src.with_name(f"judge_partial_unread_{stamp}")
            src.rename(dst)
            archived.append(str(dst.relative_to(cfg.root)))
        if previous:
            session_path.rename(session_path.with_name(f"judge_s{cfg.seed}_SESSION_interrupted_{stamp}.json"))

    rows_by_config = {}
    for c in cfg.configs:
        answers = cfg.root / f"{c}_s{cfg.seed}" / "answers.csv"
        if not answers.exists():
            raise SystemExit(f"{c}: no answers.csv; generate before judging")
        rows_by_config[c] = judge_run.load_rows(cfg.questions, answers, "minirag", cfg.fail_response)
    status = {"session_id": uuid.uuid4().hex, "seed": cfg.seed, "state": "running", "started_at": qa_run.utc_now(),
              "heartbeat_at": qa_run.utc_now(), "judge_model": cfg.judgemodel, "configs": list(cfg.configs),
              "registration_commit": cfg.registration, "provenance": cfg.provenance,
              "questions_sha256": sha_file(cfg.questions),
              "answers_sha256": {c: sha_file(cfg.root / f"{c}_s{cfg.seed}" / "answers.csv") for c in cfg.configs},
              "archived_partial_unread": archived, "pid": os.getpid(), "arms": {}}

    def save():
        write_status(session_path, status)

    save()
    try:
        for c in cfg.configs:
            await judge_arm(cfg, c, complete, rows_by_config[c], status, save, sleep)
        models = collections.Counter()
        for arm in status["arms"].values():
            models.update(arm.get("response_models", {}))
        status["response_models"] = dict(models)
        foreign = [m for m in models if m != cfg.judgemodel]
        status["state"] = "model_mismatch" if foreign else "completed"
        status["finished_at"] = qa_run.utc_now()
        save()
        return 0 if not foreign else 3
    except BaseException as exc:
        status.update(state="interrupted", error_type=type(exc).__name__, interrupted_at=qa_run.utc_now())
        save()
        raise


def parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("configs", nargs="+")
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--questions", type=Path, required=True)
    p.add_argument("--judgemodel", required=True)
    p.add_argument("--registration", default="860f20f")
    p.add_argument("--archive-partial", action="store_true")
    p.add_argument("--allow-dirty", action="store_true", help="tests only")
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--api-tries", type=int, default=6)
    p.add_argument("--api-wait", type=float, default=60.0)
    return p


def main(argv=None):
    cfg = parser().parse_args(argv)
    sys.path[:0] = [str(ROOT), str(ROOT / "reproduce")]
    cfg.provenance = provenance()
    if cfg.provenance["dirty_judging_sources"] and not cfg.allow_dirty:
        raise SystemExit("uncommitted changes in judging code: " + ", ".join(cfg.provenance["dirty_judging_sources"])
                         + " -- commit first so the session records the code that ran")
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    judge_run.require_gemini_endpoint()
    import llm_trace
    from minirag.llm.gemini import gemini_complete_if_cache
    from minirag.prompt import PROMPTS
    from Step_2_evaluate import JUDGE_PROMPT

    llm_trace.install()
    cfg.prompt, cfg.fail_response = JUDGE_PROMPT, PROMPTS["fail_response"]

    async def complete(prompt_text):
        return await gemini_complete_if_cache(cfg.judgemodel, prompt_text)

    lock_dir = cfg.root / f"judge_s{cfg.seed}_lock"
    lock_dir.mkdir(parents=True, exist_ok=True)
    with qa_run.run_lock(lock_dir):
        return asyncio.run(run_session(cfg, complete))


if __name__ == "__main__":
    sys.exit(main())
