"""Chi tiết nhóm Null của lượt canary CE1 — chuyển dịch từng câu so với mốc B2, cộng ba chunk gây nhầm đã biết.

    .venv/bin/python reproduce/rerank/canary_null_detail.py [canary|dev] [ce1|ce1_lite] | tee logs/rerank/<tầng>_null_detail.txt

Chỉ đọc log đã có. Không gọi LLM, không sinh, không chấm.
Mốc B2 dựng đúng cách screen_variant dựng: answers.jsonl của B2 khi có, ngược lại V3 đông lạnh
(context B2 trùng V3 thì câu trả lời của B2 CHÍNH LÀ câu trả lời V3).
"""
import collections, csv, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "reproduce", "retrieval_audit"))
import diagnose as d  # noqa: E402

S = os.path.join(ROOT, "logs", "screening")
MISLEAD = {"L002": "20260112_10:00", "L055": "20261113_13:00", "L052": "20260214_16:00"}


def last(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        out.setdefault(r["question"], {}).update(r)
    return out


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "canary"
    var = sys.argv[2] if len(sys.argv) > 2 else "ce1"
    src = (os.path.join(ROOT, "reproduce", "screening", "canary100.csv") if stage == "canary"
           else os.path.join(ROOT, "logs", "devset.csv"))
    rows = list(csv.DictReader(open(src, encoding="utf-8")))
    nul = [r["Question"] for r in rows if r["Type"] == "Null"]
    v3 = last(os.path.join(S, "frozen", "v3.jsonl"))
    b2 = last(os.path.join(S, "b2", "answers.jsonl"))
    ce = last(os.path.join(S, var, "answers.jsonl"))
    rep = json.load(open(os.path.join(S, var, f"{stage}_report.json"), encoding="utf-8"))
    ctx = rep["contexts"]

    def base_verdict(q):
        return b2[q]["verdict"] if q in b2 and b2[q].get("verdict") else v3[q]["verdict"]

    def var_verdict(q):
        return ce[q]["verdict"] if q in ce and ce[q].get("verdict") else base_verdict(q)

    print(f"NULL — {len(nul)} câu, tầng {stage} · mốc B2 → {var}\n")
    tr = collections.Counter()
    for q in nul:
        a, b = base_verdict(q), var_verdict(q)
        tr[(a, b)] += 1
        mark = "  " if a == b else ("↑" if b == "accurate" else "↓" if a == "accurate" else "~")
        print(f"   {mark} {a:8s} → {b:8s} · đổi context {'có' if ctx.get(q, {}).get('changed') else '—'} | {q[:66]}")
    print("\n   Chuyển dịch:", " · ".join(f"{a}→{b}: {n}" for (a, b), n in sorted(tr.items())))
    acc_b = sum(base_verdict(q) == "accurate" for q in nul)
    acc_v = sum(var_verdict(q) == "accurate" for q in nul)
    err_b = sum(base_verdict(q) == "error" for q in nul)
    err_v = sum(var_verdict(q) == "error" for q in nul)
    nei_b = sum(base_verdict(q) == "neither" for q in nul)
    nei_v = sum(var_verdict(q) == "neither" for q in nul)
    print(f"   acc {acc_b}/{len(nul)} → {acc_v}/{len(nul)} · err {err_b} → {err_v} · neither {nei_b} → {nei_v}")

    # vật liệu đầu vào của nhóm Null
    ctxf = {"ce1": "ce1_on_dev_ctx.jsonl", "ce1_lite": "ce1_lite_on_dev_ctx.jsonl"}[var]
    on = {r["question"]: r for r in (json.loads(l) for l in
                                     open(os.path.join(ROOT, "logs", "retrieval_audit", ctxf),
                                          encoding="utf-8")) if not r.get("none")}
    b2c = {r["question"]: r for r in (json.loads(l) for l in
                                      open(os.path.join(ROOT, "logs", "retrieval_audit", "vector_bm25_dev_ctx.jsonl"),
                                           encoding="utf-8")) if not r.get("none")}
    sh = [q for q in nul if q in on and q in b2c]
    import statistics as st
    eb = [len({d.ctime(c) or c for c in b2c[q]["chunk_ids"]}) for q in sh]
    ea = [len({d.ctime(c) or c for c in on[q]["chunk_ids"]}) for q in sh]
    print(f"\n   Vật liệu đầu vào ({len(sh)} câu Null có context cả hai bên):")
    print(f"      sự kiện phân biệt trong Sources, trung vị {st.median(eb)} → {st.median(ea)}")
    print(f"      số chunk trung vị {st.median([len(b2c[q]['chunk_ids']) for q in sh])} → "
          f"{st.median([len(on[q]['chunk_ids']) for q in sh])}")
    print(f"      token Sources trung vị {st.median([sum(d.tok(c) for c in b2c[q]['chunk_ids']) for q in sh])} → "
          f"{st.median([sum(d.tok(c) for c in on[q]['chunk_ids']) for q in sh])}")


if __name__ == "__main__":
    main()
