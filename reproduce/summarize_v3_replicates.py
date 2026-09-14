"""Tổng hợp các lượt sinh lặp lại của V3 (trộn RRF) so với baseline qwen637_fix.

Tách hai nguồn nhiễu mà trước đây bị gộp làm một:
  - nhiễu giám khảo: sd giữa 3 lượt chấm CÙNG một file (con số ± trong mọi bảng cũ)
  - nhiễu giữa các lần chạy: sd của acc giữa các lượt SINH khác nhau (Qwen lấy mẫu)
Mỗi lượt được McNemar chính xác với baseline trên phán quyết đa số, tổng và 435 câu ngoài dev.

    python reproduce/summarize_v3_replicates.py [--runs v3 v3_r2 v3_r3]
"""

import argparse
import collections
import csv
import statistics as st

from scipy.stats import binomtest

p = argparse.ArgumentParser()
p.add_argument("--base", default="fix")
p.add_argument("--runs", nargs="+", default=["v3", "v3_r2", "v3_r3"])
args = p.parse_args()


def load(tag):
    passes = collections.defaultdict(dict)
    votes = collections.defaultdict(list)
    types = {}
    for r in csv.DictReader(open(f"logs/qwen637_{tag}_judged.csv", encoding="utf-8")):
        passes[r["run"]][r["question"]] = r["verdict"]
        votes[r["question"]].append(r["verdict"])
        types[r["question"]] = r["type"]
    major = {q: collections.Counter(v).most_common(1)[0][0] for q, v in votes.items()}
    return passes, major, types


def rates(passes, qs, label):
    vals = [100 * sum(d.get(q) == label for q in qs) / len(qs) for d in passes.values()]
    return st.mean(vals), (st.stdev(vals) if len(vals) > 1 else 0.0)


def mcnemar(base, new, qs):
    b = sum(new[q] == "accurate" and base[q] != "accurate" for q in qs)
    c = sum(base[q] == "accurate" and new[q] != "accurate" for q in qs)
    return b, c, (binomtest(b, b + c, 0.5).pvalue if b + c else 1.0)


base_passes, base_major, types = load(args.base)
runs = {t: load(t) for t in args.runs}
qs_all = sorted(set(base_major).intersection(*[set(m) for _, m, _ in runs.values()]))
dev = {r["Question"] for r in csv.DictReader(open("logs/devset.csv", encoding="utf-8"))}
groups = {"TỔNG": qs_all, "Single": [q for q in qs_all if types[q] == "Single"],
          "Multi": [q for q in qs_all if types[q] == "Multi"],
          "Null": [q for q in qs_all if types[q] == "Null"],
          "ngoài dev": [q for q in qs_all if q not in dev]}

print(f"V3 LẶP LẠI — {len(args.runs)} lượt sinh × 3 lượt chấm, {len(qs_all)} câu ghép được")
print(f"baseline: qwen637_{args.base}; các lượt: {', '.join('qwen637_' + t for t in args.runs)}\n")

for g, qs in groups.items():
    ba, _ = rates(base_passes, qs, "accurate")
    per_run = [rates(runs[t][0], qs, "accurate") for t in args.runs]
    accs = [a for a, _ in per_run]
    errs = [rates(runs[t][0], qs, "error")[0] for t in args.runs]
    between = st.stdev(accs) if len(accs) > 1 else 0.0
    within = st.mean(s for _, s in per_run)
    print(f"{g:<10} n={len(qs):<4} baseline {ba:6.2f} │ V3 các lượt "
          + " / ".join(f"{a:.2f}" for a in accs)
          + f" │ trung bình {st.mean(accs):.2f} ± {between:.2f} (giữa lượt sinh), "
          f"nhiễu giám khảo {within:.2f} │ err TB {st.mean(errs):.2f} │ Δ so baseline {st.mean(accs) - ba:+.2f}")

print("\nMcNEMAR TỪNG LƯỢT so với baseline (phán quyết đa số, nhị thức chính xác)")
for t in args.runs:
    major = runs[t][1]
    cells = []
    for g in ("TỔNG", "Null", "ngoài dev"):
        b, c, pv = mcnemar(base_major, major, groups[g])
        cells.append(f"{g} {b} lên / {c} xuống, p = {pv:.2g}")
    print(f"  {t:<7} " + " · ".join(cells))

print("\nĐỒNG THUẬN GIỮA CÁC LƯỢT SINH (phán quyết đa số)")
majors = [runs[t][1] for t in args.runs]
for i in range(len(args.runs)):
    for j in range(i + 1, len(args.runs)):
        same = sum(majors[i][q] == majors[j][q] for q in qs_all)
        print(f"  {args.runs[i]} vs {args.runs[j]}: cùng phán quyết {same}/{len(qs_all)} = {100 * same / len(qs_all):.1f}%")
n_acc = collections.Counter(sum(m[q] == "accurate" for m in majors) for q in qs_all)
print("  số lượt được chấm accurate trên mỗi câu: "
      + " · ".join(f"{k}/{len(majors)} lượt: {n_acc[k]} câu" for k in range(len(majors), -1, -1)))
