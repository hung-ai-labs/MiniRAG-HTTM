"""Offline paired analysis of the registered CRN arm; preview is never read."""
import argparse
import json
from math import comb
import statistics

from run import OUT, QUESTIONS, SEEDS, rows, sha
from share_judge import MODELS, output_dir

LABELS = ("accurate", "error", "neither")


def exact_mcnemar(b, c):
    n = b + c
    return min(1.0, 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2**n) if n else 1.0


def rates(labels):
    n = len(labels)
    return {"n": n} | {k: round(100 * labels.count(k) / n, 2) if n else None
                       for k in (*LABELS, "no_majority")}


def summary(rowset):
    majority = rates([r["majority"] for r in rowset])
    passes = [rates([r[f"pass{p}"] for r in rowset if r[f"pass{p}"] != "abstain"])
              for p in (1, 2, 3)]
    mean_sd = {}
    for label in LABELS:
        values = [p[label] for p in passes if p[label] is not None]
        mean_sd[label] = {"mean": round(statistics.mean(values), 2) if values else None,
                          "sd": round(statistics.stdev(values), 2) if len(values) > 1 else 0.0}
    return {"majority": majority, "passes": passes, "pass_mean_sd": mean_sd}


def paired(c0, other, label):
    if set(c0) != set(other):
        raise ValueError("arm question IDs differ")
    b = sum(c0[q]["majority"] != label and other[q]["majority"] == label for q in c0)
    c = sum(c0[q]["majority"] == label and other[q]["majority"] != label for q in c0)
    return {"b_up": b, "c_down": c, "net": b - c, "p_exact": exact_mcnemar(b, c)}


def comparison(c0, other, groups, arm):
    result = {}
    for name, ids in groups.items():
        left, right = ({q: run[q] for q in ids} for run in (c0, other))
        transitions = {}
        for q in ids:
            key = f"{left[q]['majority']} -> {right[q]['majority']}"
            transitions[key] = transitions.get(key, 0) + 1
        result[name] = {"L-C0": summary(list(left.values())), arm: summary(list(right.values())),
                        "acc": paired(left, right, "accurate"), "err": paired(left, right, "error"),
                        "transitions": dict(sorted(transitions.items()))}
    return result


def analyze_rows(mapping, verdicts, questions, changed_by_seed, *, raw_mapping=None, raw_verdicts=None):
    by_run = {}
    for items, votes in ((mapping, verdicts), (raw_mapping or [], raw_verdicts or {})):
        for item in items:
            if items is raw_mapping and item["arm"] != "L-T":
                continue
            uid, qid = item["unique_id"], item["query_id"]
            if uid not in votes:
                raise ValueError(f"missing unique verdict {uid}")
            key = (item["model"], item["seed"], item["arm"])
            run = by_run.setdefault(key, {})
            if qid in run and run[qid] != votes[uid]:
                raise ValueError(f"conflicting verdict: {key} {qid}")
            run[qid] = votes[uid]
    models = sorted({model for model, _, _ in by_run})
    result = {}
    for model in models:
        result[model] = {}
        for seed in SEEDS:
            c0 = by_run[(model, seed, "L-C0")]
            tc = by_run[(model, seed, "L-TC")]
            if len(c0) != 435 or set(c0) != set(questions) or set(tc) != set(c0):
                raise ValueError(f"incomplete primary arms: {model} s{seed}")
            changed = set(changed_by_seed[(model, seed)])
            if not changed <= set(questions):
                raise ValueError("gate contains unknown question ID")
            unchanged = set(questions) - changed
            if any(c0[q] != tc[q] for q in unchanged):
                raise AssertionError(f"CRN unchanged verdicts differ: {model} s{seed}")
            groups = {"all": set(questions), "changed": changed, "unchanged": unchanged}
            groups.update({t: {q for q, kind in questions.items() if kind == t}
                           for t in ("Single", "Multi", "Null")})
            result[model][str(seed)] = {"primary": comparison(c0, tc, groups, "L-TC")}
            raw = by_run.get((model, seed, "L-T"))
            if raw is not None:
                if set(raw) != set(c0):
                    raise ValueError(f"incomplete raw L-T: {model} s{seed}")
                result[model][str(seed)]["secondary"] = comparison(c0, raw, groups, "L-T")
        tests = [result[model][str(s)]["primary"]["all"] for s in SEEDS]
        acc = all(t["acc"]["net"] > 0 and t["acc"]["p_exact"] < .05 for t in tests)
        err = all(t["err"]["net"] < 0 and t["err"]["p_exact"] < .05 for t in tests)
        result[model]["registered_verdict"] = {"acc_increase_all_3_p_lt_0_05": acc,
                                               "err_decrease_all_3_p_lt_0_05": err,
                                               "acc_up_and_err_down": acc and err}
    return result


def load_judged(model, *, include_raw_lt=False):
    shared = output_dir(model, include_raw_lt=include_raw_lt)
    mapping = json.loads((shared / "mapping.json").read_text(encoding="utf-8"))
    if mapping.get("model") != model or mapping.get("preview") or mapping.get("include_raw_lt") != include_raw_lt:
        raise ValueError("wrong judge mapping variant")
    for name, expected_sha in mapping["answer_sha256"].items():
        _, run = name.split("/", 1)
        if sha(OUT / model / run / "answers.csv") != expected_sha:
            raise ValueError(f"answer changed after judge preparation: {name}")
    judged = shared / "judge"
    manifest = json.loads((judged / "manifest.json").read_text(encoding="utf-8"))
    if (manifest["judge_model"], manifest["passes"], manifest["seed"], manifest["invalid_tries"]) != (
            "gemini-3.5-flash-lite", 3, 13, 3):
        raise ValueError("judge protocol differs")
    if manifest["questions_sha256"] != sha(shared / "questions.csv") or \
            manifest["answers_sha256"] != sha(shared / "answers.csv"):
        raise ValueError("judge inputs differ")
    if json.loads((judged / "summary.json").read_text(encoding="utf-8"))["status"] != "completed":
        raise ValueError("judge incomplete")
    verdicts = {r["query_id"]: r for r in rows(judged / "per_question.csv")}
    if len(verdicts) != mapping["n_unique"]:
        raise ValueError("unique verdict count differs")
    return mapping, verdicts


def markdown(model, data, manifest):
    lines = [f"# Temporal accuracy — {model}", "", "Phân tích chính: L-TC so với L-C0; 435 câu mỗi seed.",
             f"Judge chia sẻ: {manifest['calls_with_sharing']}/{manifest['calls_without_sharing']} lượt; "
             f"tiết kiệm {manifest['calls_saved']}.", "",
             "| Seed | C0 acc/err/neither | TC acc/err/neither | acc b/c/p | err b/c/p |",
             "|---|---|---|---|---|"]
    for seed in SEEDS:
        cell = data[str(seed)]["primary"]["all"]
        def fmt(arm):
            return "/".join(f"{cell[arm]['majority'][k]} "
                            f"({cell[arm]['pass_mean_sd'][k]['mean']}±{cell[arm]['pass_mean_sd'][k]['sd']})"
                            for k in LABELS)
        a, e = cell["acc"], cell["err"]
        lines.append(f"| {seed} | {fmt('L-C0')} | {fmt('L-TC')} | "
                     f"{a['b_up']}/{a['c_down']}/{a['p_exact']:.4g} | "
                     f"{e['b_up']}/{e['c_down']}/{e['p_exact']:.4g} |")
    if all("secondary" in data[str(seed)] for seed in SEEDS):
        lines += ["", "## Phân tích phụ: L-T thô so với L-C0", "",
                  "| Seed | C0 acc/err/neither | L-T acc/err/neither | acc b/c/p | err b/c/p |",
                  "|---|---|---|---|---|"]
        for seed in SEEDS:
            cell = data[str(seed)]["secondary"]["all"]
            def fmt(arm):
                return "/".join(str(cell[arm]["majority"][k]) for k in LABELS)
            a, e = cell["acc"], cell["err"]
            lines.append(f"| {seed} | {fmt('L-C0')} | {fmt('L-T')} | "
                         f"{a['b_up']}/{a['c_down']}/{a['p_exact']:.4g} | "
                         f"{e['b_up']}/{e['c_down']}/{e['p_exact']:.4g} |")
    lines += ["", "## Phân nhóm và McNemar", "",
              "| Seed | Phép so | Nhóm | n | acc b/c/p | err b/c/p |",
              "|---|---|---|---:|---|---|"]
    for seed in SEEDS:
        for variant in ("primary", "secondary"):
            if variant not in data[str(seed)]:
                continue
            for group in ("changed", "unchanged", "Single", "Multi", "Null"):
                cell = data[str(seed)][variant][group]
                a, e = cell["acc"], cell["err"]
                lines.append(f"| {seed} | {variant} | {group} | {cell['L-C0']['majority']['n']} | "
                             f"{a['b_up']}/{a['c_down']}/{a['p_exact']:.4g} | "
                             f"{e['b_up']}/{e['c_down']}/{e['p_exact']:.4g} |")
    lines += ["", f"Luật ba seed: {data['registered_verdict']}",
              "Chi tiết tỷ lệ, từng pass và ma trận chuyển nhãn: `ANALYSIS.json`.", ""]
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", choices=(*MODELS, "all"), default="all")
    a = p.parse_args()
    questions = {r["query_id"]: r["Type"] for r in rows(QUESTIONS)}
    reports = {}
    for model in MODELS if a.model == "all" else (a.model,):
        shared = output_dir(model)
        if not (shared / "judge/summary.json").exists():
            if a.model == "all":
                continue
            raise FileNotFoundError(shared / "judge/summary.json")
        manifest, verdicts = load_judged(model)
        raw_manifest = raw_verdicts = None
        if (output_dir(model, include_raw_lt=True) / "judge/summary.json").exists():
            raw_manifest, raw_verdicts = load_judged(model, include_raw_lt=True)
        changed = {}
        for seed in SEEDS:
            gate = json.loads((OUT / model / f"gate_s{seed}.json").read_text(encoding="utf-8"))
            if gate.get("baseline_identical") != 435:
                raise ValueError("baseline identity gate failed")
            changed[(model, seed)] = gate["context_changed"]
        report = analyze_rows(manifest["mapping"], verdicts, questions, changed,
                              raw_mapping=raw_manifest["mapping"] if raw_manifest else None,
                              raw_verdicts=raw_verdicts)
        data = report[model]
        reports[model] = data
        folder = OUT / model
        (folder / "ANALYSIS.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (folder / "ANALYSIS.md").write_text(markdown(model, data, manifest), encoding="utf-8")
        print(folder / "ANALYSIS.md")
    if not reports:
        raise ValueError("no completed main judge; preview is excluded")
    if len(reports) == len(MODELS):
        (OUT / "ANALYSIS.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (OUT / "ANALYSIS.md").write_text("\n\n".join((OUT / m / "ANALYSIS.md").read_text(encoding="utf-8")
                                                         for m in MODELS), encoding="utf-8")


if __name__ == "__main__":
    main()
