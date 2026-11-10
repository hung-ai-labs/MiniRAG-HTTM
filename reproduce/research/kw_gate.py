"""Gate G4a of the LiHua MiniCPM ablation (amendment M2 of LIHUA_ABLATION_MINICPM.md): keyword-format compliance.

Reads, for each seed, kw_attempts_s<seed>.jsonl and kw_s<seed>.jsonl written by phased_qa.py keywords and checks
that at least 95% of the questions have a usable keyword reply after at most 1 + KW_RETRIES attempts. Also writes the
query ids whose reply was usable at attempt 0 (sensitivity analysis S-kw). No model calls.

    python reproduce/research/kw_gate.py --root runs/lihua_world/ablation_minicpm --questions dataset/LiHua-World/splits/nondev435.csv \
        --out runs/lihua_world/ablation_minicpm/kw_gate.json
"""

import argparse
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phased_qa  # noqa: E402

THRESHOLD = 95.0  # percent of questions usable after retries, each seed (registered in M2)


def rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def seed_report(root, seed, query_ids):
    attempts = {}
    for r in rows(Path(root) / f"kw_attempts_s{seed}.jsonl"):
        attempts.setdefault(r["query_id"], []).append(r)
    accepted = {r["query_id"]: r["result"] for r in rows(Path(root) / f"kw_s{seed}.jsonl")}  # last line wins
    first_ok = sorted(q for q in query_ids if attempts.get(q) and attempts[q][0]["valid"])
    final_ok = sorted(q for q in query_ids if phased_qa.keywords_valid(accepted.get(q)))
    n = len(query_ids)
    by_attempt = {}
    for q in final_ok:
        k = next(r["attempt"] for r in attempts.get(q, []) if r["valid"]) if attempts.get(q) else None
        by_attempt[str(k)] = by_attempt.get(str(k), 0) + 1
    return {"questions": n, "missing": sorted(set(query_ids) - set(accepted)),
            "usable_at_attempt_0": len(first_ok), "usable_at_attempt_0_pct": round(100 * len(first_ok) / n, 2),
            "usable_after_retries": len(final_ok), "usable_after_retries_pct": round(100 * len(final_ok) / n, 2),
            "accepted_at_attempt": by_attempt, "unusable": sorted(set(query_ids) - set(final_ok)),
            "calls": sum(len(v) for v in attempts.values()), "first_attempt_usable_ids": first_ok}


def gate(root, seeds, questions):
    with open(questions, newline="", encoding="utf-8") as f:
        query_ids = [r["query_id"] for r in csv.DictReader(f)]
    seeds_out = {str(s): seed_report(root, s, query_ids) for s in seeds}
    passed = {s: not r["missing"] and r["usable_after_retries_pct"] >= THRESHOLD for s, r in seeds_out.items()}
    return {"threshold_pct": THRESHOLD, "retries": phased_qa.KW_RETRIES, "seeds": seeds_out, "gate": passed}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--questions", type=Path, required=True)
    p.add_argument("--seeds", type=int, nargs="+", default=[101, 202, 303])
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)
    result = gate(args.root, args.seeds, args.questions)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({s: {k: v for k, v in r.items() if k not in ("first_attempt_usable_ids", "unusable")}
                      for s, r in result["seeds"].items()} | {"gate": result["gate"]}, indent=2))
    return 0 if all(result["gate"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
