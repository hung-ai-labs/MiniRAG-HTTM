"""A3 khả thi không: tín hiệu truy hồi có tách được câu Null khỏi câu có đáp án không?
Offline, 0 API. Type chỉ dùng để ĐO khả năng tách, không dùng lúc chạy."""
import asyncio, csv, json, statistics as st, sys
sys.path.insert(0, "reproduce"); sys.path.insert(0, ".")
from gemini_common import build_rag, get_args

def auc(pos, neg):
    s = sum(1 if a > b else 0.5 if a == b else 0 for a in pos for b in neg)
    return s / (len(pos) * len(neg))

async def main(args):
    rag = build_rag(args)
    seen, data = set(), []
    for r in csv.DictReader(open("dataset/LiHua-World/qa/query_set.csv")):
        q = r["Question"]
        if q in seen: continue
        seen.add(q)
        res = await rag.chunks_vdb.query(q, top_k=30)
        if not data: print("trường kết quả vdb:", list(res[0].keys()) if res else None)
        sims = [float(x["distance"]) for x in res]
        data.append({"q": q, "type": r["Type"], "top1": sims[0] if sims else 0.0,
                     "gap12": (sims[0] - sims[1]) if len(sims) > 1 else 0.0,
                     "top5": st.mean(sims[:5]) if sims else 0.0, "ids": [x["id"] for x in res]})
    print(f"\n{len(data)} câu · Null {sum(d['type']=='Null' for d in data)}\n")
    print(f"{'tín hiệu':34s}{'Null tv':>9s}{'có đáp án tv':>14s}{'AUC':>7s}")
    for f, lab in (("top1", "cosine chunk tốt nhất"), ("top5", "cosine trung bình top-5"),
                   ("gap12", "khoảng cách top1 - top2")):
        nul = [d[f] for d in data if d["type"] == "Null"]; ans = [d[f] for d in data if d["type"] != "Null"]
        print(f"{lab:34s}{st.median(nul):9.3f}{st.median(ans):14.3f}{auc(ans, nul):7.3f}")
    vec = {d["q"]: d["ids"] for d in data}
    on, oa = [], []
    for r in map(json.loads, open("logs/diag_path2chunk.jsonl")):
        if not r.get("reached_kwd2chunk"): continue
        ov = len(set(t[0] for t in r["buggy"]["top"][:30]) & set(vec[r["question"]]))
        (on if r["type"] == "Null" else oa).append(ov)
    print(f"{'trùng đồ thị∩vector top-30 (dev)':34s}{st.median(on):9.1f}{st.median(oa):14.1f}{auc(oa, on):7.3f}"
          f"   (Null n={len(on)}, có đáp án n={len(oa)})")
    print("\nAUC = xác suất một câu có đáp án có tín hiệu cao hơn một câu Null. 0,5 = không tách được.")

asyncio.run(main(get_args("A3 feasibility")))
