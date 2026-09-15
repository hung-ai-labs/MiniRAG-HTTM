"""Phân tích tầng D theo đăng ký trước (ROADMAP: "Tầng D — xác nhận bằng lặp lượt sinh", "Xử lý phán quyết và mẫu số" và chi
tiết triển khai chốt ngày 15/09/2026).

    .venv/bin/python reproduce/stage_d/analyze_stage_d.py             # một lần, sau khi đủ 8 lượt
    .venv/bin/python reproduce/stage_d/analyze_stage_d.py --selftest  # thử trên các file 637 câu cũ, không đọc dữ liệu tầng D

H1 = B1 vs V3 · H2 = B2 vs vector thuần · H3 = B2 vs B1. Mỗi nhánh 3 lượt sinh; mỗi lượt lấy lượt chấm run = 1.
"""
import argparse, collections, csv, json, math, os, statistics as st, sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "logs", "stage_d")
T_PTS = 4.18                         # ngưỡng bền với nhiễu sinh trên 435 câu (tập lặp V3 cố định)
TOK_REF, TOK_TOL = 3870, 0.05        # E5
SEED, NPERM = 20260914, 100_000
MAX_MISSING = 4                      # 1% của 435 câu
LABELS = ("accurate", "error", "neither")
TYPES = ("Single", "Multi", "Null")


def sd(name):
    return f"logs/stage_d/{name}"


ARMS = {
    "V3": [("logs/qwen637_v3_judged.csv", "1", None), ("logs/qwen637_v3_r2_judged.csv", "1", None),
           ("logs/qwen637_v3_r3_judged.csv", "1", None)],
    "VEC": [("logs/qwen637_vec_judged.csv", "1", None), (sd("vec_s202_judged.csv"), "1", sd("vec_s202_ctx.jsonl")),
            (sd("vec_s303_judged.csv"), "1", sd("vec_s303_ctx.jsonl"))],
    "B1": [(sd(f"b1_s{s}_judged.csv"), "1", sd(f"b1_s{s}_ctx.jsonl")) for s in (101, 202, 303)],
    "B2": [(sd(f"b2_s{s}_judged.csv"), "1", sd(f"b2_s{s}_ctx.jsonl")) for s in (101, 202, 303)],
}
HYPS = [("H1", "B1", "V3"), ("H2", "B2", "VEC"), ("H3", "B2", "B1")]


def questions():
    rows = list(csv.DictReader(open(os.path.join(ROOT, "reproduce", "stage_d", "nondev435.csv"), encoding="utf-8")))
    assert len(rows) == 435 and len({r["Question"] for r in rows}) == 435
    return [r["Question"] for r in rows], {r["Question"]: r["Type"] for r in rows}


def mcnemar_p(b, c):
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n)


def tokens_median(path):
    p = os.path.join(ROOT, path) if path else None
    if not p or not os.path.exists(p):
        return None
    last = {}
    for line in open(p, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            last[r["query"]] = r                     # resume ghi lại vài câu -> giữ bản ghi cuối
    return st.median(r["sources_tok"] + r["entities_tok"] for r in last.values()) if last else None


def load_run(path, run, qs):
    """Phiếu của một lượt chấm: mỗi dòng trùng văn bản nặng 1 / (số dòng của câu đó trong lượt)."""
    qset = set(qs)
    rows = [r for r in csv.DictReader(open(os.path.join(ROOT, path), encoding="utf-8"))
            if r["run"] == run and r["question"] in qset]
    lines = collections.Counter(r["question"] for r in rows)
    votes, failed = collections.defaultdict(collections.Counter), 0
    for r in rows:
        if r["verdict"] in LABELS:
            votes[r["question"]][r["verdict"]] += 1 / lines[r["question"]]
        else:
            failed += 1
    have = [q for q in qs if q in votes]
    rate = {l: 100 * sum(votes[q][l] for q in have) / len(have) for l in LABELS} if have else {}
    correct = {q: votes[q]["accurate"] > 0.5 for q in have}          # đa số tuyệt đối; chia đều -> không đúng
    return {"path": path, "rate": rate, "correct": correct, "missing": len(qs) - len(have), "failed": failed,
            "dup_questions": sum(1 for n in lines.values() if n > 1)}


def load_arm(name, qs, arms):
    runs = []
    for path, run, ctx in arms[name]:
        if not os.path.exists(os.path.join(ROOT, path)):
            return None, f"thiếu {path}"
        r = load_run(path, run, qs)
        r["tokens_median"] = tokens_median(ctx)
        runs.append(r)
    bad = [r["path"] for r in runs if r["failed"] or r["missing"] > MAX_MISSING]
    return runs, (f"KHÔNG HỢP LỆ: {bad}" if bad else "")


def perm_test(d):
    d = np.asarray(d, dtype=float)
    if len(d) == 0:
        return 0.0, 1.0
    obs = float(d.mean())
    rng = np.random.default_rng(SEED)                # khởi tạo lại cho mỗi phép thử
    hits, left = 0, NPERM
    while left:
        b = min(left, 10_000)
        signs = rng.choice((-1.0, 1.0), size=(b, len(d)))
        hits += int(np.sum(np.abs(signs @ d / len(d)) >= abs(obs) - 1e-12))
        left -= b
    return obs, (hits + 1) / (NPERM + 1)


def compare(A, B, qs, types):
    common = [q for q in qs if all(q in r["correct"] for r in A + B)]
    mA = {q: st.mean(r["correct"][q] for r in A) for q in common}
    mB = {q: st.mean(r["correct"][q] for r in B) for q in common}
    obs, p = perm_test([mA[q] - mB[q] for q in common])
    pairs = []
    for a, b in zip(A, B):
        up = sum(a["correct"][q] and not b["correct"][q] for q in common)
        dn = sum(b["correct"][q] and not a["correct"][q] for q in common)
        nq = [q for q in common if types[q] == "Null"]
        nu = sum(a["correct"][q] and not b["correct"][q] for q in nq)
        nd = sum(b["correct"][q] and not a["correct"][q] for q in nq)
        pairs.append({"variant": a["path"], "base": b["path"], "up": up, "down": dn, "net": up - dn,
                      "mcnemar_p": mcnemar_p(up, dn), "null_net": nu - nd})
    groups = {}
    for g in TYPES:
        gq = [q for q in common if types[q] == g]
        go, gp = perm_test([mA[q] - mB[q] for q in gq])
        groups[g] = {"n": len(gq), "diff_pts": 100 * go, "p": gp, "significant_drop": go < 0 and gp < 0.05}
    toks = [r["tokens_median"] for r in A]
    e5 = all(t is not None and abs(t / TOK_REF - 1) <= TOK_TOL for t in toks)
    derr = st.mean(r["rate"]["error"] for r in A) - st.mean(r["rate"]["error"] for r in B)
    null_net_mean = st.mean(x["null_net"] for x in pairs)
    return {"n": len(common), "diff_pts": 100 * obs, "p_perm": p, "pairs": pairs,
            "pairs_positive": sum(x["net"] > 0 for x in pairs), "groups": groups, "delta_err_pts": derr,
            "null_net_mean": null_net_mean, "tokens_median": toks,
            "E3": derr <= 1.0,
            "E4": not any(v["significant_drop"] for v in groups.values()) and null_net_mean >= -3,
            "E5": e5}


def holm(ps):
    order = sorted(ps, key=ps.get)
    adj, running, m = {}, 0.0, len(order)
    for i, h in enumerate(order):
        running = max(running, min(1.0, (m - i) * ps[h]))
        adj[h] = running
    return adj


def classify(c):
    if c["diff_pts"] <= 0:
        return "NEGATIVE"
    robust = (c["diff_pts"] >= T_PTS and c["pairs_positive"] == len(c["pairs"]) and c["p_holm"] < 0.05
              and c["E3"] and c["E4"] and c["E5"])
    return "ROBUST POSITIVE" if robust else "BORDERLINE"


def reading(cls):
    ok = lambda h: cls.get(h) == "ROBUST POSITIVE"  # noqa: E731
    out = []
    if "H1" in cls and "H2" in cls:
        out.append({(False, False): "H1 trượt + H2 trượt → bác hướng BM25.",
                    (False, True): "H1 trượt + H2 đạt → BM25 có ích nhưng có thể xung đột với xếp hạng đồ thị; đọc tiếp H3.",
                    (True, True): "H1 đạt + H2 đạt → BM25 có ích; H3 quyết định đồ thị còn thêm giá trị hay không.",
                    (True, False): "H1 đạt + H2 trượt → BM25 chỉ có ích khi đi cùng xếp hạng đồ thị; báo đúng như vậy."}
                   [(ok("H1"), ok("H2"))])
    if ok("H3"):
        out.append("B2 thắng B1 (H3 ROBUST POSITIVE theo chiều B2) → khi đã có trộn từ vựng + vector, xếp hạng suy từ đồ thị "
                   "hiện tại làm hại.")
    return out


def f2(x):
    return f"{x:+.2f}".replace(".", ",")


def arm_lines(name, runs):
    accs = [r["rate"]["accurate"] for r in runs]
    return [f"{name}: acc từng lượt " + " / ".join(f"{a:.2f}".replace(".", ",") for a in accs)
            + f" · trung bình {st.mean(accs):.2f} ± {st.stdev(accs):.2f}".replace(".", ",")
            + " · err từng lượt " + " / ".join(f"{r['rate']['error']:.2f}".replace(".", ",") for r in runs)
            + " · neither " + " / ".join(f"{r['rate']['neither']:.2f}".replace(".", ",") for r in runs)
            + f" · thiếu phiếu {[r['missing'] for r in runs]} · judge_failed {[r['failed'] for r in runs]}"]


def hyp_lines(h, a, b, c):
    L = [f"{h} = {a} vs {b} ({c['n']} câu ghép được): hiệu trung bình {f2(c['diff_pts'])} điểm "
         f"(so với T = 4,18: {f2(c['diff_pts'] - T_PTS)}) · hoán vị p = {c['p_perm']:.5f} · Holm p = {c['p_holm']:.5f}",
         "  cặp lượt: " + " · ".join(f"{x['up']} lên / {x['down']} xuống (McNemar p = {x['mcnemar_p']:.3g})" for x in c["pairs"])
         + f" · cùng chiều dương {c['pairs_positive']}/{len(c['pairs'])}",
         f"  E3 Δerr trung bình {f2(c['delta_err_pts'])} điểm → {'ĐẠT' if c['E3'] else 'TRƯỢT'}",
         "  E4 " + " · ".join(f"{g} {f2(v['diff_pts'])} (n = {v['n']}, p = {v['p']:.3f})" for g, v in c["groups"].items())
         + f" · Null net trung bình {f2(c['null_net_mean'])} câu → {'ĐẠT' if c['E4'] else 'TRƯỢT'}",
         f"  E5 token context trung vị từng lượt {c['tokens_median']} (±5% của 3.870) → {'ĐẠT' if c['E5'] else 'TRƯỢT'}",
         f"  Phân loại: {c['class']}"]
    return L


def selftest(qs, types):
    arms = {"V3": ARMS["V3"], "FIX": [("logs/qwen637_fix_judged.csv", r, None) for r in ("1", "2", "3")]}
    A, why_a = load_arm("V3", qs, arms)
    B, why_b = load_arm("FIX", qs, arms)
    assert A and B and not why_a and not why_b, (why_a, why_b)
    same = compare(A, A, qs, types)
    diff = compare(A, B, qs, types)
    again = compare(A, B, qs, types)
    ok = (same["diff_pts"] == 0 and same["p_perm"] == 1.0 and diff["diff_pts"] > 0
          and again["p_perm"] == diff["p_perm"] and A[0]["dup_questions"] == 1 and diff["n"] == 435)
    print(f"selftest: V3 vs chính nó {f2(same['diff_pts'])} điểm, p = {same['p_perm']:.3f} · V3 (lượt chấm 1) vs baseline "
          f"(3 lượt chấm của một lượt sinh) {f2(diff['diff_pts'])} điểm, p = {diff['p_perm']:.5f}, {diff['n']} câu · "
          f"p lặp lại giống hệt: {again['p_perm'] == diff['p_perm']} · câu trùng dòng ngoài dev: {A[0]['dup_questions']}")
    print("SELFTEST:", "ĐẠT" if ok else "TRƯỢT")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    qs, types = questions()
    if a.selftest:
        sys.exit(selftest(qs, types))

    arms, notes = {}, []
    for name in ARMS:
        runs, why = load_arm(name, qs, ARMS)
        if runs is None or why:
            notes.append(f"{name}: {why}")
        if runs is not None and not why:
            arms[name] = runs
    tested = [(h, x, y) for h, x, y in HYPS if x in arms and y in arms]
    comps = {h: compare(arms[x], arms[y], qs, types) for h, x, y in tested}
    adj = holm({h: c["p_perm"] for h, c in comps.items()}) if comps else {}
    for h, c in comps.items():
        c["p_holm"] = adj[h]
        c["class"] = classify(c)
    cls = {h: c["class"] for h, c in comps.items()}

    lines = ["TẦNG D — 435 câu ngoài dev × 3 lượt sinh × lượt chấm run = 1 (đăng ký trước; B2 mang nhãn lệch đăng ký từ tầng B)",
             f"Hoán vị đổi dấu {NPERM:,} lần, seed {SEED}, hai phía · Holm trên {len(comps)} giả thuyết · T = 4,18 điểm"]
    lines += [f"- {n}" for n in notes]
    for name, runs in arms.items():
        lines += arm_lines(name, runs)
    for h, x, y in tested:
        lines += hyp_lines(h, x, y, comps[h])
    untested = [h for h, _, _ in HYPS if h not in comps]
    if untested:
        lines.append(f"Chưa kiểm được: {untested} (thiếu nhánh hoặc nhánh không hợp lệ)")
    lines += ["Luật đọc:"] + [f"- {x}" for x in reading(cls)]
    os.makedirs(OUT, exist_ok=True)
    json.dump({"classes": cls, "comparisons": comps, "notes": notes,
               "arms": {n: [{k: v for k, v in r.items() if k != "correct"} for r in runs] for n, runs in arms.items()}},
              open(os.path.join(OUT, "stage_d_report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(os.path.join(OUT, "stage_d_report.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
