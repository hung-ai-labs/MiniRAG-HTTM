"""Giai đoạn 2–3 — mô phỏng offline các quy tắc chọn chunk trên dev 200 so với B2 đông lạnh.

    .venv/bin/python reproduce/retrieval_audit/simulate.py | tee logs/retrieval_audit/simulate.txt

Quy tắc (định nghĩa và tham số chốt trong logs/retrieval_audit/BASELINE_B2.md TRƯỚC khi chạy file này):
- b2       : A1 như code — lấy chunk theo thứ tự trộn, DỪNG ở chunk đầu tiên làm tràn 4.000 token.
- window   : chunk dài hơn W = 400 token được thay bằng một cửa sổ ≤ W token quanh dòng khớp từ khoá câu hỏi
             nhiều nhất (điểm dòng = tổng idf BM25 của từ câu hỏi xuất hiện trong dòng, bỏ STOP); dòng "Time:" giữ
             làm tiêu đề; sau đó A1 như b2. Không đọc Type/Evidence/đáp án.
Evidence và đáp án vàng chỉ dùng để ĐÁNH GIÁ.
"""
import collections, csv, json, math, os, re, statistics as st, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import diagnose as d  # noqa: E402
from minirag.bm25 import STOP, tokenize, BM25Index  # noqa: E402
from minirag.utils import encode_string_by_tiktoken  # noqa: E402

W = 400
BUDGET = d.BUDGET
IDX = BM25Index({cid: v["content"] for cid, v in d.CHUNKS.items()})


def ntok(s):
    return len(encode_string_by_tiktoken(s))


def window(cid, query):
    text = d.CHUNKS[cid]["content"]
    if d.tok(cid) <= W:
        return text
    lines = text.split("\n")
    head = [l for l in lines if l.startswith("Time:")]
    body = [(i, l) for i, l in enumerate(lines) if l.strip() and not l.startswith("Time:")]
    terms = {w for w in tokenize(query) if w not in STOP}
    score = [sum(IDX.idf.get(w, 0) for w in terms & set(tokenize(l))) for _, l in body]
    best = max(range(len(body)), key=lambda k: (score[k], -k))
    lo = hi = best
    budget = W - sum(ntok(h) + 1 for h in head)
    used = ntok(body[best][1]) + 1
    while True:
        opts = []
        if lo > 0:
            opts.append((score[lo - 1], 1, lo - 1))
        if hi < len(body) - 1:
            opts.append((score[hi + 1], 0, hi + 1))
        if not opts:
            break
        _, _, k = max(opts)
        t = ntok(body[k][1]) + 1
        if used + t > budget:
            break
        used += t
        lo, hi = min(lo, k), max(hi, k)
    return "\n".join(head + [l for _, l in body[lo:hi + 1]])


def select(rule, rec):
    q, ranked = rec["question"], rec["ranked_ids"]
    out, used = [], 0
    for c in ranked:
        text = window(c, q) if rule == "window" else d.CHUNKS[c]["content"]
        t = ntok(text)
        if used + t > BUDGET:
            break
        out.append((c, text))
        used += t
    return out, used


def norm(s):
    return " ".join(re.findall(r"[a-z0-9]+", s.lower()))


def mcnemar(b, c):
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n)


def main():
    recs = [json.loads(l) for l in open(d.CTX, encoding="utf-8")]
    recs = [r for r in recs if not r.get("none")]
    gold = d.gold_map()
    answers = {r["Question"]: r["Gold Answer"] for r in csv.DictReader(open(os.path.join(ROOT, "dataset", "LiHua-World", "qa", "query_set.csv"), encoding="utf-8"))}
    sel = {rule: {r["question"]: select(rule, r) for r in recs} for rule in ("b2", "window")}
    # b2 mô phỏng phải khớp chunk_ids đã log
    assert all([c for c, _ in sel["b2"][r["question"]][0]] == r["chunk_ids"] for r in recs)

    ev = [r for r in recs if r["question"] in gold]
    # tập "trích xuất được": đáp án vàng (chuẩn hoá) nằm nguyên văn trong một chunk đáp án
    extr = [r for r in ev if len(norm(answers[r["question"]])) >= 3 and
            any(norm(answers[r["question"]]) in norm(d.CHUNKS[g]["content"]) for g in gold[r["question"]])]

    def has_gold(rule, r):
        ids = {c for c, _ in sel[rule][r["question"]][0]}
        return all(g in ids for g in gold[r["question"]])

    def has_answer(rule, r):
        text = norm(" ".join(t for _, t in sel[rule][r["question"]][0]))
        return norm(answers[r["question"]]) in text

    print(f"Dev 200 · {len(recs)} câu có context · {len(ev)} câu có evidence · {len(extr)} câu có đáp án trích nguyên văn "
          f"được từ chunk đáp án · W = {W} · ngân sách {BUDGET}\n")
    for rule in ("window",):
        print(f"=== {rule} so với B2")
        for label, pop, fn in (("đủ chunk đáp án (180)", ev, has_gold), ("đáp án nguyên văn có trong Sources", extr, has_answer)):
            b0 = sum(fn("b2", r) for r in pop)
            b1 = sum(fn(rule, r) for r in pop)
            up = sum(fn(rule, r) and not fn("b2", r) for r in pop)
            dn = sum(fn("b2", r) and not fn(rule, r) for r in pop)
            print(f"   {label:36s} {b0}/{len(pop)} → {b1}/{len(pop)} · {up} lên / {dn} xuống · p = {mcnemar(up, dn):.3g}")
            for t in ("Single", "Multi"):
                pt = [r for r in pop if r["type"] == t]
                u = sum(fn(rule, r) and not fn("b2", r) for r in pt)
                dd = sum(fn("b2", r) and not fn(rule, r) for r in pt)
                print(f"      {t:6s} {sum(fn('b2', r) for r in pt)}/{len(pt)} → {sum(fn(rule, r) for r in pt)}/{len(pt)} · {u} lên / {dd} xuống")
        tb = [sel["b2"][r["question"]][1] for r in recs]
        tv = [sel[rule][r["question"]][1] for r in recs]
        nb = [len(sel["b2"][r["question"]][0]) for r in recs]
        nv = [len(sel[rule][r["question"]][0]) for r in recs]
        changed = sum(1 for r in recs if sel[rule][r["question"]][0] != sel["b2"][r["question"]][0])
        print(f"   token Sources trung vị {st.median(tb)} → {st.median(tv)} ({100 * (st.median(tv) / st.median(tb) - 1):+.1f}%) · "
              f"chunk trung vị {st.median(nb)} → {st.median(nv)} · context đổi {changed}/{len(recs)} câu")
        # Null — chỉ chẩn đoán
        nul = [r for r in recs if r["type"] == "Null"]
        cn = sum(1 for r in nul if sel[rule][r["question"]][0] != sel["b2"][r["question"]][0])
        ev_b = [len({d.ctime(c) or c for c, _ in sel["b2"][r["question"]][0]}) for r in nul]
        ev_v = [len({d.ctime(c) or c for c, _ in sel[rule][r["question"]][0]}) for r in nul]
        ev_ba = [len({d.ctime(c) or c for c, _ in sel["b2"][r["question"]][0]}) for r in recs]
        ev_va = [len({d.ctime(c) or c for c, _ in sel[rule][r["question"]][0]}) for r in recs]
        print(f"   Sự kiện phân biệt (Time khác nhau) trong Sources, trung vị — mọi câu: {st.median(ev_ba)} → {st.median(ev_va)} · "
              f"Null: {st.median(ev_b)} → {st.median(ev_v)}")
        print(f"   Null: context đổi {cn}/{len(nul)} câu · chunk trung vị {st.median(len(sel['b2'][r['question']][0]) for r in nul)} → "
              f"{st.median(len(sel[rule][r['question']][0]) for r in nul)}\n")
    json.dump({rule: {q: [c for c, _ in v[0]] for q, v in s.items()} for rule, s in sel.items()},
              open(os.path.join(ROOT, "logs", "retrieval_audit", "simulate_ids.json"), "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
