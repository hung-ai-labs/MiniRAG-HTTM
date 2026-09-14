"""Probe offline (dev 200, 0 API, 0 GPU): mỗi trường planner như MỘT bảng xếp hạng thêm vào RRF(G,V).
Không đổi V3. G = xếp hạng đồ thị đã lưu (diag_path2chunk, PATH2CHUNK_FIX=0 = cấu hình V3), V = vector top-30.
Trường chỉ lấy từ CHỮ trong câu hỏi (regex tất định) -- cận dưới của một parser tốt, không dùng Evidence lúc xếp hạng."""
import asyncio, collections, datetime as dt, json, math, os, re, statistics as st, sys
sys.path.insert(0, 'reproduce'); sys.path.insert(0, '.')
from simulate_fusion import a1, rrf, mcnemar, TOPN
from gemini_common import build_rag, get_args
import minirag.operate as op

STOP = set(("a an the of to in on at for from by with about and or is are was were be been being do does did has have had that this "
            "these those what which who whom whose when where why how whether his her their its he she they it i you we me him them my "
            "your our as into than then there here more most any some all can could would should will may might question").split())
def toks(s): return re.findall(r"[a-z0-9]+", s.lower())

class BM25:  # Okapi, k1=1.2 b=0.75 mặc định sách giáo khoa, không tinh chỉnh
    def __init__(self, docs, k1=1.2, b=0.75):
        self.ids = list(docs); self.tf = [collections.Counter(toks(docs[i])) for i in self.ids]
        self.L = [sum(t.values()) for t in self.tf]; self.avg = sum(self.L) / len(self.L)
        df = collections.Counter(w for t in self.tf for w in t); N = len(self.ids)
        self.idf = {w: math.log(1 + (N - n + .5) / (n + .5)) for w, n in df.items()}; self.k1, self.b = k1, b
    def rank(self, q, n=TOPN):
        qs = [w for w in toks(q) if w not in STOP]; out = []
        for cid, t, L in zip(self.ids, self.tf, self.L):
            s = sum(self.idf[w] * t[w] * (self.k1 + 1) / (t[w] + self.k1 * (1 - self.b + self.b * L / self.avg)) for w in qs if t.get(w))
            if s > 0: out.append((s, cid))
        return [c for _, c in sorted(out, key=lambda x: -x[0])[:n]]

MON = {m: i + 1 for i, m in enumerate("january february march april may june july august september october november december".split())}
def dnum(y, m, d):
    try: return dt.date(y, m, d).toordinal()
    except ValueError: return None
def query_days(q):
    out = [dnum(int(m[1]), int(m[2]), int(m[3])) for m in re.finditer(r'\b(20\d{2})(\d{2})(\d{2})\b', q)]
    out += [dnum(int(m[3] or 2026), MON[m[1].lower()], int(m[2])) for m in re.finditer(
        r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,\s*(20\d{2}))?', q, re.I)]
    return [d for d in out if d]
def day_of(txt):
    m = re.search(r'Time:\s*(\d{4})(\d{2})(\d{2})_', txt or ''); return dnum(int(m[1]), int(m[2]), int(m[3])) if m else None

def split_q(q):
    q2 = re.sub(r'^\s*Question:\s*', '', q).strip().rstrip('?')
    m = re.search(r'between (.+?) and (.+?)(?: more than| less than|\s*\(|$)', q2, re.I)
    if m: return [m[1], m[2]]
    for conn in (' before ', ' after '):
        if conn in q2:
            a, b = q2.split(conn, 1)
            if len(toks(a)) >= 3 and len(toks(b)) >= 3: return [a, b]
    m = re.search(r'^(.+?)\s+and\s+((?:who|what|when|where|how|which)\b.+)$', q2, re.I)
    return [m[1], m[2]] if m else []

async def main():
    args = get_args("planner probe"); rag = build_rag(args); wd = args.workingdir
    chunks = json.load(open(os.path.join(wd, "kv_store_text_chunks.json")))
    docs = json.load(open(os.path.join(wd, "kv_store_full_docs.json")))
    TOK = {c: len(op.encode_string_by_tiktoken(v["content"])) for c, v in chunks.items()}
    CDAY = {c: day_of(v["content"]) or day_of(docs.get(v["full_doc_id"], {}).get("content")) for c, v in chunks.items()}
    bm = BM25({c: v["content"] for c, v in chunks.items()})
    G_ = rag.chunk_entity_relation_graph
    recs = [json.loads(l) for l in open("logs/diag_path2chunk.jsonl", encoding="utf-8") if l.strip()]
    ok = [r for r in recs if r.get("reached_kwd2chunk") and r["gold"]]
    R = []
    for r in ok:
        q, gold = r["question"], r["gold"]
        V100 = [x["id"] for x in await rag.chunks_vdb.query(q, top_k=100)]; V = V100[:TOPN]
        G = [t[0] for t in r["buggy"]["top"]][:TOPN]
        K = bm.rank(q)
        qd = query_days(q)
        T = None
        if qd:
            vpos = {c: i for i, c in enumerate(V)}
            T = [c for *_, c in sorted((min(abs(CDAY[c] - d) for d in qd), vpos.get(c, 999), c) for c in chunks if CDAY.get(c))][:TOPN]
        subs = split_q(q)
        S = [[x["id"] for x in await rag.chunks_vdb.query(s, top_k=TOPN)] for s in subs] if subs else None
        E = []
        for it in await rag.relationships_vdb.query(q, top_k=60):
            e = await G_.get_edge(it["src_id"], it["tgt_id"])
            for s in op.split_string_by_multi_markers((e or {}).get("source_id", ""), [op.GRAPH_FIELD_SEP]):
                s = s.strip()
                if s in chunks and s not in E: E.append(s)
            if len(E) >= TOPN: break
        E = E[:TOPN]
        base = rrf(G, V)
        var = {"V3 = RRF(G,V)": base,
               "+T ngày trong câu (regex)": rrf(G, V, T) if T else base,
               "+S câu con (tách mệnh đề)": rrf(G, V, *S) if S else base,
               "+K BM25 câu gốc": rrf(G, V, K),
               "+E cạnh relationships_vdb": rrf(G, V, E),
               "vector thuần (tham chiếu)": V}
        R.append(dict(q=q, t=r["type"], gold=gold, ev=r["evidence"], qd=qd, subs=subs, G=G, V=V, V100=V100, K=K, E=E, T=T, S=S,
                      base=base, kept={n: a1(o, TOK) for n, o in var.items()}))

    NG = sum(len(x["gold"]) for x in R)
    print(f"dev: {len(R)} câu có evidence, {NG} chunk đáp án. Single {sum(x['t']=='Single' for x in R)}, Multi {sum(x['t']=='Multi' for x in R)}\n")
    print("A. TỪNG BẢNG XẾP HẠNG: recall chunk đáp án ở top-30, và phần MỚI ngoài G∪V")
    GV = lambda x: set(x["G"]) | set(x["V"])
    def rec(key, only=None):
        rs = [x for x in R if x[key] is not None and (only is None or only(x))]
        if key == "S": hits = [(g in set().union(*map(set, x["S"])), g in GV(x)) for x in rs for g in x["gold"]]
        else: hits = [(g in x[key], g in GV(x)) for x in rs for g in x["gold"]]
        n = len(hits); return len(rs), n, sum(h for h, _ in hits), sum(h and not u for h, u in hits)
    for key, lab in (("G", "G đồ thị"), ("V", "V vector top-30"), ("V100", "vector top-100"), ("K", "K BM25 câu gốc"),
                     ("E", "E cạnh"), ("T", "T ngày (chỉ câu có ngày)"), ("S", "S câu con (chỉ câu tách được)")):
        nq, n, h, new = rec(key)
        print(f"  {lab:32s} {nq:3d} câu {n:3d} chunk · recall {100*h/max(1,n):5.1f}% · mới ngoài G∪V {new}")
    u = sum(g in GV(x) for x in R for g in x["gold"])
    inlist = sum(g in x["base"] for x in R for g in x["gold"])
    kept = sum(g in x["kept"]["V3 = RRF(G,V)"] for x in R for g in x["gold"])
    print(f"  G∪V chứa {u}/{NG} = {100*u/NG:.1f}%; sau A1@4000 còn {kept} = {100*kept/NG:.1f}%  → mất ở bước cắt ngân sách: {inlist-kept} chunk")
    print(f"  ngoài G∪V hoàn toàn: {NG-u} chunk ({100*(NG-u)/NG:.1f}%) — trần của mọi 'nguồn ứng viên mới'\n")

    print("B. MỖI BIẾN THỂ SAU A1@4000 (so với V3 mô phỏng; McNemar trên 'câu đủ đáp án')")
    for grp, sel in (("TỔNG", lambda x: True), ("Single", lambda x: x["t"] == "Single"), ("Multi", lambda x: x["t"] == "Multi")):
        rs = [x for x in R if sel(x)]; ng = sum(len(x["gold"]) for x in rs)
        print(f"  --- {grp}: {len(rs)} câu, {ng} chunk")
        for n in R[0]["kept"]:
            ch = sum(g in x["kept"][n] for x in rs for g in x["gold"])
            full = [all(g in x["kept"][n] for g in x["gold"]) for x in rs]
            bfull = [all(g in x["kept"]["V3 = RRF(G,V)"] for g in x["gold"]) for x in rs]
            b = sum(f and not bf for f, bf in zip(full, bfull)); c = sum(bf and not f for f, bf in zip(full, bfull))
            aff = sum(x["kept"][n] != x["kept"]["V3 = RRF(G,V)"] for x in rs)
            tok = st.median(sum(TOK[cc] for cc in x["kept"][n]) for x in rs); nch = st.median(len(x["kept"][n]) for x in rs)
            print(f"    {n:30s} chunk {100*ch/ng:5.1f}% · đủ {100*sum(full)/len(rs):5.1f}% · {b:2d} lên/{c:2d} xuống p={mcnemar(b,c):.3f}"
                  f" · đổi context {aff:3d} câu · token tv {tok:.0f} · chunk tv {nch:.0f}")

    print("\nC. THỜI GIAN")
    dq = [x for x in R if x["qd"]]
    evd = lambda x: {day_of('Time: ' + e) for e in x["ev"]}
    print(f"  câu có evidence mang ngày cụ thể: {len(dq)} ({collections.Counter(x['t'] for x in dq)})")
    print(f"  ngày trong câu TRÙNG ngày evidence: {sum(bool(set(x['qd']) & evd(x)) for x in dq)}/{len(dq)}")
    for n in ("V3 = RRF(G,V)", "+T ngày trong câu (regex)", "+K BM25 câu gốc"):
        print(f"  {n:30s} đủ đáp án trên nhóm có ngày: {sum(all(g in x['kept'][n] for g in x['gold']) for x in dq)}/{len(dq)}")
    print(f"  BM25 top-30 đã chứa đủ gold ở nhóm có ngày: {sum(all(g in x['K'] for g in x['gold']) for x in dq)}/{len(dq)}")

    print("\nD. CÂU CON")
    sq = [x for x in R if x["S"]]
    print(f"  tách được: {len(sq)} câu ({collections.Counter(x['t'] for x in sq)})")
    for x in sq[:6]: print("    ", x["t"], "|", " ‖ ".join(x["subs"])[:150])
    mq = [x for x in R if x["t"] == "Multi"]
    print(f"  Multi: V3 thiếu evidence ở {sum(not all(g in x['kept']['V3 = RRF(G,V)'] for g in x['gold']) for x in mq)}/{len(mq)} câu")
if __name__ == "__main__": asyncio.run(main())
