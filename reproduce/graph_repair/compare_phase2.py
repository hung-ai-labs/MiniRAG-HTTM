"""Phase 2a (PHASE2_REGISTRATION.md): regression checks and dev-180 comparison against frozen C0. Offline."""
import json
import os
import statistics
import sys
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reproduce" / "screening"))
from screen_variant import dev_rows, gold_map  # noqa: E402

FROZEN = ROOT / "logs" / "c_ablation" / "graph"
P2 = ROOT / "logs" / "graph_repair" / "phase2"


def records(path):
    rows = [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]
    return {r.get("query") or r.get("question"): r for r in rows}


def mcnemar(b, c):
    n, k = b + c, min(b, c)
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


gold = gold_map()
questions = [r["Question"] for r in dev_rows() if r["Question"] in gold]
types = {r["Question"]: r.get("Type", "Single") for r in dev_rows()}


def full(recs):
    return {q: all(g in recs[q].get("chunk_ids", []) for g in gold[q]) for q in questions}


def micro(recs):
    hit = sum(len(set(gold[q]) & set(recs[q].get("chunk_ids", []))) for q in questions)
    return 100 * hit / sum(len(gold[q]) for q in questions)


c0 = records(FROZEN / "C0" / "C0_records.jsonl")
c0_full = full(c0)
out = {}
for name, frozen in (("c0_reg", "C0"), ("c2_reg", "C2")):
    path = P2 / name / f"{frozen}_records.jsonl"
    if path.exists():
        a, b = records(FROZEN / frozen / f"{frozen}_records.jsonl"), records(path)
        same = sum(a[q]["chunk_ids"] == b[q]["chunk_ids"] for q in questions)
        print(f"regression {name} vs frozen {frozen}: {same}/{len(questions)} identical chunk_ids")
        out[f"regression_{name}"] = same

arms = [("C0 (frozen)", FROZEN / "C0" / "C0_records.jsonl"), ("C1 (frozen)", FROZEN / "C1" / "C1_records.jsonl"), ("C2 (frozen)", FROZEN / "C2" / "C2_records.jsonl"),
        ("G-B0", P2 / "g_b0" / "C1_records.jsonl"),
        ("G-A", P2 / "g_a" / "C2_records.jsonl"), ("G-B", P2 / "g_b" / "C2_records.jsonl"),
        ("G-AB", P2 / "g_ab" / "C2_records.jsonl")]
print(f"\n{'arm':12} {'full':>8} {'Single':>7} {'Multi':>6} {'micro':>6} {'up/down vs C0':>14} {'p':>9} {'med tok':>8}")
for arm, path in arms:
    if not path.exists():
        continue
    recs = records(path)
    f = full(recs)
    up = sum(f[q] and not c0_full[q] for q in questions)
    down = sum(c0_full[q] and not f[q] for q in questions)
    single = sum(f[q] for q in questions if types[q] == "Single")
    multi = sum(f[q] for q in questions if types[q] == "Multi")
    tok = statistics.median(recs[q].get("sources_tok", 0) for q in questions)
    p = mcnemar(up, down)
    print(f"{arm:12} {sum(f.values()):>4}/{len(questions)} {single:>7} {multi:>6} {micro(recs):>6.1f} "
          f"{up:>6}/{down:<7} {p:>9.3g} {tok:>8}")
    out[arm] = {"full": sum(f.values()), "single": single, "multi": multi, "micro": round(micro(recs), 2),
                "up": up, "down": down, "p": p, "median_sources_tok": tok}
(P2 / "phase2a_summary.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
