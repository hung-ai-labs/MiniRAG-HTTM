"""Analyse the LiHua ablation v2 exactly as registered (docs/research/lihua_world/LIHUA_ABLATION_V2.md, 860f20f).

Offline, no model calls. Per generation seed and per contrast, reuses compare_mhr.compare (majority-of-3
accurate vs not, exact McNemar, paired bootstrap 10,000 draws seed 13, -3 point margin) and adds:

  L1   B2 vs C0 -- primary; confirmed when all seeds point the same way with p < 0.05 each
  L2-6 component contributions as full minus ablated -- B2-VEC (BM25), B2-BM25 (vector), B2-B1 (graph in
       Sources), B2-NOENT (Entities), NOENT-NOGRAPH (remaining graph) -- one Holm family per seed; a component
       "contributes" when all seeds agree in sign with Holm-adjusted p < 0.05 in each
  L7   Null error, B2 vs C0 (secondary)
  Evidence Recall of the Sources actually put in context (descriptive), stage D direction check, per-arm
  tables by question type, judge sd and generation sd kept apart.

Refuses to analyse a seed whose judging session is not "completed" (use --allow-incomplete only for smoke).

    python reproduce/research/analyze_lihua_ablation.py --root runs/lihua_world/ablation_v2 \
        --out results/lihua_world/ablation_v2
"""

import argparse
import csv
import importlib.util
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("compare_mhr", Path(__file__).with_name("compare_mhr.py"))
compare_mhr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(compare_mhr)

ARMS = ("L-C0", "L-B2", "L-VEC", "L-BM25", "L-B1", "L-NOENT", "L-NOGRAPH")
# id: (reference a, compared b, question) -- every difference is b - a.
CONTRASTS = {
    "L1": ("L-C0", "L-B2", "overall effect of B2"),
    "L2": ("L-VEC", "L-B2", "BM25 channel"),
    "L3": ("L-BM25", "L-B2", "vector channel"),
    "L4": ("L-B1", "L-B2", "graph ranking in Sources (B2 drops it)"),
    "L5": ("L-NOENT", "L-B2", "Entities table"),
    "L6": ("L-NOGRAPH", "L-NOENT", "remaining graph at query time (gate + parser)"),
}
FAMILY = ("L2", "L3", "L4", "L5", "L6")
STAGE_D = {"L4": "+6.59 (H3)", "L2": "+8.12 (H2)"}  # historical direction only, never pooled
ALPHA = 0.05


def holm(pvalues):
    """Holm step-down adjusted p-values for a dict name -> p."""
    order = sorted(pvalues, key=pvalues.get)
    m, adjusted, running = len(order), {}, 0.0
    for i, name in enumerate(order):
        running = max(running, min(1.0, (m - i) * pvalues[name]))
        adjusted[name] = running
    return adjusted


def majority_rates(rows, types=None):
    """Recomputed from per_question.csv, not copied from summary.json."""
    picked = [r for r in rows.values() if not types or r["Type"] in types]
    n = len(picked)
    return {k: round(100 * sum(r["majority"] == k for r in picked) / n, 2) if n else None
            for k in ("accurate", "error", "neither", "no_majority")} | {"n": n}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_run(root, arm, seed):
    rows, summary = compare_mhr.load(root / f"{arm}_s{seed}" / "judge")
    return rows, summary


def last_records(path):
    out = {}
    if Path(path).exists():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[r["query"]] = r
    return out


def evidence_recall(root, arm, seed, questions, gold):
    """Gold chunks found among the Sources chunks MiniRAG put into the context."""
    log = last_records(root / f"{arm}_s{seed}" / "context.jsonl")
    micro_hit = micro_all = 0
    per_q, full = [], 0
    for q, qid in questions.items():
        g = gold.get(qid)
        if not g:
            continue
        got = set((log.get(q) or {}).get("chunk_ids") or [])  # early exit -> no Sources -> nothing retrieved
        hit = len(g & got)
        micro_hit, micro_all = micro_hit + hit, micro_all + len(g)
        per_q.append(hit / len(g))
        full += hit == len(g)
    n = len(per_q)
    return {"n_questions": n, "micro": round(100 * micro_hit / micro_all, 2) if micro_all else None,
            "macro": round(100 * statistics.mean(per_q), 2) if per_q else None,
            "full_evidence": round(100 * full / n, 2) if n else None}


def analyse(root, seeds, questions_csv, gold_jsonl, allow_incomplete=False):
    with open(questions_csv, newline="", encoding="utf-8") as f:
        questions = {r["Question"]: r["query_id"] for r in csv.DictReader(f)}
    gold, no_gold = {}, []
    for line in Path(gold_jsonl).read_text(encoding="utf-8").splitlines():
        g = json.loads(line)
        if g["evidence"] is None:
            continue  # Null: no evidence by design
        chunks = {c for e in g["evidence"] for c in e["chunk_ids"]}
        if chunks:
            gold[g["query_id"]] = chunks
        else:
            no_gold.append(g["query_id"])

    sessions = {}
    for s in seeds:
        path = root / f"judge_s{s}_SESSION.json"
        sessions[s] = read_json(path) if path.exists() else {"state": "missing"}
        if sessions[s]["state"] != "completed" and not allow_incomplete:
            raise SystemExit(f"seed {s}: judging session is {sessions[s]['state']!r}, not completed")

    runs = {(a, s): load_run(root, a, s) for a in ARMS for s in seeds}
    result = {"registration_commit": "860f20f", "seeds": list(seeds), "sessions": {
        s: {k: v.get(k) for k in ("state", "session_id", "started_at", "finished_at", "judge_model", "response_models",
                                  "archived_partial_unread")} for s, v in sessions.items()},
        "questions_without_mapped_evidence": no_gold, "arms": {}, "contrasts": {}, "decisions": {}}

    for a in ARMS:
        per_seed = {}
        for s in seeds:
            rows, summary = runs[(a, s)]
            groups = (summary or {}).get("groups", {})
            per_seed[s] = {"majority": majority_rates(rows),
                           "pass_mean_sd": groups.get("all", {}).get("pass_mean_sd"),  # judge noise, from judge_run
                           "by_type_majority": {t: majority_rates(rows, [t])
                                                for t in sorted({r["Type"] for r in rows.values()})},
                           "early_exit": groups.get("all", {}).get("early_exit"),
                           "abstained": (summary or {}).get("abstained"),
                           "evidence_recall": evidence_recall(root, a, s, questions, gold)}
        accs = [per_seed[s]["majority"]["accurate"] for s in seeds if per_seed[s]["majority"]]
        result["arms"][a] = {"per_seed": per_seed, "generation_mean_sd_accurate": {
            "mean": round(statistics.mean(accs), 2) if accs else None,
            "sd": round(statistics.stdev(accs), 2) if len(accs) > 1 else None}}

    for cid, (ref, cmp, what) in CONTRASTS.items():
        result["contrasts"][cid] = {"a": ref, "b": cmp, "question": what, "per_seed": {
            s: compare_mhr.compare(runs[(ref, s)][0], runs[(cmp, s)][0]) for s in seeds}}
    result["contrasts"]["L7"] = {"a": "L-C0", "b": "L-B2", "question": "Null error", "per_seed": {
        s: compare_mhr.compare(runs[("L-C0", s)][0], runs[("L-B2", s)][0], ["Null"]) for s in seeds}}

    for s in seeds:  # Holm within each seed over the component family
        adj = holm({c: result["contrasts"][c]["per_seed"][s]["primary_accurate"]["p"] for c in FAMILY})
        for c in FAMILY:
            result["contrasts"][c]["per_seed"][s]["primary_accurate"]["p_holm"] = adj[c]

    def signs(cid):
        return {(1 if x["primary_accurate"]["diff"] > 0 else -1 if x["primary_accurate"]["diff"] < 0 else 0)
                for x in result["contrasts"][cid]["per_seed"].values()}

    l1 = result["contrasts"]["L1"]["per_seed"].values()
    same = signs("L1")
    result["decisions"]["L1"] = {
        "confirmed": len(same) == 1 and 0 not in same and all(x["primary_accurate"]["p"] < ALPHA for x in l1),
        "direction": "B2 better" if same == {1} else "B2 worse" if same == {-1} else "mixed"}
    for cid in FAMILY:
        per = result["contrasts"][cid]["per_seed"].values()
        sg = signs(cid)
        result["decisions"][cid] = {
            "contributes": len(sg) == 1 and 0 not in sg and all(x["primary_accurate"]["p_holm"] < ALPHA for x in per),
            "direction": "positive" if sg == {1} else "negative" if sg == {-1} else "mixed",
            "noninferior_at_-3_all_seeds": all(x["primary_accurate"]["noninferior_at_-3"] for x in per)}
        if cid in STAGE_D:
            result["decisions"][cid]["stage_d_direction_replicated"] = sg == {1}
            result["decisions"][cid]["stage_d"] = STAGE_D[cid]
    l7 = result["contrasts"]["L7"]["per_seed"].values()
    result["decisions"]["L7"] = {"more_errors_significant_seeds": sum(
        1 for x in l7 if x["secondary_error"]["more_errors"] > x["secondary_error"]["fewer_errors"]
        and x["secondary_error"]["p"] < ALPHA), "seeds": len(seeds)}
    return result


def report(result):
    lines = ["# LiHua-World ablation v2 — kết quả (tự sinh bởi analyze_lihua_ablation.py)", "",
             "| Nhánh | " + " | ".join(f"acc s{s}" for s in result["seeds"]) + " | TB ± sd sinh |",
             "|---|" + "---:|" * (len(result["seeds"]) + 1)]
    for a, v in result["arms"].items():
        cells = [f"{v['per_seed'][s]['majority']['accurate']:.2f}" for s in result["seeds"]]
        g = v["generation_mean_sd_accurate"]
        lines.append(f"| {a} | " + " | ".join(cells) + f" | {g['mean']} ± {g['sd']} |")
    lines += ["", "| Phép so | b − a | " + " | ".join(f"s{s}: Δ (lên/xuống, p, p Holm)" for s in result["seeds"])
              + " | Kết luận |", "|---|---|" + "---|" * (len(result["seeds"]) + 1)]
    for cid, c in result["contrasts"].items():
        if cid == "L7":
            continue
        cells = []
        for s in result["seeds"]:
            x = c["per_seed"][s]["primary_accurate"]
            ph = f", {x['p_holm']:.3g}" if "p_holm" in x else ""
            cells.append(f"{x['diff']:+.2f} ({x['up']}/{x['down']}, {x['p']:.3g}{ph})")
        lines.append(f"| {cid} | {c['b']} − {c['a']} | " + " | ".join(cells) + f" | {json.dumps(result['decisions'][cid])} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--root", type=Path, default=ROOT / "runs/lihua_world/ablation_v2")
    p.add_argument("--questions", type=Path, default=ROOT / "dataset/LiHua-World/splits/nondev435.csv")
    p.add_argument("--gold", type=Path, default=ROOT / "dataset/LiHua-World/splits/nondev435_gold_chunks.jsonl")
    p.add_argument("--seeds", type=int, nargs="+", default=[101, 202, 303])
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--allow-incomplete", action="store_true", help="smoke only")
    args = p.parse_args(argv)
    result = analyse(args.root, args.seeds, args.questions, args.gold, args.allow_incomplete)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "ANALYSIS.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.out / "ANALYSIS.md").write_text(report(result), encoding="utf-8")
    print(report(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
