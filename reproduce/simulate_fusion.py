"""Mô phỏng offline: trộn xếp hạng đồ thị với xếp hạng vector có giữ được chunk đáp án không.

Động cơ (chẩn đoán dev 200, 13/09): top-30 vector thuần chứa 87,0% chunk đáp án, còn
xếp hạng đồ thị (kwd2chunk) chỉ giữ 62,3% trong 30 chunk và 45-47% sau A1@4000.
kwd2chunk chỉ xếp hạng chunk nằm trên đường đi; chunk vector tìm được mà không nằm
trên đường nào thì không bao giờ vào context.

Không tốn API: xếp hạng đồ thị lấy từ logs/diag_path2chunk.jsonl, xếp hạng vector tính
lại bằng chunks_vdb (MiniLM cục bộ) và được đối chiếu với vector_gold_hit đã lưu.
RRF dùng k=60 -- hằng số mặc định của Cormack et al. 2009, không tinh chỉnh.
"""
import asyncio, collections, json, math, os, statistics as st, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(_HERE); sys.path.append(os.path.dirname(_HERE))
import minirag.operate as op  # noqa: E402
from gemini_common import build_rag, get_args  # noqa: E402

A1, K_RRF, TOPN = 4000, 60, 30


def a1(order, TOK):
    kept, tok = [], 0
    for cid in order:
        if cid not in TOK:
            continue
        tok += TOK[cid]
        if tok > A1:
            break
        kept.append(cid)
    return kept


def rrf(*rankings):
    sc = collections.defaultdict(float)
    for rk in rankings:
        for i, cid in enumerate(rk):
            sc[cid] += 1 / (K_RRF + i + 1)
    return [c for c, _ in sorted(sc.items(), key=lambda x: -x[1])]


def mcnemar(b, c):
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n)


async def main(args):
    rag = build_rag(args)
    chunks = json.load(open(os.path.join(args.workingdir, "kv_store_text_chunks.json")))
    TOK = {cid: len(op.encode_string_by_tiktoken(c["content"])) for cid, c in chunks.items()}
    recs = [json.loads(l) for l in open("logs/diag_path2chunk.jsonl", encoding="utf-8") if l.strip()]
    ok = [r for r in recs if r.get("reached_kwd2chunk") and r["gold"]]

    names = ["đồ thị có lỗi (hiện tại)", "đồ thị đã sửa", "vector thuần",
             "RRF(đồ thị có lỗi, vector)", "RRF(đồ thị đã sửa, vector)"]
    kept_by = {n: {} for n in names}
    mism = 0
    for r in ok:
        v = [x["id"] for x in await rag.chunks_vdb.query(r["question"], top_k=TOPN)]
        if [g in v for g in r["gold"]] != r["vector_gold_hit"]:
            mism += 1
        gb = [t[0] for t in r["buggy"]["top"]][:TOPN]
        gf = [t[0] for t in r["fixed"]["top"]][:TOPN]
        for n, order in zip(names, (gb, gf, v, rrf(gb, v), rrf(gf, v))):
            kept_by[n][r["question"]] = a1(order, TOK)

    print(f"vector tính lại lệch cờ đã lưu: {mism}/{len(ok)} câu"
          f"{'  <- mô phỏng CHÍNH XÁC' if mism == 0 else '  <- CẢNH BÁO: mô phỏng lệch'}")
    for label, sel in (("TỔNG", lambda r: True), ("Single", lambda r: r["type"] == "Single"),
                       ("Multi", lambda r: r["type"] == "Multi")):
        rs = [r for r in ok if sel(r)]
        G = sum(len(r["gold"]) for r in rs)
        print(f"\n--- {label}: {len(rs)} câu, {G} chunk đáp án · A1@{A1} ---")
        print(f"{'cách xếp hạng':30s}{'chunk đáp án giữ':>18s}{'câu đủ đáp án':>15s}"
              f"{'chunk tv':>10s}{'token tv':>10s}")
        for n in names:
            kb = kept_by[n]
            hit = sum(sum(g in kb[r["question"]] for g in r["gold"]) for r in rs)
            full = sum(all(g in kb[r["question"]] for g in r["gold"]) for r in rs)
            print(f"{n:30s}{100*hit/G:17.1f}%{100*full/len(rs):14.1f}%"
                  f"{st.median(len(kb[r['question']]) for r in rs):10.1f}"
                  f"{st.median(sum(TOK[c] for c in kb[r['question']]) for r in rs):10.0f}")
        base, best = kept_by[names[0]], kept_by[names[4]]
        b = sum(all(g in best[r["question"]] for g in r["gold"]) and
                not all(g in base[r["question"]] for g in r["gold"]) for r in rs)
        c = sum(all(g in base[r["question"]] for g in r["gold"]) and
                not all(g in best[r["question"]] for g in r["gold"]) for r in rs)
        print(f"McNemar 'câu đủ đáp án', RRF(đã sửa) vs hiện tại: {b} lên / {c} xuống, p = {mcnemar(b, c):.4f}")


if __name__ == "__main__":
    asyncio.run(main(get_args("Mô phỏng hybrid fusion")))
