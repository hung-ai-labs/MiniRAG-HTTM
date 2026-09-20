"""Chẩn đoán độ sâu xếp hạng của B2 — offline, không sinh, không chấm, không reranker.

    .venv/bin/python reproduce/retrieval_audit/ranking_depth.py | tee logs/retrieval_audit/ranking_depth.txt

Định nghĩa nhóm và tiêu chí độ phủ chốt trước trong logs/retrieval_audit/RANKING_DEPTH.md.
Evidence, Type, đáp án vàng chỉ dùng để ĐÁNH GIÁ; mọi tín hiệu chỉ đọc câu hỏi và nội dung chunk.
"""
import asyncio, collections, csv, json, math, os, re, statistics as st, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
import diagnose as d  # noqa: E402
from minirag.bm25 import STOP, tokenize, BM25Index  # noqa: E402

HIGH, LOW = 5, 10
IDX = BM25Index({cid: v["content"] for cid, v in d.CHUNKS.items()})
BM_POS = {cid: i for i, cid in enumerate(IDX.ids)}
QWORDS = {"what", "which", "who", "whom", "whose", "when", "where", "why", "how", "did", "does", "do", "is", "are", "was",
          "were", "in", "on", "at", "the", "a", "an", "during", "after", "before", "according", "based", "besides", "if",
          "has", "have", "will", "can", "could", "would", "should", "and", "or", "of", "for", "to", "with"}
MONTHS = {m: i + 1 for i, m in enumerate("january february march april may june july august september october november "
                                          "december".split())}
N_CHUNKS = len(d.CHUNKS)
FLAT = {cid: re.sub(r"\s+", "", v["content"].lower()) for cid, v in d.CHUNKS.items()}


# ---------------------------------------------------------------- tín hiệu (chỉ đọc câu hỏi + chunk)
def bm25_score(q, cid):
    terms = [w for w in tokenize(q) if w not in STOP]
    i = BM_POS[cid]
    tf, length = IDX.tf[i], IDX.lens[i]
    return sum(IDX.idf[w] * tf[w] * (IDX.k1 + 1) / (tf[w] + IDX.k1 * (1 - IDX.b + IDX.b * length / IDX.avg))
               for w in terms if tf.get(w))


def idf_cov(q, cid):
    terms = {w for w in tokenize(q) if w not in STOP}
    words = set(tokenize(d.CHUNKS[cid]["content"]))
    tot = sum(IDX.idf.get(w, 0) for w in terms)
    return sum(IDX.idf.get(w, 0) for w in terms & words) / tot if tot else 0.0


def entities(q):
    """Cụm từ viết hoa liên tiếp không đứng đầu câu; bỏ thực thể có mặt trong > 50% chunk (vd. nhân vật chính)."""
    toks = re.findall(r"[A-Za-z][A-Za-z'\-]*|\S", q)
    ents, cur = [], []
    for i, t in enumerate(toks):
        if t[0].isupper() and i > 0 and t.lower() not in QWORDS:
            cur.append(t)
        else:
            if cur:
                ents.append("".join(cur).lower())
            cur = []
    if cur:
        ents.append("".join(cur).lower())
    out = []
    for e in dict.fromkeys(ents):
        df = sum(1 for f in FLAT.values() if e in f)
        if 0 < df <= N_CHUNKS / 2:
            out.append(e)
    return out


def ent_cov(q, cid, ents):
    return sum(e in FLAT[cid] for e in ents) / len(ents) if ents else None


def q_date(q):
    m = re.search(r"\b(20\d\d)(\d\d)(\d\d)\b", q)
    if m:
        return "".join(m.groups())
    m = re.search(r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d\d)\b", q, re.I)
    if m:
        return f"{m.group(3)}{MONTHS[m.group(1).lower()]:02d}{int(m.group(2)):02d}"
    return None


def date_match(qd, cid):
    t = d.ctime(cid)
    return None if qd is None else (1.0 if t and t[:8] == qd else 0.0)


def jacc(a, b):
    wa, wb = d.words(a), d.words(b)
    return len(wa & wb) / len(wa | wb) if wa and wb else 0.0


# ---------------------------------------------------------------- vector: tính lại cosine, kiểm khớp hạng đã log
def vector_scores(questions):
    from nano_vectordb.dbs import buffer_string_to_array
    from transformers import AutoModel, AutoTokenizer
    from minirag.llm.hf import hf_embed
    vdb = json.load(open(os.path.join(ROOT, "LiHua-World-qwen-modal", "vdb_chunks.json"), encoding="utf-8"))
    mat = buffer_string_to_array(vdb["matrix"]).reshape(-1, vdb["embedding_dim"])
    mat = mat / np.linalg.norm(mat, axis=-1, keepdims=True)
    ids = [x["__id__"] for x in vdb["data"]]
    name = "sentence-transformers/all-MiniLM-L6-v2"
    tok, model = AutoTokenizer.from_pretrained(name), AutoModel.from_pretrained(name)
    out = {}
    for q in questions:
        e = asyncio.run(hf_embed([q], tokenizer=tok, embed_model=model))[0]
        e = e / np.linalg.norm(e)
        s = mat @ e
        out[q] = {ids[i]: float(s[i]) for i in range(len(ids))}
    return out


def main():
    recs = [json.loads(l) for l in open(d.CTX, encoding="utf-8")]
    recs = {r["question"]: r for r in recs if not r.get("none")}
    gold = d.gold_map()
    sheet = {r["cau_hoi"]: r["id"] for r in csv.DictReader(open(os.path.join(ROOT, "logs", "null_audit", "d3_label_audit",
                                                                              "sheet_A.csv"), encoding="utf-8"))}
    vs = vector_scores(list(recs))
    # kiểm: sắp cosine lại phải ra đúng vector_ids đã log (top-30)
    ok = sum(1 for q, r in recs.items()
             if [c for c, _ in sorted(vs[q].items(), key=lambda x: -x[1])[:30]] == r["vector_ids"])
    print(f"Kiểm vector: sắp lại cosine khớp vector_ids đã log {ok}/{len(recs)} câu")
    okb = sum(1 for q, r in recs.items() if IDX.rank(q, 30) == r["bm25_ids"])
    print(f"Kiểm BM25: xếp lại khớp bm25_ids đã log {okb}/{len(recs)} câu\n")

    def feats(q, r, cid, ents, qd):
        rk = r["ranked_ids"]
        vr = r["vector_ids"].index(cid) + 1 if cid in r["vector_ids"] else None
        br = r["bm25_ids"].index(cid) + 1 if cid in r["bm25_ids"] else None
        above = rk[: rk.index(cid)]
        doc = d.CHUNKS[cid]["full_doc_id"]
        return {"rrf": rk.index(cid) + 1, "bm25_rank": br, "bm25": round(bm25_score(q, cid), 2), "vec_rank": vr,
                "vec": round(vs[q][cid], 3), "src": "both" if vr and br else "vector" if vr else "bm25",
                "tok": d.tok(cid), "idf_cov": round(idf_cov(q, cid), 2), "ent_cov": ent_cov(q, cid, ents),
                "date": date_match(qd, cid), "doc": doc,
                "same_doc_above": any(d.CHUNKS[a]["full_doc_id"] == doc for a in above),
                "max_jacc_above": round(max([jacc(cid, a) for a in above] or [0]), 2)}

    # ---- tập 20 ca
    cut = []
    for q, r in recs.items():
        if q not in gold or not all(g in r["ranked_ids"] for g in gold[q]):
            continue
        miss = [g for g in gold[q] if g not in r["chunk_ids"]]
        if not miss:
            continue
        k = len(r["chunk_ids"])
        if r["ranked_ids"][k] in gold[q]:
            continue
        cut.append(q)
    print(f"Tập độ sâu xếp hạng: {len(cut)} câu (Single {sum(recs[q]['type'] == 'Single' for q in cut)}, "
          f"Multi {sum(recs[q]['type'] == 'Multi' for q in cut)})\n")

    lvl = lambda x: "cao" if x and x <= HIGH else "giữa" if x and x <= LOW else "thấp"  # noqa: E731
    cats = collections.Counter()
    rows, dist = [], []
    print("1. Chunk đáp án bị cắt (hạng RRF cao nhất trong số bị cắt) — hạng/điểm từng bộ, đặc trưng")
    print("   loại | RRF | BM25 hạng/điểm | vector hạng/cos | nguồn | tok | idf_cov | ent_cov | ngày | trùng doc trên | "
          "chunk trên: số / token")
    for q in cut:
        r = recs[q]
        ents, qd = entities(q), q_date(q)
        miss = [g for g in gold[q] if g not in r["chunk_ids"]]
        g = min(miss, key=lambda c: r["ranked_ids"].index(c))
        f = feats(q, r, g, ents, qd)
        above = [c for c in r["ranked_ids"][: f["rrf"] - 1] if c not in gold[q]]
        fa = [feats(q, r, c, ents, qd) for c in above]
        a_tok = sum(x["tok"] for x in fa)
        bl, vl = lvl(f["bm25_rank"]), lvl(f["vec_rank"])
        cat = "C" if bl == "cao" and vl == "cao" else "A" if bl == "cao" else "B" if vl == "cao" else "D"
        cats[cat] += 1
        debt = sum(d.tok(c) for c in r["ranked_ids"][: f["rrf"]]) - d.BUDGET
        rows.append((q, r["type"], f, fa, debt, cat, ents, qd))
        ec = "—" if f["ent_cov"] is None else f"{f['ent_cov']:.2f}"
        dist += [(q, x) for x in fa]
        print(f"   {r['type'][:1]} {cat} | {f['rrf']:2d} | {str(f['bm25_rank']):>4s}/{f['bm25']:5.1f} | "
              f"{str(f['vec_rank']):>4s}/{f['vec']:.3f} | {f['src']:6s} | {f['tok']:4d} | {f['idf_cov']:.2f} | "
              f"{ec:>4s} | "
              f"{'—' if f['date'] is None else int(f['date'])} | {'có' if f['same_doc_above'] else '—'} | "
              f"{len(fa)} / {a_tok} · nợ {debt}")

    print("\n2. Phân nhóm (cao = hạng ≤ 5, chốt trước): " + " · ".join(f"{k} {v}" for k, v in sorted(cats.items())))
    gb = [x[2]["bm25_rank"] for x in rows]
    gv = [x[2]["vec_rank"] for x in rows]
    print(f"   hạng BM25 của chunk đáp án: {sorted(y if y else 99 for y in gb)}  (99 = không có trong top-30)")
    print(f"   hạng vector của chunk đáp án: {sorted(y if y else 99 for y in gv)}")
    print(f"   nguồn chunk đáp án: {dict(collections.Counter(x[2]['src'] for x in rows))}")

    # ---- 3. đặc trưng chunk chiếm chỗ
    print(f"\n3. {len(dist)} chunk không phải đáp án đứng trên chunk đáp án bị cắt — so với chính chunk đáp án của câu đó")
    comp = collections.Counter()
    for q, g_f, fa in [(x[0], x[2], x[3]) for x in rows]:
        for f in fa:
            comp["tổng"] += 1
            comp["nguồn: cả hai"] += f["src"] == "both"
            comp["nguồn: chỉ một bộ, trong khi đáp án ở cả hai"] += f["src"] != "both" and g_f["src"] == "both"
            comp["dài ≥ 800 token"] += f["tok"] >= 800
            comp["idf_cov cao hơn đáp án"] += f["idf_cov"] > g_f["idf_cov"]
            comp["idf_cov thấp hơn đáp án"] += f["idf_cov"] < g_f["idf_cov"]
            if f["ent_cov"] is not None:
                comp["(có thực thể) ent_cov = 1"] += f["ent_cov"] == 1
                comp["(có thực thể) ent_cov thấp hơn đáp án"] += f["ent_cov"] < g_f["ent_cov"]
            if f["date"] is not None:
                comp["(có ngày) sai ngày"] += f["date"] == 0
            comp["BM25 cao hơn đáp án"] += f["bm25"] > g_f["bm25"]
            comp["cosine cao hơn đáp án"] += f["vec"] > g_f["vec"]
            comp["cùng tài liệu với một chunk cao hơn"] += f["same_doc_above"]
            comp["gần trùng chunk cao hơn (J ≥ 0,6)"] += f["max_jacc_above"] >= 0.6
    n = comp.pop("tổng")
    for k, v in comp.most_common():
        print(f"   {k:48s} {v:4d} ({100 * v / n:.0f}%)")

    # ---- 4. tín hiệu: độ phủ trên 20 ca + rủi ro câu đang tốt
    SIG = {
        "S1 đồng thuận hai bộ": lambda q, r, c, e, qd: 1.0 if c in r["vector_ids"] and c in r["bm25_ids"] else 0.0,
        "S2 độ phủ idf từ câu hỏi": lambda q, r, c, e, qd: idf_cov(q, c),
        "S3 độ phủ thực thể": lambda q, r, c, e, qd: ent_cov(q, c, e),
        "S4 khớp ngày nêu rõ": lambda q, r, c, e, qd: date_match(qd, c),
        "S5 chunk ngắn (−token)": lambda q, r, c, e, qd: -float(d.tok(c)),
        "S6 không cùng tài liệu với chunk cao hơn": lambda q, r, c, e, qd: 0.0 if any(
            d.CHUNKS[a]["full_doc_id"] == d.CHUNKS[c]["full_doc_id"] for a in r["ranked_ids"][: r["ranked_ids"].index(c)]) else 1.0,
        "S7 chỉ điểm BM25": lambda q, r, c, e, qd: bm25_score(q, c),
        "S8 chỉ cosine vector": lambda q, r, c, e, qd: vs[q][c],
        # nhắm nhóm A: hạng tốt nhất ở MỘT bộ bất kỳ — bỏ phần thưởng "có mặt ở cả hai danh sách" của RRF
        "S9 hạng tốt nhất ở một bộ (−min hạng)": lambda q, r, c, e, qd: -float(min(
            r["bm25_ids"].index(c) + 1 if c in r["bm25_ids"] else 99,
            r["vector_ids"].index(c) + 1 if c in r["vector_ids"] else 99)),
    }

    def rescuable(q, r, sig, targets, e, qd):
        """Mọi chunk đáp án bị cắt đều cứu được: chunk không phải đáp án đứng trên và kém hơn hẳn đủ trả nợ token."""
        for g in targets:
            sg = sig(q, r, g, e, qd)
            if sg is None:
                return False
            i = r["ranked_ids"].index(g)
            debt = sum(d.tok(c) for c in r["ranked_ids"][: i + 1]) - d.BUDGET
            worse = [c for c in r["ranked_ids"][:i] if c not in gold[q] and (sig(q, r, c, e, qd) is not None)
                     and sig(q, r, c, e, qd) < sg]
            if sum(d.tok(c) for c in worse) < debt:
                return False
        return True

    def at_risk(q, r, sig, e, qd):
        """Câu đang đủ đáp án: có chunk đáp án bị đẩy ra nếu các chunk không phải đáp án đứng dưới, tốt hơn hẳn, được đưa lên."""
        for g in gold[q]:
            sg = sig(q, r, g, e, qd)
            if sg is None:
                continue
            i = r["ranked_ids"].index(g)
            slack = d.BUDGET - sum(d.tok(c) for c in r["ranked_ids"][: i + 1])
            better = [c for c in r["ranked_ids"][i + 1:] if c not in gold[q] and sig(q, r, c, e, qd) is not None
                      and sig(q, r, c, e, qd) > sg]
            if sum(d.tok(c) for c in better) > slack:
                return True
        return False

    good = [q for q, r in recs.items() if q in gold and all(g in r["chunk_ids"] for g in gold[q])]
    print(f"\n4. Tín hiệu — điều kiện cần để cứu (20 ca) và rủi ro đẩy đáp án ra ở {len(good)} câu đang đủ đáp án")
    print(f"   {'tín hiệu':42s} | cứu được (S / M) | câu tốt có rủi ro (S / M) | câu có tín hiệu")
    table = {}
    for name, sig in SIG.items():
        res = []
        for q, typ, f, fa, debt, cat, e, qd in rows:
            miss = [g for g in gold[q] if g not in recs[q]["chunk_ids"]]
            res.append((typ, rescuable(q, recs[q], sig, miss, e, qd)))
        risk = [(recs[q]["type"], at_risk(q, recs[q], sig, entities(q), q_date(q))) for q in good]
        applic = sum(1 for x in rows if sig(x[0], recs[x[0]], gold[x[0]][0], x[6], x[7]) is not None)
        rs = sum(ok for t, ok in res if t == "Single"); rm = sum(ok for t, ok in res if t == "Multi")
        ks = sum(ok for t, ok in risk if t == "Single"); km = sum(ok for t, ok in risk if t == "Multi")
        table[name] = (rs + rm, ks + km, rm, km)
        print(f"   {name:42s} | {rs + rm:2d}/20 ({rs} / {rm}) | {ks + km:3d}/{len(good)} ({ks} / {km}) | {applic}/20")

    # ---- 5. Null
    nul = [q for q, r in recs.items() if r["type"] == "Null"]
    MISLEAD = {"L002": "20260112_10:00", "L055": "20261113_13:00", "L052": "20260214_16:00"}
    print(f"\n5. An toàn Null — {len(nul)} câu dev")
    print("   (a) câu Null mà tín hiệu sẽ kéo được chunk ngoài Sources vào (chunk ngoài, tốt hơn hẳn chunk trong, đủ token)")
    print("   (b) chunk được kéo vào có độ phủ thực thể = 1 và idf_cov ≥ trung vị Sources B2 của câu đó (dạng 'sự thật gần giống')")
    print("   (c) chunk gây nhầm đã xác định (L002, L055, L052): tỉ lệ ứng viên có tín hiệu tốt hơn hẳn nó (0,00 = nó đứng đầu hoặc đồng hạng đầu)")
    for name, sig in SIG.items():
        a = b = 0
        pct = []
        for q in nul:
            r = recs[q]; e, qd = entities(q), q_date(q)
            kept, out = r["chunk_ids"], [c for c in r["ranked_ids"] if c not in r["chunk_ids"]]
            vals_k = [sig(q, r, c, e, qd) for c in kept]
            vals_k = [v for v in vals_k if v is not None]
            if not vals_k:
                continue
            worst_k = min(vals_k)
            pulled = [c for c in out if sig(q, r, c, e, qd) is not None and sig(q, r, c, e, qd) > worst_k]
            freed = sum(d.tok(c) for c in kept if sig(q, r, c, e, qd) is not None and sig(q, r, c, e, qd) <= worst_k)
            if pulled and freed >= min(d.tok(c) for c in pulled):
                a += 1
                med_idf = st.median(idf_cov(q, c) for c in kept)
                b += any((ent_cov(q, c, e) in (1, 1.0) or e == []) and idf_cov(q, c) >= med_idf for c in pulled)
            lid = sheet.get(q)
            if lid in MISLEAD:
                target = next((c for c in r["ranked_ids"] if (d.ctime(c) or "") == MISLEAD[lid]), None)
                if target:
                    vals = [sig(q, r, c, e, qd) for c in r["ranked_ids"]]
                    vals = [v for v in vals if v is not None]
                    tv = sig(q, r, target, e, qd)
                    if tv is not None:
                        pct.append(f"{lid} {sum(v > tv for v in vals) / len(vals):.2f}")
        print(f"   {name:42s} | (a) {a:2d}/20 | (b) {b:2d}/20 | (c) {' · '.join(pct) or '—'}")
    json.dump({"cut": [{"q": x[0], "type": x[1], "gold": x[2], "cat": x[5]} for x in rows]},
              open(os.path.join(ROOT, "logs", "retrieval_audit", "ranking_depth.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__":
    main()
