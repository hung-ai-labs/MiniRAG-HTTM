"""Step 2 - score a Step_1 output CSV into the paper's acc / err metrics.

Each (question, gold answer, prediction) triple is judged by Gemini:
  accurate  -> the prediction conveys the gold answer
  error     -> the prediction asserts something contradicting the gold answer
  neither   -> the prediction refuses / is off-topic / says it doesn't know

    export GEMINI_API_KEY=your_key
    python ./reproduce/Step_2_evaluate.py --inputpath ./logs/gemini_output.csv
"""

import argparse
import asyncio
import csv
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
)

from minirag.llm.gemini import gemini_complete_if_cache  # noqa: E402

JUDGE_PROMPT = """You are grading a question-answering system.

Question: {question}
Gold answer: {gold}
System answer: {pred}

Reply with exactly one word:
- "accurate" if the system answer conveys the gold answer (wording may differ).
- "error" if the system answer states something that contradicts the gold answer.
- "neither" if the system answer is a refusal, says it does not know, or is off-topic.
"""


def get_args():
    parser = argparse.ArgumentParser(description="Score MiniRAG output")
    parser.add_argument("--inputpath", type=str, required=True)
    parser.add_argument("--judgemodel", type=str, default="gemini-flash-lite-latest")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--column", type=str, default="minirag")
    return parser.parse_args()


async def judge(sem, model, row, column):
    async with sem:
        try:
            verdict = await gemini_complete_if_cache(
                model,
                JUDGE_PROMPT.format(
                    question=row["Question"],
                    gold=row["Gold Answer"],
                    pred=row[column],
                ),
            )
        except Exception as e:
            print("judge error:", e)
            return "neither"
    verdict = verdict.strip().lower()
    for label in ("accurate", "error", "neither"):
        if label in verdict:
            return label
    return "neither"


async def main():
    args = get_args()
    with open(args.inputpath, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f)]

    out = os.path.splitext(args.inputpath)[0] + "_scored.csv"

    # Resume: rows already judged in a previous run are kept, so a quota
    # exhaustion partway through costs nothing but the unjudged remainder.
    done = {}
    if os.path.exists(out):
        with open(out, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                done[r["Question"]] = r["verdict"]
        print(f"resuming: {len(done)} rows already scored")

    todo = [r for r in rows if r["Question"] not in done]
    sem = asyncio.Semaphore(args.concurrency)

    write_header = not os.path.exists(out)
    with open(out, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["Question", "Gold Answer", args.column, "verdict"])
        # Judge in chunks so progress is flushed to disk as it is made.
        for i in range(0, len(todo), args.concurrency):
            batch = todo[i : i + args.concurrency]
            got = await asyncio.gather(
                *[judge(sem, args.judgemodel, r, args.column) for r in batch]
            )
            for r, v in zip(batch, got):
                writer.writerow([r["Question"], r["Gold Answer"], r[args.column], v])
                done[r["Question"]] = v
            f.flush()

    verdicts = [done[r["Question"]] for r in rows if r["Question"] in done]
    total = len(verdicts)
    acc = verdicts.count("accurate")
    err = verdicts.count("error")

    print(f"\nn         = {total}")
    print(f"accuracy  = {acc / total:.2%}  ({acc})")
    print(f"error     = {err / total:.2%}  ({err})")
    print(f"per-row verdicts written to {out}")


asyncio.run(main())
