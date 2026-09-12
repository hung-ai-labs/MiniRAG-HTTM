"""Step 2 - score a run into acc / err using the paper's judging protocol.

MiniRAG's paper judges each answer with an LLM and, to keep the numbers
robust, "repeated each evaluation three times with order randomization,
reporting means and variance". This does the same: N independent judging
passes over a shuffled question order, then mean +/- std across passes.

Running once is not enough to compare two configurations: without the spread
across passes there is no way to tell a real gain from the judge changing its
mind, and single-pass judging on this task moves by a few points on its own.

Verdicts follow the paper's definitions:
  accurate - semantically equivalent to the gold answer ("water bottle" for
             a gold answer of "bottle")
  error    - asserts something wrong without acknowledging it ("yoga mat")
  neither  - says it does not know, refuses, or is off-topic

    export GEMINI_API_KEY=...
    python reproduce/Step_2_evaluate.py --inputpath ./logs/gemini_output.csv \
        --repeats 3
"""

import argparse
import asyncio
import collections
import csv
import os
import random
import statistics
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(_HERE)
sys.path.append(os.path.dirname(_HERE))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(_HERE), ".env"))

from minirag.llm.gemini import gemini_complete_if_cache  # noqa: E402

csv.field_size_limit(10**9)

JUDGE_PROMPT = """You are grading a question-answering system.

Question: {question}
Gold answer: {gold}
System answer: {pred}

Reply with exactly one word:
- "accurate" if the system answer conveys the gold answer. Wording may differ;
  a more specific but consistent answer still counts (gold "bottle", answer
  "water bottle" -> accurate).
- "error" if the system answer asserts something that contradicts the gold
  answer, without acknowledging any uncertainty.
- "neither" if the system answer says it does not know, refuses to answer, or
  is off-topic.
"""


def get_args():
    p = argparse.ArgumentParser(description="Score MiniRAG output (acc / err)")
    p.add_argument("--inputpath", required=True)
    p.add_argument("--output", default="", help="default: <input>_judged.csv")
    p.add_argument("--queryset", default="./dataset/LiHua-World/qa/query_set.csv",
                   help="Used only to attach the Type column for the breakdown.")
    p.add_argument("--judgemodel", default="gemini-flash-lite-latest")
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--column", default="minirag")
    p.add_argument("--repeats", type=int, default=3,
                   help="Independent judging passes (the paper uses 3).")
    p.add_argument("--seed", type=int, default=13)
    return p.parse_args()


# A failed API call used to return "neither", which silently turned quota
# exhaustion into a verdict: the run looked complete while every failure was
# scored as an abstention. On the 637-question run that fabricated 25 verdicts
# before it was caught. Retry instead, and if the judge truly cannot be reached,
# emit a distinct label so summarize() can refuse to report the pass.
JUDGE_FAILED = "judge_failed"


async def judge(sem, model, row, column):
    for attempt in range(6):
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
                break
            except Exception as e:
                if attempt == 5:
                    print("judge error (bỏ cuộc sau 6 lần):", e)
                    return JUDGE_FAILED
                wait = 60 * (attempt + 1)   # hạn mức ngày chỉ hồi sau nhiều phút
                print(f"judge error: {e} — thử lại sau {wait}s ({attempt + 1}/5)")
        await asyncio.sleep(wait)
    verdict = (verdict or "").strip().lower()
    for label in ("accurate", "error", "neither"):
        if label in verdict:
            return label
    return "neither"


def summarize(records, label_of_type):
    """acc/err per pass, then mean +/- std across passes, overall and per type."""
    by_run = collections.defaultdict(list)
    for r in records:
        by_run[r["run"]].append(r)

    def rates(rows):
        n = len(rows)
        if not n:
            return None, None
        c = collections.Counter(x["verdict"] for x in rows)
        return c["accurate"] / n * 100, c["error"] / n * 100

    failed = sum(1 for r in records if r["verdict"] == JUDGE_FAILED)
    if failed:
        print(f"\n⛔ {failed} lượt chấm THẤT BẠI (không gọi được judge).")
        print("   Số dưới đây KHÔNG dùng được: mẫu thiếu, và phần thiếu không ngẫu nhiên")
        print("   (hạn mức cạn dần nên lỗi dồn về cuối danh sách). Chạy lại khi có quota.")

    print(f"\n{'':<10}{'acc %':>18}{'err %':>18}")
    accs, errs = [], []
    for run in sorted(by_run):
        a, e = rates(by_run[run])
        accs.append(a)
        errs.append(e)
        print(f"lượt {run:<5}{a:>17.2f}{e:>18.2f}")

    def pm(vals):
        if len(vals) < 2:
            return f"{vals[0]:.2f}" if vals else "-"
        return f"{statistics.mean(vals):.2f} ± {statistics.stdev(vals):.2f}"

    n = len(by_run[sorted(by_run)[0]])
    print(f"{'-' * 46}")
    print(f"{'TỔNG':<10}{pm(accs):>17}{pm(errs):>18}   (n={n})")

    types = sorted({label_of_type.get(r['question'], '?') for r in records})
    if len(types) > 1:
        print(f"\n{'theo loại':<10}{'acc %':>18}{'err %':>18}{'n':>6}")
        for t in types:
            a_l, e_l = [], []
            for run in sorted(by_run):
                rows = [x for x in by_run[run]
                        if label_of_type.get(x["question"]) == t]
                a, e = rates(rows)
                if a is not None:
                    a_l.append(a)
                    e_l.append(e)
            cnt = len([x for x in by_run[sorted(by_run)[0]]
                       if label_of_type.get(x["question"]) == t])
            print(f"{t:<10}{pm(a_l):>17}{pm(e_l):>18}{cnt:>6}")

    if len(accs) > 1:
        print(
            f"\nSÀN NHIỄU JUDGE: acc dao động {max(accs) - min(accs):.2f} điểm "
            f"giữa các lượt (sd {statistics.stdev(accs):.2f}).\n"
            "Chênh lệch nhỏ hơn mức này giữa hai cấu hình không kết luận được."
        )


async def main():
    args = get_args()
    out = args.output or (os.path.splitext(args.inputpath)[0] + "_judged.csv")

    with open(args.inputpath, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    label_of_type = {}
    if os.path.exists(args.queryset):
        with open(args.queryset, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                label_of_type[r["Question"]] = r.get("Type", "?")

    # Resume is keyed on (question, run): a pass interrupted halfway costs only
    # the judgments it had not reached.
    done = set()
    records = []
    if os.path.exists(out) and os.path.getsize(out) > 0:
        with open(out, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                done.add((r["question"], int(r["run"])))
                records.append({"question": r["question"], "run": int(r["run"]),
                                "verdict": r["verdict"]})
        print(f"resuming: {len(done)} lượt chấm đã có")

    sem = asyncio.Semaphore(args.concurrency)
    write_header = not (os.path.exists(out) and os.path.getsize(out) > 0)

    with open(out, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if write_header:
            w.writerow(["question", "type", "run", "verdict"])

        for run in range(1, args.repeats + 1):
            # Order randomization, per the paper's protocol.
            order = list(rows)
            random.Random(args.seed + run).shuffle(order)
            todo = [r for r in order if (r["Question"], run) not in done]
            if not todo:
                continue
            print(f"lượt {run}: chấm {len(todo)} câu")

            for i in range(0, len(todo), args.concurrency * 5):
                chunk = todo[i : i + args.concurrency * 5]
                got = await asyncio.gather(
                    *[judge(sem, args.judgemodel, r, args.column) for r in chunk]
                )
                for r, v in zip(chunk, got):
                    # Không ghi hàng thất bại ra file: resume ở dòng 208 bỏ qua
                    # mọi (câu, lượt) đã có trong file, nên ghi vào là lần chạy
                    # sau sẽ vĩnh viễn không chấm lại chúng.
                    if v != JUDGE_FAILED:
                        w.writerow([r["Question"],
                                    label_of_type.get(r["Question"], "?"), run, v])
                    records.append({"question": r["Question"], "run": run,
                                    "verdict": v})
                fh.flush()
                print(f"  {min(i + len(chunk), len(todo))}/{len(todo)}")

    summarize(records, label_of_type)
    print(f"\nchi tiết từng lượt: {out}")
    # Thoát khác 0 khi có lượt chấm hỏng, để `until ...` ở script gọi ngoài chờ
    # rồi chạy lại. Thoát 0 ở đây là lặng lẽ công bố một bảng số thiếu mẫu.
    if any(r["verdict"] == JUDGE_FAILED for r in records):
        sys.exit(1)


asyncio.run(main())
