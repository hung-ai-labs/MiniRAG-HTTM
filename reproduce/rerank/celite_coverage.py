"""CE-lite, bước THĂM DÒ — độ phủ và chi phí của các luật chọn tập con, tính trên điểm CE1 đã lưu.

    .venv/bin/python reproduce/rerank/celite_coverage.py | tee logs/rerank/celite_coverage.txt

⚠ Đây là phần THĂM DÒ, dùng để CHỌN luật. Nó chỉ đo ĐỘ PHỦ (chunk đáp án của ca đó có nằm trong tập con không)
và CHI PHÍ (số ứng viên, số cửa sổ MaxP). Nó KHÔNG đo giữ bằng chứng / Single / Multi / Null — các số đó chỉ
được đo MỘT LẦN cho luật đã chốt, trong celite_eval.py, sau khi đăng ký trước.

Evidence chỉ dùng để đánh giá độ phủ. Không luật nào đọc nhãn vàng lúc chạy.
"""
import json, os, statistics as st, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "reproduce", "retrieval_audit"))
sys.path.insert(0, HERE)
import diagnose as d  # noqa: E402
from ce_score import MAXLEN, load_model  # noqa: E402

REFS = os.path.join(ROOT, "logs", "rerank", "ce1_refs.json")


# ---------------------------------------------------------------- luật chọn tập con (chỉ đọc hạng và độ dài chunk)
def top_rrf(r, n):
    return r["ranked_ids"][:n]


def union_bv(r, n):
    top = set(r["bm25_ids"][:n]) | set(r["vector_ids"][:n])
    return [c for c in r["ranked_ids"] if c in top]      # giữ thứ tự RRF cho ổn định


def token_horizon(r, mult):
    """Tiền tố theo NGÂN SÁCH TOKEN: lấy theo thứ tự RRF tới khi token cộng dồn chạm mult × 4000."""
    out, t = [], 0
    for c in r["ranked_ids"]:
        out.append(c)
        t += d.tok(c)
        if t >= mult * d.BUDGET:
            break
    return out


def main():
    tok, _, _ = load_model()
    wp = {}

    def n_windows(q, subset):
        """Số cửa sổ MaxP đúng công thức đã ghim: cửa sổ = 512 − len(q) − 3, bước = cửa sổ // 2."""
        if q not in wp:
            wp[q] = len(tok(q, add_special_tokens=False)["input_ids"])
        w = MAXLEN - wp[q] - 3
        step = max(1, w // 2)
        n = 0
        for c in subset:
            if c not in wp:
                wp[c] = len(tok(d.CHUNKS[c]["content"], add_special_tokens=False)["input_ids"])
            t = wp[c]
            n += 1 if t <= w else len(range(0, t - w + step, step))
        return n

    recs = {r["question"]: r for r in (json.loads(l) for l in open(d.CTX, encoding="utf-8")) if not r.get("none")}
    gold = d.gold_map()
    refs = json.load(open(REFS, encoding="utf-8"))
    cut, resc = refs["cut"], set(refs["rescued"])

    print(f"THĂM DÒ — {len(cut)} ca độ sâu xếp hạng · CE1 cứu được {len(resc)}\n")
    print("1. Chunk đáp án bị cắt của từng ca")
    print("   loại | hạng RRF | BM25 | vec | nguồn | tok | CE1 cứu | token cộng dồn tới nó")
    rows = []
    for q in cut:
        r = recs[q]
        g = min([x for x in gold[q] if x not in r["chunk_ids"]], key=lambda c: r["ranked_ids"].index(c))
        rrf = r["ranked_ids"].index(g) + 1
        br = r["bm25_ids"].index(g) + 1 if g in r["bm25_ids"] else None
        vr = r["vector_ids"].index(g) + 1 if g in r["vector_ids"] else None
        src = "cả hai" if br and vr else "vector" if vr else "bm25"
        cum = sum(d.tok(c) for c in r["ranked_ids"][:rrf])
        rows.append({"q": q, "type": r["type"], "gold": g, "rrf": rrf, "bm25": br, "vec": vr,
                     "src": src, "tok": d.tok(g), "resc": q in resc, "cum": cum})
        print(f"   {r['type'][:1]}    | {rrf:8d} | {str(br):>4s} | {str(vr):>3s} | {src:6s} | {d.tok(g):4d} | "
              f"{'CÓ' if q in resc else '—':7s} | {cum:6d}")

    rr = sorted(x["rrf"] for x in rows if x["resc"])
    nr = sorted(x["rrf"] for x in rows if not x["resc"])
    cum_r = sorted(x["cum"] for x in rows if x["resc"])
    print(f"\n   hạng RRF, 11 ca CE1 CỨU ĐƯỢC  : {rr}  (max {max(rr)})")
    print(f"   hạng RRF, 9 ca KHÔNG cứu được : {nr}")
    print(f"   token cộng dồn, 11 ca cứu được: trung vị {st.median(cum_r):.0f} · max {max(cum_r)}")

    print("\n2. Độ phủ và chi phí từng luật")
    full_w = st.mean([n_windows(q, recs[q]["ranked_ids"]) for q in recs])
    full_c = st.mean([len(recs[q]["ranked_ids"]) for q in recs])
    print(f"   {'luật':36s} | phủ 11 ca cứu | phủ 20 ca | ứng viên/câu | cửa sổ/câu | % chi phí CE1")
    rules = ([(f"top {n} theo RRF", lambda r, n=n: top_rrf(r, n)) for n in (10, 15, 20, 25, 30)]
             + [(f"hợp top {n} BM25 & top {n} vector", lambda r, n=n: union_bv(r, n)) for n in (10, 15, 20)]
             + [(f"tiền tố token {m}× ngân sách", lambda r, m=m: token_horizon(r, m)) for m in (1.5, 2.0, 2.5, 3.0)])
    for name, fn in rules:
        cov_resc = cov_all = 0
        for x in rows:
            sub = set(fn(recs[x["q"]]))
            cov_all += x["gold"] in sub
            cov_resc += (x["gold"] in sub) and x["resc"]
        n_c = st.mean([len(fn(recs[q])) for q in recs])
        n_w = st.mean([n_windows(q, fn(recs[q])) for q in recs])
        print(f"   {name:36s} | {cov_resc:2d}/11         | {cov_all:2d}/20     | {n_c:11.1f}  | {n_w:9.1f}  |"
              f" {100 * n_w / full_w:5.0f}%")
    print(f"\n   CE1 đầy đủ: ứng viên/câu {full_c:.1f} · cửa sổ/câu {full_w:.1f} = 100% "
          f"(tương ứng p50 1830 ms, max 3429 ms trên CPU)")


if __name__ == "__main__":
    main()
