"""Paired comparison of two judged MultiHop-RAG runs, exactly as pre-registered
(MULTIHOP_RAG_ROADMAP.md, "Câu hỏi nghiên cứu và phép thử", commit 7013291).

Inputs are two judge_run.py directories over the same questions and the same
generation seed (per_question.csv + summary.json). For B against A:

  primary    accurate vs not-accurate on the majority-of-3 verdict
             (error, neither, no_majority all count as not accurate);
             exact McNemar on the discordant pairs, "b up / c down, p";
             paired bootstrap of the accuracy difference (resample questions,
             keep each question's A/B pair), 10,000 draws, seed 13, 95% CI;
             non-inferiority only if the CI's lower bound > -3 points
  secondary  error vs not-error, McNemar (up = fewer errors under B)
  described  per-pass mean +/- sd (judge noise) from summary.json, neither,
             no_majority, early exits -- never mixed into the tests

Every question must have a complete verdict in both runs; otherwise the
comparison is refused.

    python reproduce/research/compare_mhr.py runs/multihop_rag/dev400/C0_s101/judge \
        runs/multihop_rag/dev400/C1_s101/judge --names C0 C1 [--types null] [--out result.json]
"""

import argparse
import csv
import importlib.util
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("screen_variant", ROOT / "reproduce/screening/screen_variant.py")
_screen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_screen)
mcnemar_p = _screen.mcnemar_p  # the registered implementation (exact, two-sided)

DRAWS, SEED, MARGIN = 10_000, 13, -3.0


def load(judge_dir):
    with open(Path(judge_dir) / "per_question.csv", newline="", encoding="utf-8") as f:
        rows = {r["query_id"]: r for r in csv.DictReader(f)}
    incomplete = [q for q, r in rows.items() if r["majority"] == "incomplete"]
    if incomplete:
        raise ValueError(f"{judge_dir}: {len(incomplete)} questions without a complete verdict")
    summary_path = Path(judge_dir) / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else None
    return rows, summary


def paired(a_flags, b_flags):
    """b = A false -> B true, c = A true -> B false."""
    up = sum(1 for x, y in zip(a_flags, b_flags) if not x and y)
    down = sum(1 for x, y in zip(a_flags, b_flags) if x and not y)
    return up, down, mcnemar_p(up, down)


def bootstrap_ci(a_flags, b_flags, draws=DRAWS, seed=SEED):
    n = len(a_flags)
    diffs = [int(y) - int(x) for x, y in zip(a_flags, b_flags)]
    rng = random.Random(seed)
    stats = sorted(100 * sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(draws))
    return stats[int(0.025 * draws)], stats[int(0.975 * draws) - 1]


def compare(rows_a, rows_b, types=None):
    if set(rows_a) != set(rows_b):
        raise ValueError("the two runs do not cover the same questions")
    ids = sorted(q for q in rows_a if not types or rows_a[q]["Type"] in types)
    if not ids:
        raise ValueError("no questions selected")
    acc_a = [rows_a[q]["majority"] == "accurate" for q in ids]
    acc_b = [rows_b[q]["majority"] == "accurate" for q in ids]
    err_a = [rows_a[q]["majority"] == "error" for q in ids]
    err_b = [rows_b[q]["majority"] == "error" for q in ids]
    up, down, p = paired(acc_a, acc_b)
    # Secondary: "up" means fewer errors under B, so pass the flags as not-error.
    e_up, e_down, e_p = paired([not x for x in err_a], [not x for x in err_b])
    lo, hi = bootstrap_ci(acc_a, acc_b)
    n = len(ids)

    def share(flags):
        return round(100 * sum(flags) / n, 2)

    def label_share(rows, label):
        return round(100 * sum(1 for q in ids if rows[q]["majority"] == label) / n, 2)

    return {
        "n": n,
        "primary_accurate": {"acc_a": share(acc_a), "acc_b": share(acc_b),
                             "diff": round(share(acc_b) - share(acc_a), 2), "up": up, "down": down, "p": p,
                             "ci95": [round(lo, 2), round(hi, 2)], "noninferior_at_-3": lo > MARGIN},
        "secondary_error": {"err_a": share(err_a), "err_b": share(err_b), "fewer_errors": e_up,
                            "more_errors": e_down, "p": e_p},
        "described": {name: {"neither": label_share(rows, "neither"), "no_majority": label_share(rows, "no_majority")}
                      for name, rows in (("a", rows_a), ("b", rows_b))},
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("a", type=Path, help="judge dir of the reference config")
    p.add_argument("b", type=Path, help="judge dir of the config compared against it")
    p.add_argument("--names", nargs=2, default=("A", "B"))
    p.add_argument("--types", nargs="*", help="restrict to these question types (e.g. null)")
    p.add_argument("--out", type=Path)
    args = p.parse_args(argv)

    rows_a, summary_a = load(args.a)
    rows_b, summary_b = load(args.b)
    result = {"a": args.names[0], "b": args.names[1], "types": args.types or "all",
              "overall": compare(rows_a, rows_b, args.types)}
    types = sorted({r["Type"] for r in rows_a.values()})
    if not args.types:
        result["by_type"] = {t: compare(rows_a, rows_b, [t]) for t in types}
    result["pass_mean_sd"] = {name: (s or {}).get("groups", {}).get("all", {}).get("pass_mean_sd")
                              for name, s in zip(args.names, (summary_a, summary_b))}
    result["early_exit"] = {name: (s or {}).get("groups", {}).get("all", {}).get("early_exit")
                            for name, s in zip(args.names, (summary_a, summary_b))}
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    o = result["overall"]["primary_accurate"]
    print(f"{args.names[1]} vs {args.names[0]} (n={result['overall']['n']}): acc {o['acc_a']} -> {o['acc_b']} "
          f"({o['diff']:+}), {o['up']} up / {o['down']} down, p = {o['p']:.3g}, 95% CI {o['ci95']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
