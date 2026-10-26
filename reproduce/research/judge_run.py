"""Judge a qa_run.py answer file: 3 passes, strict labels, majority per question.

Uses Step_2_evaluate.JUDGE_PROMPT unchanged, so verdicts stay comparable with
the LiHua numbers, but fixes how a reply becomes a label. Step_2_evaluate
matches substrings (`"inaccurate"` reads as accurate) and turns anything it
cannot read into "neither", which looks exactly like a real abstention. Here a
reply must be exactly one of accurate / error / neither (case, surrounding
whitespace, quotes, asterisks and trailing punctuation ignored). Anything else
is invalid: the same prompt is asked again, and when the tries run out the
record is `parse_failed` -- never mapped to a label. API failures that outlast
the retries are `judge_failed`. Neither status enters any statistic: the run
stays incomplete, exits non-zero, and --resume retries exactly those records.

Outputs in --run-dir:
    judge.jsonl         one record per (query_id, pass) attempt cycle, with every
                        raw reply and per-request metadata (llm_trace.py)
    manifest.json       inputs, model, prompt and settings; resume must match
    per_question.csv    query_id, Type, one column per pass, majority
    summary.json        only when every record is ok

Two aggregates, deliberately kept apart (MULTIHOP_RAG_ROADMAP.md):
    majority      one label per question = the label of >= 2 of 3 passes,
                  `no_majority` on a 1-1-1 split; for paired tests
    pass mean/sd  acc/err/neither of each pass, then mean +/- sd across passes;
                  the paper's way of reporting, and judge noise only

    python reproduce/research/judge_run.py --questions dataset/MultiHop-RAG/splits/dev400.csv \
        --answers runs/multihop_rag/<run>/answers.csv --run-dir runs/multihop_rag/<run>/judge
"""

import argparse
import asyncio
import collections
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

LABELS = ("accurate", "error", "neither")
STRIP = " \t\r\n\"'`*.,;:!?"
GEMINI_HOST = "generativelanguage.googleapis.com"


def parse_label(reply):
    text = (reply or "").strip().lower().strip(STRIP)
    return text if text in LABELS else None


def majority(labels):
    label, votes = collections.Counter(labels).most_common(1)[0]
    return label if votes * 2 > len(labels) else "no_majority"


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_rows(questions, answers, column, fail_response=None):
    """fail_response: MiniRAG's canned early-exit reply, counted separately because on
    a Null question it reads like a correct refusal although no answer was generated."""
    with open(questions, newline="", encoding="utf-8") as f:
        qrows = list(csv.DictReader(f))
    with open(answers, newline="", encoding="utf-8") as f:
        arows = list(csv.DictReader(f))
    # qa_run.py exports answers in input order; check rather than trust it.
    if len(qrows) != len(arows):
        raise ValueError(f"{len(arows)} answers for {len(qrows)} questions")
    rows = []
    for i, (q, a) in enumerate(zip(qrows, arows)):
        if q["Question"] != a["Question"] or q["Gold Answer"] != a["Gold Answer"]:
            raise ValueError(f"row {i}: answers.csv does not line up with the question file")
        rows.append({"query_id": q["query_id"], "type": q.get("Type", "?"), "question": q["Question"],
                     "gold": q["Gold Answer"], "pred": a[column],
                     "early_exit": fail_response is not None and a[column].strip() == fail_response})
    if len({r["query_id"] for r in rows}) != len(rows):
        raise ValueError("duplicate query_id")
    return rows


def require_gemini_endpoint():
    # The judge is Gemini by protocol; a shell still configured for the Modal SLM
    # would otherwise grade with Qwen and nothing would look wrong.
    base = os.environ.get("GEMINI_API_BASE", "").strip()
    if base and GEMINI_HOST not in base:
        raise ValueError("GEMINI_API_BASE is not the Gemini endpoint; refusing to judge with another model")
    if os.environ.get("GEMINI_API_KEY_ONLY", "").strip() and os.environ.get("MINIRAG_SLM_KEY", "").strip() \
            and os.environ["GEMINI_API_KEY_ONLY"].strip() == os.environ["MINIRAG_SLM_KEY"].strip():
        raise ValueError("GEMINI_API_KEY_ONLY is the Modal SLM key; refusing to judge")


async def judge_one(complete, prompt_text, *, invalid_tries, api_tries, api_wait):
    """Return (status, label, attempts). complete(prompt) -> reply text."""
    import llm_trace

    attempts, invalid, failures = [], 0, 0
    while True:
        requests = []
        try:
            with llm_trace.trace(requests.append):
                reply = await complete(prompt_text)
        except Exception as exc:
            failures += 1
            attempts.append({"ok": False, "error_type": type(exc).__name__, "requests": requests})
            if failures >= api_tries:
                return "judge_failed", None, attempts
            await asyncio.sleep(api_wait * failures)
            continue
        label = parse_label(reply)
        attempts.append({"ok": True, "raw": reply, "label": label, "requests": requests})
        if label:
            return "ok", label, attempts
        invalid += 1
        if invalid >= invalid_tries:
            return "parse_failed", None, attempts


def read_records(path):
    latest = {}
    if path.exists():
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        for i, line in enumerate(lines):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                if i == len(lines) - 1:
                    break  # torn by a crash or power-off mid-write: that verdict is simply judged again
                raise ValueError(f"{path}: corrupt record on line {i + 1}") from None
            latest[(r["query_id"], r["pass"])] = r  # last record wins on resume
    return latest


def summarize(rows, latest, passes):
    def rates(labels):
        n = len(labels)
        return {k: round(100 * sum(1 for x in labels if x == k) / n, 2) for k in (*LABELS, "no_majority")} | {"n": n}

    def mean_sd(values):
        return {"mean": round(statistics.mean(values), 2),
                "sd": round(statistics.stdev(values), 2) if len(values) > 1 else 0.0}

    groups = {"all": rows}
    for r in rows:
        groups.setdefault(r["type"], []).append(r)
    out = {}
    for name, group in sorted(groups.items()):
        per_pass = [rates([latest[(r["query_id"], p)]["label"] for r in group]) for p in range(1, passes + 1)]
        out[name] = {
            "early_exit": sum(1 for r in group if r["early_exit"]),
            "majority": rates([majority([latest[(r["query_id"], p)]["label"] for p in range(1, passes + 1)])
                               for r in group]),
            "per_pass": per_pass,
            "pass_mean_sd": {k: mean_sd([pp[k] for pp in per_pass]) for k in LABELS},
        }
    return out


async def run(args, rows, complete):
    args.run_dir.mkdir(parents=True, exist_ok=True)
    identity = {
        "questions_sha256": sha256_file(args.questions), "answers_sha256": sha256_file(args.answers),
        "answer_column": args.column, "judge_model": args.judgemodel, "passes": args.passes, "seed": args.seed,
        "prompt_sha256": hashlib.sha256(args.prompt.encode()).hexdigest(), "invalid_tries": args.invalid_tries,
        "label_contract": list(LABELS),
    }
    manifest_path = args.run_dir / "manifest.json"
    if manifest_path.exists():
        if not args.resume:
            raise ValueError("Run directory already holds a judge run; use --resume or a new directory")
        if json.loads(manifest_path.read_text(encoding="utf-8")) != identity:
            raise ValueError("Inputs or settings differ from the existing judge run; refusing to resume")
    elif args.resume:
        raise ValueError("Nothing to resume in this directory")
    else:
        manifest_path.write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")

    journal = args.run_dir / "judge.jsonl"
    latest = read_records(journal)
    sem = asyncio.Semaphore(args.concurrency)
    lock = asyncio.Lock()

    async def one(row, pass_id, fh):
        prompt_text = args.prompt.format(question=row["question"], gold=row["gold"], pred=row["pred"])
        async with sem:
            status, label, attempts = await judge_one(
                complete, prompt_text, invalid_tries=args.invalid_tries,
                api_tries=args.api_tries, api_wait=args.api_wait)
        record = {"query_id": row["query_id"], "pass": pass_id, "status": status, "label": label,
                  "type": row["type"], "attempts": attempts}
        async with lock:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        latest[(row["query_id"], pass_id)] = record

    with journal.open("a", encoding="utf-8") as fh:
        for pass_id in range(1, args.passes + 1):
            order = list(rows)
            random.Random(args.seed + pass_id).shuffle(order)  # Step_2_evaluate's order randomisation
            todo = [r for r in order if latest.get((r["query_id"], pass_id), {}).get("status") != "ok"]
            if todo:
                print(f"pass {pass_id}: judging {len(todo)}")
                await asyncio.gather(*(one(r, pass_id, fh) for r in todo))

    statuses = collections.Counter(latest[(r["query_id"], p)]["status"]
                                   for r in rows for p in range(1, args.passes + 1))
    with (args.run_dir / "per_question.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["query_id", "Type", *[f"pass{p}" for p in range(1, args.passes + 1)], "majority"])
        for r in rows:
            labels = [latest[(r["query_id"], p)]["label"] or latest[(r["query_id"], p)]["status"]
                      for p in range(1, args.passes + 1)]
            done = all(latest[(r["query_id"], p)]["status"] == "ok" for p in range(1, args.passes + 1))
            w.writerow([r["query_id"], r["type"], *labels, majority(labels) if done else "incomplete"])

    if set(statuses) != {"ok"}:
        print(f"INCOMPLETE: {dict(statuses)} -- rerun with --resume; no summary written")
        return 1
    summary = {"status": "completed", "n_questions": len(rows), "passes": args.passes,
               "groups": summarize(rows, latest, args.passes)}
    (args.run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    overall = summary["groups"]["all"]
    print(f"early exits (canned fail_response): {overall['early_exit']}")
    print(f"majority: {overall['majority']}")
    print(f"pass mean/sd: {overall['pass_mean_sd']}")
    return 0


def parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--questions", type=Path, required=True, help="CSV with query_id, Question, Gold Answer, Type")
    p.add_argument("--answers", type=Path, required=True, help="answers.csv exported by qa_run.py")
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--column", default="minirag")
    p.add_argument("--judgemodel", default="gemini-flash-lite-latest")
    p.add_argument("--passes", type=int, default=3)
    p.add_argument("--seed", type=int, default=13)
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--invalid-tries", type=int, default=3, help="Asks per record before parse_failed")
    p.add_argument("--api-tries", type=int, default=6, help="API failures per record before judge_failed")
    p.add_argument("--api-wait", type=float, default=60.0, help="Seconds x failure count between API retries")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "reproduce"))
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    require_gemini_endpoint()
    import llm_trace
    from minirag.llm.gemini import gemini_complete_if_cache
    from Step_2_evaluate import JUDGE_PROMPT
    from minirag.prompt import PROMPTS

    llm_trace.install()
    args.prompt = JUDGE_PROMPT
    rows = load_rows(args.questions, args.answers, args.column, PROMPTS["fail_response"])

    async def complete(prompt_text):
        return await gemini_complete_if_cache(args.judgemodel, prompt_text)

    return asyncio.run(run(args, rows, complete))


if __name__ == "__main__":
    sys.exit(main())
