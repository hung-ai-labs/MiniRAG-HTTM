"""Freeze a stratified dev set, and report the current baseline on it.

Every tuning experiment must be scored on the *same* questions, otherwise a
change in the sample gets mistaken for a change in the system. This writes the
question list once; re-running with the same seed reproduces it exactly.

The baseline costs nothing: the full 637-question run is already scored, so the
dev-set baseline is a lookup, not a re-run.

    python reproduce/make_devset.py --size 200
"""

import argparse
import collections
import csv
import os
import random
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(_HERE))

csv.field_size_limit(10**9)


def get_args():
    p = argparse.ArgumentParser(description="Freeze a stratified dev set")
    p.add_argument("--queryset", default="./dataset/LiHua-World/qa/query_set.csv")
    p.add_argument("--scored", default="./logs/gemini_output_scored.csv")
    p.add_argument("--out", default="./logs/devset.csv")
    p.add_argument("--size", type=int, default=200)
    p.add_argument("--seed", type=int, default=13)
    return p.parse_args()


def main():
    args = get_args()

    with open(args.queryset, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    by_type = collections.defaultdict(list)
    for r in rows:
        by_type[r.get("Type") or "?"].append(r)

    rng = random.Random(args.seed)
    picked = []
    for t, group in sorted(by_type.items()):
        k = min(len(group), max(1, round(args.size * len(group) / len(rows))))
        picked += rng.sample(group, k)
    rng.shuffle(picked)
    picked = picked[: args.size]

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(picked)

    mix = collections.Counter(r.get("Type") for r in picked)
    full_mix = collections.Counter(r.get("Type") for r in rows)
    print(f"dev set: {len(picked)} câu -> {args.out}  (seed {args.seed})")
    for t in sorted(mix):
        print(
            f"  {t:<8} {mix[t]:>3}  ({mix[t]/len(picked):.1%}"
            f"  vs {full_mix[t]/len(rows):.1%} toàn bộ)"
        )

    if not os.path.exists(args.scored):
        print(f"\n(chưa có {args.scored}, bỏ qua baseline)")
        return

    with open(args.scored, encoding="utf-8") as f:
        verdicts = {r["Question"]: r["verdict"] for r in csv.DictReader(f)}

    want = {r["Question"] for r in picked}
    have = [v for q, v in verdicts.items() if q in want]
    missing = len(want) - len(have)

    c = collections.Counter(have)
    n = len(have)
    print(f"\nBASELINE trên dev set  (n={n}" + (f", thiếu {missing}" if missing else "") + ")")
    print(f"  accuracy   {c['accurate'] / n:6.2%}   ({c['accurate']})")
    print(f"  error      {c['error'] / n:6.2%}   ({c['error']})")
    print(f"  không TL   {c['neither'] / n:6.2%}   ({c['neither']})")

    print("\n  theo loại:")
    tmap = {r["Question"]: r.get("Type") for r in picked}
    per = collections.defaultdict(collections.Counter)
    for q, v in verdicts.items():
        if q in want:
            per[tmap[q]][v] += 1
    for t in sorted(per):
        cc = per[t]
        m = sum(cc.values())
        print(f"    {t:<8} n={m:>3}  acc={cc['accurate']/m:6.2%}  err={cc['error']/m:6.2%}")


main()
