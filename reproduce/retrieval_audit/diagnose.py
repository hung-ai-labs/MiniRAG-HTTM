"""Giai đoạn 1 — chẩn đoán truy hồi của B2 trên dev 200, offline, không sinh, không chấm.

    .venv/bin/python reproduce/retrieval_audit/diagnose.py | tee logs/retrieval_audit/diagnose.txt

Evidence (logs/diag_path2chunk.jsonl) chỉ dùng để ĐÁNH GIÁ. Không có gì ở đây chạy lúc truy vấn.
"""
import collections, csv, json, os, re, statistics as st, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from minirag.utils import encode_string_by_tiktoken  # noqa: E402

CTX = os.path.join(ROOT, "logs", "retrieval_audit", "vector_bm25_dev_ctx.jsonl")
CHUNKS = json.load(open(os.path.join(ROOT, "LiHua-World-qwen-modal", "kv_store_text_chunks.json"), encoding="utf-8"))
BUDGET = 4000
TOK = {}


def tok(cid):
    if cid not in TOK:
        TOK[cid] = len(encode_string_by_tiktoken(CHUNKS[cid]["content"]))
    return TOK[cid]


def ctime(cid):
    m = re.search(r"Time:\s*(\S+)", CHUNKS[cid]["content"])
    return m.group(1) if m else None


def words(cid):
    return set(re.findall(r"[a-z0-9']+", CHUNKS[cid]["content"].lower()))


def speakers(cid):
    return set(re.findall(r"^\s*([A-Z][A-Za-z\-]+):", CHUNKS[cid]["content"], re.M))


def gold_map():
    g = {}
    for line in open(os.path.join(ROOT, "logs", "diag_path2chunk.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        if r.get("gold"):
            g[r["question"]] = r["gold"]
    return g


def a1(ids):
    t, out = 0, []
    for c in ids:
        t += tok(c)
        if t > BUDGET:
            break
        out.append(c)
    return out


def pct(a, b):
    return 100 * a / b if b else float("nan")


def main():
    recs = [json.loads(l) for l in open(CTX, encoding="utf-8")]
    gold = gold_map()
    rows = [r for r in recs if not r.get("none")]
    print(f"Dev 200 · B2 dựng lại offline · {len(rows)} câu có context · {sum(1 for r in rows if r['question'] in gold)} câu có evidence")

    # --- kiểm A1 tái dựng khớp log
    mism = sum(1 for r in rows if a1(r["ranked_ids"]) != r["chunk_ids"])
    print(f"Tái dựng A1 từ ranked_ids khớp chunk_ids đã log: {len(rows) - mism}/{len(rows)}\n")

    ev = [r for r in rows if r["question"] in gold]
    G = sum(len(gold[r["question"]]) for r in ev)
    cand = sum(g in r["ranked_ids"] for r in ev for g in gold[r["question"]])
    kept = sum(g in r["chunk_ids"] for r in ev for g in gold[r["question"]])
    full = [r for r in ev if all(g in r["chunk_ids"] for g in gold[r["question"]])]
    full_cand = [r for r in ev if all(g in r["ranked_ids"] for g in gold[r["question"]])]
    by = collections.defaultdict(lambda: [0, 0])
    for r in ev:
        by[r["type"]][0] += 1
        by[r["type"]][1] += all(g in r["chunk_ids"] for g in gold[r["question"]])
    first = [min(r["ranked_ids"].index(g) + 1 for g in gold[r["question"]] if g in r["ranked_ids"])
             for r in ev if any(g in r["ranked_ids"] for g in gold[r["question"]])]
    print("1–3. Recall và giữ lại (180 câu có evidence)")
    print(f"   chunk đáp án trong ứng viên (≤ 60 chunk trộn): {cand}/{G} = {pct(cand, G):.1f}%")
    print(f"   chunk đáp án còn sau A1@4000:                 {kept}/{G} = {pct(kept, G):.1f}%")
    print(f"   câu đủ mọi chunk đáp án — trong ứng viên {len(full_cand)}/{len(ev)} = {pct(len(full_cand), len(ev)):.1f}% · "
          f"sau A1 {len(full)}/{len(ev)} = {pct(len(full), len(ev)):.1f}%")
    for t, (n, k) in sorted(by.items()):
        print(f"      {t:6s} đủ đáp án sau A1 {k}/{n} = {pct(k, n):.1f}%")
    print(f"4. Hạng chunk đáp án đầu tiên trong danh sách trộn: trung vị {st.median(first)} · p75 "
          f"{sorted(first)[int(.75 * len(first))]} · p90 {sorted(first)[int(.9 * len(first))]}")

    nr = [len(r["ranked_ids"]) for r in rows]
    nk = [len(r["chunk_ids"]) for r in rows]
    stok = [r["sources_tok"] for r in rows]
    ktok = [tok(c) for r in rows for c in r["chunk_ids"]]
    print(f"5. Số chunk: ứng viên trung vị {st.median(nr)} · vào Sources trung vị {st.median(nk)} (min {min(nk)}, max {max(nk)})")
    print(f"6. Token Sources trung vị {st.median(stok)} · chunk dài trung vị {st.median(ktok)} token, p90 "
          f"{sorted(ktok)[int(.9 * len(ktok))]}, max {max(ktok)}")
    waste = [BUDGET - r["sources_tok"] for r in rows]
    print(f"   ngân sách bỏ trống do A1 dừng ở chunk đầu tiên tràn: trung vị {st.median(waste)} token")

    # --- trùng lặp
    dup_pairs, dup_q = 0, 0
    for r in rows:
        ids = r["chunk_ids"]
        ws = {c: words(c) for c in ids}
        n = 0
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = ws[ids[i]], ws[ids[j]]
                if a and b and len(a & b) / len(a | b) >= 0.6:
                    n += 1
        dup_pairs += n
        dup_q += n > 0
    print(f"7. Cặp chunk gần trùng (Jaccard từ ≥ 0,6) trong Sources: {dup_pairs} cặp, ở {dup_q}/{len(rows)} câu")

    # --- nguồn
    src = collections.Counter()
    gsrc = collections.Counter()
    for r in rows:
        v, b = set(r["vector_ids"]), set(r["bm25_ids"])
        for c in r["chunk_ids"]:
            src["cả hai" if c in v and c in b else "chỉ vector" if c in v else "chỉ BM25"] += 1
        for g in gold.get(r["question"], []):
            if g in r["ranked_ids"]:
                gsrc["cả hai" if g in v and g in b else "chỉ vector" if g in v else "chỉ BM25"] += 1
    tot = sum(src.values())
    print("8. Nguồn của chunk trong Sources: " + " · ".join(f"{k} {v} ({pct(v, tot):.0f}%)" for k, v in src.most_common()))
    gt = sum(gsrc.values())
    print("   Nguồn của chunk đáp án có trong ứng viên: " + " · ".join(f"{k} {v} ({pct(v, gt):.0f}%)" for k, v in gsrc.most_common()))

    # --- bị chiếm chỗ
    disp = [r for r in ev if any(g in r["ranked_ids"] and g not in r["chunk_ids"] for g in gold[r["question"]])]
    print(f"9. Câu có chunk đáp án tìm được nhưng bị A1 cắt: {len(disp)}/{len(ev)}")

    # --- phân loại thất bại chính cho câu KHÔNG đủ đáp án sau A1
    print("\nPHÂN LOẠI THẤT BẠI — câu không đủ chunk đáp án sau A1 (phân loại tự động theo proxy, không đọc nghĩa)")
    fails = [r for r in ev if r not in full]
    cat = collections.Counter()
    sub = collections.Counter()
    detail = []
    for r in fails:
        q, gs = r["question"], gold[r["question"]]
        v, b = set(r["vector_ids"]), set(r["bm25_ids"])
        missing = [g for g in gs if g not in r["chunk_ids"]]
        if any(g not in r["ranked_ids"] for g in missing):
            cat["chunk đáp án không có trong ứng viên"] += 1
            detail.append((q, "never", r["type"]))
            continue
        cat["tìm được nhưng bị A1 cắt"] += 1
        # chunk chiếm chỗ: chunk không phải đáp án đứng trước chunk đáp án đầu tiên bị cắt
        g0 = min(r["ranked_ids"].index(g) for g in missing)
        ahead = [c for c in r["ranked_ids"][:g0] if c not in gs]
        gsp = set().union(*[speakers(g) for g in gs])
        gtimes = {ctime(g) for g in gs}
        kinds = collections.Counter()
        for c in ahead:
            kinds["chỉ BM25" if c in b and c not in v else "chỉ vector" if c in v and c not in b else "cả hai"] += 1
            if speakers(c) & gsp and ctime(c) not in gtimes:
                kinds["cùng người nói, khác thời điểm"] += 1
            if ctime(c) is None:
                kinds["chunk nối tiếp (không có Time)"] += 1
        for k, n in kinds.items():
            sub[k] += n
        need = sum(tok(c) for c in r["ranked_ids"][: g0 + 1])
        detail.append((q, f"cut rank {g0 + 1} need {need} tok", r["type"]))
    for k, n in cat.most_common():
        print(f"   {k:40s} {n:3d} câu ({pct(n, len(fails)):.0f}%)")
    tot_ahead = sum(v for k, v in sub.items() if k in ("chỉ BM25", "chỉ vector", "cả hai"))
    print(f"   Chunk không phải đáp án đứng trước chunk đáp án bị cắt: {tot_ahead}")
    for k, n in sub.most_common():
        print(f"      {k:36s} {n:4d} ({pct(n, tot_ahead):.0f}%)")
    by_t = collections.Counter((d[2], d[1] == "never") for d in detail)
    print("   Theo loại câu: " + " · ".join(f"{t} {'không trong ứng viên' if nv else 'bị cắt'} {n}"
                                           for (t, nv), n in sorted(by_t.items())))
    json.dump({"fails": detail}, open(os.path.join(ROOT, "logs", "retrieval_audit", "fail_list.json"), "w",
                                      encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
