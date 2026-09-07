"""Step 4 - score the run with the RAGAS metrics.

Uses the real `ragas` package so the metric definitions are theirs, not mine,
but points its LLM at the shared Gemini key pool and its embedder at the local
MiniLM model, so the run is rate-limited like everything else and answer
relevancy costs no API quota.

    python reproduce/Step_4_ragas.py --input ./logs/gemini_output_context.jsonl
"""

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(_HERE)
sys.path.append(os.path.dirname(_HERE))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(_HERE), ".env"))

from datasets import Dataset  # noqa: E402
from ragas import evaluate  # noqa: E402
from ragas.metrics import (  # noqa: E402
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)
from ragas.run_config import RunConfig  # noqa: E402

from ragas_adapters import GeminiPoolLLM, LocalEmbeddings  # noqa: E402


def get_args():
    p = argparse.ArgumentParser(description="RAGAS scoring")
    p.add_argument("--input", default="./logs/gemini_output_context.jsonl")
    p.add_argument("--output", default="./logs/ragas_scores.csv")
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Score only the first N samples (0 = all). RAGAS spends several "
        "LLM calls per sample, so this is the knob that decides runtime.",
    )
    p.add_argument(
        "--stratified",
        type=int,
        default=0,
        help="Sample N items keeping the Single/Multi/Null proportions of the "
        "full set. The query file is ordered, so a plain head-N slice would "
        "skew the mix; prefer this over --limit for a subset.",
    )
    p.add_argument("--seed", type=int, default=13, help="Sampling seed.")
    p.add_argument("--model", default="gemini-flash-lite-latest")
    p.add_argument(
        "--batch",
        type=int,
        default=10,
        help="Samples per chunk; each chunk is written out before the next "
        "starts, so a quota stall never loses finished work. Kept small on "
        "purpose: under a daily-quota outage a large batch can grind for hours "
        "without committing anything, and dies with all of it uncommitted.",
    )
    return p.parse_args()


def main():
    args = get_args()

    rows = []
    with open(args.input, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            # A sample with no retrieved context makes the context metrics
            # undefined rather than zero, so drop it and say how many.
            if r["contexts"] and r["answer"]:
                rows.append(r)
    dropped_total = 0
    with open(args.input, encoding="utf-8") as f:
        dropped_total = sum(1 for _ in f) - len(rows)
    if args.stratified:
        import collections
        import random

        rng = random.Random(args.seed)
        by_type = collections.defaultdict(list)
        for r in rows:
            by_type[r.get("type") or "?"].append(r)
        total = len(rows)
        picked = []
        for t, group in sorted(by_type.items()):
            # Largest-remainder would be tidier, but rounding up keeps every
            # stratum represented even when a type is a thin slice of the set.
            k = min(len(group), max(1, round(args.stratified * len(group) / total)))
            picked += rng.sample(group, k)
        rng.shuffle(picked)
        rows = picked[: args.stratified]
        mix = collections.Counter(r.get("type") or "?" for r in rows)
        print(f"lấy mẫu phân tầng (seed {args.seed}): {dict(mix)}")
    elif args.limit:
        rows = rows[: args.limit]
    print(f"chấm {len(rows)} mẫu (bỏ {dropped_total} mẫu thiếu ngữ cảnh/câu trả lời)")

    done = set()
    if os.path.exists(args.output):
        import csv as _csv

        with open(args.output, encoding="utf-8") as f:
            for r in _csv.DictReader(f):
                done.add(r["question"])
        print(f"resuming: {len(done)} mẫu đã chấm")
    todo = [r for r in rows if r["question"] not in done]

    llm = GeminiPoolLLM(args.model)
    emb = LocalEmbeddings()
    metrics = [faithfulness, answer_relevancy, context_precision, context_recall]
    # max_workers=1: the key pool already paces requests, and letting RAGAS fan
    # out on top of it just produces 429s the pool then has to back off from.
    # The long timeout is not slack -- a single job legitimately waits minutes
    # when the pool is throttling, and a timeout here silently becomes a NaN
    # cell rather than an error, quietly thinning the sample.
    run_config = RunConfig(
        max_workers=1,
        timeout=int(os.environ.get("RAGAS_TIMEOUT", "3600")),
        max_retries=3,
    )

    import csv as _csv

    header = [
        "question",
        "type",
        "faithfulness",
        "answer_relevancy",
        "context_precision",
        "context_recall",
    ]
    # Existence is not enough: a run killed before its first flush leaves a
    # 0-byte file, and skipping the header then produces a headerless CSV whose
    # resume logic silently eats the first data row as a header.
    write_header = not (
        os.path.exists(args.output) and os.path.getsize(args.output) > 0
    )
    with open(args.output, "a", newline="", encoding="utf-8") as fh:
        w = _csv.writer(fh)
        if write_header:
            w.writerow(header)

        for i in range(0, len(todo), args.batch):
            batch = todo[i : i + args.batch]
            ds = Dataset.from_dict(
                {
                    "question": [b["question"] for b in batch],
                    "answer": [b["answer"] for b in batch],
                    "contexts": [b["contexts"] for b in batch],
                    "ground_truth": [b["ground_truth"] for b in batch],
                }
            )
            res = evaluate(
                ds,
                metrics=metrics,
                llm=llm,
                embeddings=emb,
                run_config=run_config,
                raise_exceptions=False,
            )
            df = res.to_pandas()
            for b, (_, r) in zip(batch, df.iterrows()):
                w.writerow(
                    [
                        b["question"],
                        b.get("type", ""),
                        r.get("faithfulness"),
                        r.get("answer_relevancy"),
                        r.get("context_precision"),
                        r.get("context_recall"),
                    ]
                )
            fh.flush()
            print(f"  đã chấm {min(i + args.batch, len(todo))}/{len(todo)}")

    # Report means over everything scored so far, not just this run's batches.
    import pandas as pd

    df = pd.read_csv(args.output)
    print(f"\nn = {len(df)}")
    for m in header[2:]:
        col = df[m].dropna()
        if len(col):
            print(f"{m:<20} {col.mean():.4f}   (n={len(col)})")
        else:
            print(f"{m:<20} không tính được")
    print(f"\nchi tiết từng mẫu: {args.output}")


main()
