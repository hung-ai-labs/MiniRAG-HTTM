"""Probe 2: tín hiệu ngày có thêm gì khi đã có BM25; BM25 lợi bao nhiêu nhờ token ngày; đồ thị còn cần khi có BM25."""
import asyncio, collections, json, os, re, statistics as st, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, 'reproduce'); sys.path.insert(0, '.')
from probe_query_signals import BM25, query_days, day_of
from simulate_fusion import a1, rrf, mcnemar, TOPN
from gemini_common import build_rag, get_args
import minirag.operate as op

async def main():
    args = get_args("probe2"); rag = build_rag(args); wd = args.workingdir
    chunks = json.load(open(os.path.join(wd, "kv_store_text_chunks.json")))
    docs = json.load(open(os.path.join(wd, "kv_store_full_docs.json")))
    TOK = {c: len(op.encode_string_by_tiktoken(v["content"])) for c, v in chunks.items()}
    CDAY = {c: day_of(v["content"]) or day_of(docs.get(v["full_doc_id"], {}).get("content")) for c, v in chunks.items()}
    bm = BM25({c: v["content"] for c, v in chunks.items()})
    recs = [json.loads(l) for l in open("logs/diag_path2chunk.jsonl", encoding="utf-8") if l.strip()]
    ok = [r for r in recs if r.get("reached_kwd2chunk") and r["gold"]]
    R, tt = [], []
    for r in ok:
        q, gold = r["question"], r["gold"]
        V = [x["id"] for x in await rag.chunks_vdb.query(q, top_k=TOPN)]
        G = [t[0] for t in r["buggy"]["top"]][:TOPN]
        t0 = time.perf_counter(); K = bm.rank(q); tt.append(1000 * (time.perf_counter() - t0))
        Kn = bm.rank(re.sub(r'\b20\d{6}\b', ' ', q))
        qd = query_days(q); T = None
        if qd:
            vpos = {c: i for i, c in enumerate(V)}
            T = [c for *_, c in sorted((min(abs(CDAY[c] - d) for d in qd), vpos.get(c, 999), c) for c in chunks if CDAY.get(c))][:TOPN]
        var = {"V3 = RRF(G,V)": rrf(G, V), "+K": rrf(G, V, K), "+K (bỏ token ngày)": rrf(G, V, Kn),
               "+T": rrf(G, V, T) if T else rrf(G, V), "+K+T": rrf(G, V, K, T) if T else rrf(G, V, K),
               "RRF(V,K) bỏ đồ thị": rrf(V, K), "RRF(V,K,T) bỏ đồ thị": rrf(V, K, T) if T else rrf(V, K), "K thuần": K}
        R.append(dict(t=r["type"], gold=gold, qd=bool(qd), kept={n: a1(o, TOK) for n, o in var.items()}))
    def cmp(rs, n, ref):
        f = [all(g in x["kept"][n] for g in x["gold"]) for x in rs]; bf = [all(g in x["kept"][ref] for g in x["gold"]) for x in rs]
        b = sum(a and not z for a, z in zip(f, bf)); c = sum(z and not a for a, z in zip(f, bf)); return sum(f), b, c, mcnemar(b, c)
    groups = (("TỔNG", lambda x: True), ("Single", lambda x: x["t"] == "Single"), ("Multi", lambda x: x["t"] == "Multi"),
              ("câu CÓ ngày", lambda x: x["qd"]), ("câu KHÔNG ngày", lambda x: not x["qd"]))
    for gname, sel in groups:
        rs = [x for x in R if sel(x)]; ng = sum(len(x["gold"]) for x in rs)
        print(f"--- {gname}: {len(rs)} câu, {ng} chunk")
        for n in R[0]["kept"]:
            ch = sum(g in x["kept"][n] for x in rs for g in x["gold"])
            full, b, c, p = cmp(rs, n, "V3 = RRF(G,V)"); _, b2, c2, p2 = cmp(rs, n, "+K")
            tok = st.median(sum(TOK[cc] for cc in x["kept"][n]) for x in rs)
            print(f"   {n:24s} chunk {100*ch/ng:5.1f}% đủ {100*full/len(rs):5.1f}% │ vs V3 {b:2d}/{c:2d} p={p:.3f} │ vs +K {b2:2d}/{c2:2d} p={p2:.3f} │ tok {tok:.0f}")
    print(f"\nBM25 xếp hạng 514 chunk: trung vị {st.median(tt):.2f} ms/câu, max {max(tt):.2f} ms (Python thuần, 1 luồng)")
if __name__ == "__main__": asyncio.run(main())
