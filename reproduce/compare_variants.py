"""So một biến thể với baseline: bảng 3 cột, acc/(acc+err), McNemar ghép từng câu,
tách Single/Multi/Null, tách dev 200 / 437 câu ngoài dev (quy tắc cắt được nhìn thử
trên dev nên tập ngoài dev là phép thử sạch), kèm Efficiency từ log context.

    python reproduce/compare_variants.py --base logs/qwen637_fix_judged.csv \\
        --new logs/qwen637_v2_judged.csv --ctx logs/qwen637_v2_ctx.jsonl
"""
import argparse, collections, csv, json, math, os, statistics as st


def load(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    runs = collections.defaultdict(dict)
    types = {}
    for r in rows:
        runs[r["run"]][r["question"]] = r["verdict"]
        types[r["question"]] = r["type"]
    votes = collections.defaultdict(list)
    for r in rows:
        votes[r["question"]].append(r["verdict"])
    major = {q: collections.Counter(v).most_common(1)[0][0] for q, v in votes.items()}
    fails = sum(1 for r in rows if "fail" in r["verdict"].lower())
    return runs, types, major, fails, len(rows)


def table(runs, qs):
    acc, err, nei = [], [], []
    for d in runs.values():
        n = len(qs)
        acc.append(100 * sum(d.get(q) == "accurate" for q in qs) / n)
        err.append(100 * sum(d.get(q) == "error" for q in qs) / n)
        nei.append(100 * sum(d.get(q) == "neither" for q in qs) / n)
    a, e = st.mean(acc), st.mean(err)
    return a, (st.stdev(acc) if len(acc) > 1 else 0), e, st.mean(nei), 100 * a / (a + e)


def mcnemar(base, new, qs):
    b = sum(new[q] == "accurate" and base[q] != "accurate" for q in qs)
    c = sum(base[q] == "accurate" and new[q] != "accurate" for q in qs)
    n = b + c
    p = 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n)
    return b, c, p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--dev", default="./logs/devset.csv")
    ap.add_argument("--ctx", default="")
    ap.add_argument("--basectx", default="")
    ap.add_argument("--label", default="biến thể")
    a = ap.parse_args()

    br, types, bm, bf, bn = load(a.base)
    nr, _, nm, nf, nn = load(a.new)
    common = sorted(set(bm) & set(nm))
    dev = {r["Question"] for r in csv.DictReader(open(a.dev, encoding="utf-8"))}
    print(f"baseline: {a.base} ({bn} dòng, judge_failed={bf})")
    print(f"{a.label}: {a.new} ({nn} dòng, judge_failed={nf})")
    print(f"câu ghép được: {len(common)}")

    groups = [("TỔNG", common)] + [
        (t, [q for q in common if types[q] == t]) for t in ("Single", "Multi", "Null")
    ] + [("dev 200", [q for q in common if q in dev]),
         ("ngoài dev", [q for q in common if q not in dev])]

    print(f"\n{'nhóm':10s}{'n':>5s} │ {'baseline acc':>13s}{'err':>7s}{'nei':>7s}{'prec':>7s} │"
          f" {a.label[:12]+' acc':>13s}{'err':>7s}{'nei':>7s}{'prec':>7s} │ McNemar")
    for name, qs in groups:
        if not qs:
            continue
        ba, bs, be, bne, bp = table(br, qs)
        na, ns, ne, nne, np_ = table(nr, qs)
        b, c, p = mcnemar(bm, nm, qs)
        print(f"{name:10s}{len(qs):5d} │ {ba:6.2f}±{bs:4.2f}{be:7.2f}{bne:7.2f}{bp:7.2f} │"
              f" {na:6.2f}±{ns:4.2f}{ne:7.2f}{nne:7.2f}{np_:7.2f} │"
              f" {b:3d} lên/{c:3d} xuống net {b-c:+4d} p={p:.3f}")

    def ctx_stats(path):
        if not path or not os.path.exists(path):
            return None
        rs = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
        # QA resume sau lỗi sẽ ghi lại vài truy vấn -> giữ bản ghi cuối của mỗi câu
        rs = list({r["query"]: r for r in rs}.values())
        if not rs:
            return None
        tot = sorted(r["sources_tok"] + r["entities_tok"] for r in rs)
        return (len(rs), st.median(r["n_chunks"] for r in rs), st.median(tot),
                tot[int(0.9 * (len(tot) - 1))], tot[-1])

    for lab, path in (("baseline", a.basectx), (a.label, a.ctx)):
        s = ctx_stats(path)
        if s:
            print(f"\nEfficiency {lab}: {s[0]} truy vấn · chunk trung vị {s[1]} · "
                  f"context token trung vị {s[2]:.0f} · p90 {s[3]} · max {s[4]}")


if __name__ == "__main__":
    main()
