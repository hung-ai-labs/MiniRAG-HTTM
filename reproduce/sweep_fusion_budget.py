"""Cắt có còn hy vọng không, hay chỉ hỏng vì xếp hạng kém? Quét ngân sách token và cắt vách
trên xếp hạng đồ thị hiện tại, RRF, và vector thuần. Offline, 0 API. Chỉ để phân tích --
KHÔNG dùng để chọn cấu hình cho lượt đang chạy."""
import asyncio, json, os, sys, statistics as st
sys.path.insert(0, "reproduce"); sys.path.insert(0, ".")
import minirag.operate as op
from simulate_fusion import rrf
from gemini_common import build_rag, get_args

def cut_budget(order, TOK, B):
    kept, tok = [], 0
    for c in order:
        if c not in TOK: continue
        tok += TOK[c]
        if tok > B: break
        kept.append(c)
    return kept

async def main(args):
    rag = build_rag(args)
    chunks = json.load(open(os.path.join(args.workingdir, "kv_store_text_chunks.json")))
    TOK = {c: len(op.encode_string_by_tiktoken(x["content"])) for c, x in chunks.items()}
    recs = [json.loads(l) for l in open("logs/diag_path2chunk.jsonl") if l.strip()]
    ok = [r for r in recs if r.get("reached_kwd2chunk") and r["gold"]]
    G = sum(len(r["gold"]) for r in ok)
    orders = {}
    for r in ok:
        v = [x["id"] for x in await rag.chunks_vdb.query(r["question"], top_k=30)]
        gb = [t[0] for t in r["buggy"]["top"]][:30]
        orders[r["question"]] = {"đồ thị hiện tại": gb, "RRF": rrf(gb, v), "vector thuần": v,
                                 "_gscore": [(t[0], t[1]) for t in r["buggy"]["top"]][:30]}
    print(f"{len(ok)} câu, {G} chunk đáp án — % chunk đáp án giữ được (token Sources trung vị)\n")
    print(f"{'ngân sách':>10s}" + "".join(f"{n:>24s}" for n in ("đồ thị hiện tại", "RRF", "vector thuần")))
    for B in (1000, 2000, 3000, 4000, 6000, 8000, 10**9):
        row = f"{'không cắt' if B == 10**9 else B:>10}"
        for n in ("đồ thị hiện tại", "RRF", "vector thuần"):
            ks = {q: cut_budget(o[n], TOK, B) for q, o in orders.items()}
            hit = sum(sum(g in ks[r["question"]] for g in r["gold"]) for r in ok)
            tk = st.median(sum(TOK[c] for c in ks[r["question"]]) for r in ok)
            row += f"{100*hit/G:14.1f}% ({tk:6.0f})"
        print(row)
    # Cắt vách: đồ thị dùng điểm thật; RRF dùng điểm RRF.
    print("\ncắt vách (tụt mạnh nhất), rồi A1@4000 làm trần:")
    for n in ("đồ thị hiện tại", "RRF"):
        hit, toks, ns = 0, [], []
        for r in ok:
            o = orders[r["question"]]
            if n == "đồ thị hiện tại":
                sc = [s for _, s in o["_gscore"]]; order = [c for c, _ in o["_gscore"]]
            else:
                v = o["vector thuần"]; gb = o["đồ thị hiện tại"]
                d = {}
                for rk in (gb, v):
                    for i, c in enumerate(rk): d[c] = d.get(c, 0) + 1 / (60 + i + 1)
                order = rrf(gb, v); sc = [d[c] for c in order]
            k = op._knee_keep(sc)
            kept = cut_budget(order[:k], TOK, 4000)
            hit += sum(g in kept for g in r["gold"]); toks.append(sum(TOK[c] for c in kept)); ns.append(len(kept))
        print(f"  {n:16s} giữ {100*hit/G:5.1f}% đáp án · chunk tv {st.median(ns)} · token tv {st.median(toks):.0f}")

asyncio.run(main(get_args("budget sweep")))
