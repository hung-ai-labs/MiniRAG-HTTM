"""CE1 — đánh giá offline việc xếp lại bằng cross-encoder (Phase 3–5). Không sinh, không chấm, không sửa minirag/.

    .venv/bin/python reproduce/rerank/ce_eval.py | tee logs/rerank/ce_eval.txt

Luật dừng và mọi định nghĩa chốt trong reproduce/rerank/preregistration/CE1_cross_encoder_pretrained.md TRƯỚC khi chạy.
Evidence và đáp án vàng CHỈ dùng để đánh giá — điểm cross-encoder tính từ (câu hỏi, nội dung chunk) trong ce_score.py.
"""
import collections, csv, json, math, os, re, statistics as st, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "reproduce", "retrieval_audit"))
import diagnose as d  # noqa: E402
import ranking_depth as rd  # noqa: E402

SC = json.load(open(os.path.join(ROOT, "logs", "rerank", "ce1_scores.json"), encoding="utf-8"))
MISLEAD = {"L002": "20260112_10:00", "L055": "20261113_13:00", "L052": "20260214_16:00"}


def order(r, policy="maxp"):
    """Xếp lại ĐÚNG tập ứng viên B2 theo điểm cross-encoder; hoà điểm giữ thứ tự RRF (ổn định, tất định)."""
    s = SC["scores"][r["question"]][policy]
    return sorted(r["ranked_ids"], key=lambda c: (-s.get(c, -1e9), r["ranked_ids"].index(c)))


def mcnemar(b, c):
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n)


def norm(s):
    return " ".join(re.findall(r"[a-z0-9]+", s.lower()))


def main():
    recs = {r["question"]: r for r in (json.loads(l) for l in open(d.CTX, encoding="utf-8")) if not r.get("none")}
    gold = d.gold_map()
    answers = {r["Question"]: r["Gold Answer"] for r in csv.DictReader(
        open(os.path.join(ROOT, "dataset", "LiHua-World", "qa", "query_set.csv"), encoding="utf-8"))}
    new = {q: d.a1(order(r)) for q, r in recs.items()}
    newf = {q: d.a1(order(r, "firstp")) for q, r in recs.items()}
    rank_b = {q: {c: i + 1 for i, c in enumerate(r["ranked_ids"])} for q, r in recs.items()}
    rank_a = {q: {c: i + 1 for i, c in enumerate(order(r))} for q, r in recs.items()}

    print(f"CE1 · {SC['model']} @ {SC['revision'][:12]} · {SC['device']} lô {SC['batch']} · {SC['policy']}")
    print(f"{SC['n_windows']} cửa sổ · {SC['infer_sec']}s = {SC['infer_sec'] / len(recs):.2f} s/câu ({1000 * SC['infer_sec'] / len(recs):.0f} mili giây) — p50/p95 xem ce_latency.txt\n")
    # kiểm toàn vẹn: xếp lại KHÔNG được đổi tập ứng viên
    assert all(set(order(r)) == set(r["ranked_ids"]) for r in recs.values()), "tập ứng viên đã đổi!"
    assert all(sum(d.tok(c) for c in v) <= d.BUDGET for v in new.values()), "vượt 4000 token!"
    print("Kiểm: tập ứng viên không đổi 200/200 · không câu nào vượt 4.000 token · recall ứng viên không đổi theo định nghĩa\n")

    # ---------------------------------------------------------------- Phase 3: 20 ca độ sâu xếp hạng
    cut = []
    for q, r in recs.items():
        if q not in gold or not all(g in r["ranked_ids"] for g in gold[q]):
            continue
        if not [g for g in gold[q] if g not in r["chunk_ids"]] or r["ranked_ids"][len(r["chunk_ids"])] in gold[q]:
            continue
        cut.append(q)
    print(f"=== PHASE 3 — {len(cut)} ca độ sâu xếp hạng "
          f"(Single {sum(recs[q]['type'] == 'Single' for q in cut)}, Multi {sum(recs[q]['type'] == 'Multi' for q in cut)})")
    print("   loại | hạng đáp án B2 → CE | vào Sources B2 → CE | đủ bằng chứng B2 → CE | nhóm | câu hỏi")
    cats = collections.Counter()
    for q in cut:
        r = recs[q]
        miss = [g for g in gold[q] if g not in r["chunk_ids"]]
        g = min(miss, key=lambda c: rank_b[q][c])
        rb, ra = rank_b[q][g], rank_a[q][g]
        inb, ina = g in r["chunk_ids"], g in new[q]
        fb, fa = all(x in r["chunk_ids"] for x in gold[q]), all(x in new[q] for x in gold[q])
        cat = "A" if ina else ("D" if ra > rb else "B" if ra < rb else "C")
        cats[cat] += 1
        print(f"   {recs[q]['type'][:1]} {cat} | {rb:2d} → {ra:2d} | {'—' if not inb else 'có'} → {'có' if ina else '—'} | "
              f"{'có' if fb else '—'} → {'có' if fa else '—'} | {q[:62]}")
    print(f"\n   Nhóm: " + " · ".join(f"{k} {cats[k]}" for k in "ABCD") +
          f"  (A = vào được context; B = lên hạng nhưng chưa vào; C = không đổi; D = tệ đi)")
    print(f"   FirstP (số đối chiếu, không đổi quyết định): A = "
          f"{sum(1 for q in cut for g in [min([x for x in gold[q] if x not in recs[q]['chunk_ids']], key=lambda c: rank_b[q][c])] if g in newf[q])}")

    # chunk chiếm chỗ bị đẩy xuống / kéo lên trong 20 ca
    dn = up = tot = 0
    for q in cut:
        r = recs[q]
        for c in r["ranked_ids"]:
            if c in gold[q]:
                continue
            tot += 1
            dn += rank_a[q][c] > rank_b[q][c]
            up += rank_a[q][c] < rank_b[q][c]
    print(f"   Chunk không phải đáp án trong 20 ca: {tot} · bị đẩy xuống {dn} · được kéo lên {up}")

    # ---------------------------------------------------------------- Phase 5: toàn dev
    ev = [q for q in recs if q in gold]
    extr = [q for q in ev if len(norm(answers[q])) >= 3
            and any(norm(answers[q]) in norm(d.CHUNKS[g]["content"]) for g in gold[q])]

    def full(q, ids):
        return all(g in ids for g in gold[q])

    def verb(q, ids):
        return norm(answers[q]) in norm(" ".join(d.CHUNKS[c]["content"] for c in ids))

    print("\n=== PHASE 5 — toàn dev, giữ bằng chứng B2 → CE")
    for label, pop, fn in (("đủ chunk đáp án", ev, full), ("đáp án nguyên văn trong Sources", extr, verb)):
        b0 = sum(fn(q, recs[q]["chunk_ids"]) for q in pop)
        b1 = sum(fn(q, new[q]) for q in pop)
        u = sum(fn(q, new[q]) and not fn(q, recs[q]["chunk_ids"]) for q in pop)
        w = sum(fn(q, recs[q]["chunk_ids"]) and not fn(q, new[q]) for q in pop)
        print(f"   {label:32s} {b0}/{len(pop)} → {b1}/{len(pop)} · {u} lên / {w} xuống · net {u - w:+d} · p = {mcnemar(u, w):.3g}")
        for t in ("Single", "Multi"):
            pt = [q for q in pop if recs[q]["type"] == t]
            u2 = sum(fn(q, new[q]) and not fn(q, recs[q]["chunk_ids"]) for q in pt)
            w2 = sum(fn(q, recs[q]["chunk_ids"]) and not fn(q, new[q]) for q in pt)
            print(f"      {t:6s} {sum(fn(q, recs[q]['chunk_ids']) for q in pt)}/{len(pt)} → "
                  f"{sum(fn(q, new[q]) for q in pt)}/{len(pt)} · {u2} lên / {w2} xuống · net {u2 - w2:+d}")
    lost = [q for q in ev if full(q, recs[q]["chunk_ids"]) and not full(q, new[q])]
    print(f"   Câu ĐANG TỐT mất bằng chứng: {len(lost)}" + ("" if not lost else ""))
    for q in lost:
        print(f"      [{recs[q]['type']}] {q[:88]}")
    inc = [q for q in ev if any(g in rank_b[q] for g in gold[q])]  # 4/207 chunk đáp án không có trong ứng viên
    first_b = [min(rank_b[q][g] for g in gold[q] if g in rank_b[q]) for q in inc]
    first_a = [min(rank_a[q][g] for g in gold[q] if g in rank_a[q]) for q in inc]
    print(f"   Hạng chunk đáp án đầu tiên: trung vị {st.median(first_b)} → {st.median(first_a)} · "
          f"p90 {sorted(first_b)[int(.9 * len(inc))]} → {sorted(first_a)[int(.9 * len(inc))]}")
    tb = [sum(d.tok(c) for c in recs[q]["chunk_ids"]) for q in recs]
    ta = [sum(d.tok(c) for c in new[q]) for q in recs]
    nb = [len(recs[q]["chunk_ids"]) for q in recs]
    na = [len(new[q]) for q in recs]
    ch = sum(1 for q in recs if new[q] != recs[q]["chunk_ids"])
    print(f"   Token Sources trung vị {st.median(tb)} → {st.median(ta)} ({100 * (st.median(ta) / st.median(tb) - 1):+.1f}%) · "
          f"p90 {sorted(tb)[180]} → {sorted(ta)[180]} · max {max(ta)}")
    print(f"   Số chunk trong Sources trung vị {st.median(nb)} → {st.median(na)} · context đổi {ch}/{len(recs)} câu")

    # ---------------------------------------------------------------- Phase 4: an toàn Null
    nul = [q for q in recs if recs[q]["type"] == "Null"]
    print(f"\n=== PHASE 4 — an toàn Null ({len(nul)} câu)")
    ev_b = [len({d.ctime(c) or c for c in recs[q]["chunk_ids"]}) for q in nul]
    ev_a = [len({d.ctime(c) or c for c in new[q]}) for q in nul]
    print(f"   Sự kiện phân biệt (Time khác nhau) trung vị: {st.median(ev_b)} → {st.median(ev_a)} "
          f"({100 * (st.median(ev_a) / st.median(ev_b) - 1):+.0f}%)")
    changed = sum(1 for q in nul if new[q] != recs[q]["chunk_ids"])
    pulled_full, n_pull, n_drop = 0, 0, 0
    for q in nul:
        ents = rd.entities(q)
        pulled = [c for c in new[q] if c not in recs[q]["chunk_ids"]]
        n_pull += len(pulled)
        n_drop += len([c for c in recs[q]["chunk_ids"] if c not in new[q]])
        if any((rd.ent_cov(q, c, ents) or 0) == 1.0 for c in pulled):
            pulled_full += 1
    print(f"   Context đổi {changed}/{len(nul)} câu · chunk MỚI VÀO {n_pull} · chunk RỜI ĐI {n_drop}")
    print(f"   Câu Null có chunk mới vào KHỚP ĐỦ THỰC THỂ câu hỏi: {pulled_full}/{len(nul)} "
          f"(cổng 4: ≤ 7; tín hiệu tất định tốt nhất 15–16 → đã bị loại)")
    print(f"   Số chunk Sources trung vị: {st.median([len(recs[q]['chunk_ids']) for q in nul])} → "
          f"{st.median([len(new[q]) for q in nul])}")

    print("\n   Chunk gây nhầm đã xác định (kiểm toán Null 15/09):")
    sheet = {r["cau_hoi"]: r["id"] for r in csv.DictReader(
        open(os.path.join(ROOT, "logs", "null_audit", "d3_label_audit", "sheet_A.csv"), encoding="utf-8"))}
    for q in nul:
        lid = sheet.get(q)
        if lid not in MISLEAD:
            continue
        r = recs[q]
        tgt = next((c for c in r["ranked_ids"] if (d.ctime(c) or "") == MISLEAD[lid]), None)
        if tgt is None:
            print(f"      {lid}: không tìm thấy chunk {MISLEAD[lid]} trong ứng viên")
            continue
        rb, ra = rank_b[q][tgt], rank_a[q][tgt]
        print(f"      {lid} ({MISLEAD[lid]}): hạng {rb} → {ra} ({'LÊN' if ra < rb else 'xuống' if ra > rb else 'không đổi'})"
              f" · trong Sources {'có' if tgt in r['chunk_ids'] else '—'} → {'có' if tgt in new[q] else '—'}")

    # phân định: HỖ TRỢ hay chỉ LIÊN QUAN mạnh hơn
    print("\n=== PHÂN ĐỊNH — hỗ trợ hay chỉ liên quan mạnh hơn?")
    g_up = [rank_b[q][g] - rank_a[q][g] for q in ev for g in gold[q] if g in rank_b[q]]
    nd_up = [rank_b[q][c] - rank_a[q][c] for q in nul for c in recs[q]["ranked_ids"]
             if (rd.ent_cov(q, c, rd.entities(q)) or 0) == 1.0]
    print(f"   Chunk đáp án (câu trả lời được): mức lên hạng trung vị {st.median(g_up):+.1f} (n={len(g_up)})")
    print(f"   Chunk khớp đủ thực thể ở câu Null: mức lên hạng trung vị "
          f"{st.median(nd_up) if nd_up else float('nan'):+.1f} (n={len(nd_up)})")


    # ---------------------------------------------------------------- kiểm cách giải thích thay thế
    print("\n=== KIỂM GIẢ THIẾT THAY THẾ — có phải model chỉ thích chunk DÀI?")
    import numpy as np
    xs = [d.tok(c) for q, r in recs.items() for c in r["ranked_ids"]]
    ys = [SC["scores"][q]["maxp"][c] for q, r in recs.items() for c in r["ranked_ids"]]
    print(f"   Pearson(độ dài chunk, điểm CE) = {np.corrcoef(xs, ys)[0, 1]:+.3f} (n={len(xs)})")
    ent = [d.tok(c) for q in recs for c in new[q] if c not in recs[q]["chunk_ids"]]
    lef = [d.tok(c) for q in recs for c in recs[q]["chunk_ids"] if c not in new[q]]
    print(f"   chunk mới vào Sources trung vị {st.median(ent)} token (n={len(ent)}) · rời đi {st.median(lef)} (n={len(lef)})")

    print("\n=== PHÂN ĐỊNH (khống chế CẢ hạng xuất phát LẪN độ dài) — hỗ trợ hay chỉ liên quan mạnh hơn?")
    print("   Mức lên hạng trung bình. Chênh > 0 = model tách được chunk đáp án khỏi chunk cùng dài, cùng hạng xuất phát.")
    print("   độ dài | hạng xuất phát | đáp án (n, TB) | không đáp án (n, TB) | chênh")
    for lab, lo, hi in (("<400", 0, 400), ("400-799", 400, 800), ("≥800", 800, 10 ** 9)):
        for k, a, b in (("1-5", 1, 5), ("6-15", 6, 15), ("16-30", 16, 30), ("31+", 31, 999)):
            G, N = [], []
            for q in recs:
                for c in recs[q]["ranked_ids"]:
                    if not (lo <= d.tok(c) < hi) or not (a <= rank_b[q][c] <= b):
                        continue
                    (G if c in gold.get(q, []) else N).append(rank_b[q][c] - rank_a[q][c])
            if len(G) >= 3 and N:
                print(f"   {lab:>7s} | {k:>8s}       | {len(G):3d}, {st.mean(G):+5.1f}    | {len(N):5d}, {st.mean(N):+5.1f}       "
                      f"| {st.mean(G) - st.mean(N):+5.1f}")

    print("\n=== Precision@k (không bị hiệu ứng trần)")
    for k in (3, 5, 10):
        pb = st.mean([len(set(recs[q]["ranked_ids"][:k]) & set(gold[q])) / min(k, len(gold[q])) for q in ev])
        pa = st.mean([len(set(order(recs[q])[:k]) & set(gold[q])) / min(k, len(gold[q])) for q in ev])
        print(f"   chunk đáp án trong top-{k:2d} (câu có evidence): {pb:.3f} → {pa:.3f} ({100 * (pa / pb - 1):+.0f}%)")
    E = {q: rd.entities(q) for q in nul}
    for k in (3, 5, 10):
        fb = st.mean([sum((rd.ent_cov(q, c, E[q]) or 0) == 1.0 for c in recs[q]["ranked_ids"][:k]) / k for q in nul])
        fa = st.mean([sum((rd.ent_cov(q, c, E[q]) or 0) == 1.0 for c in order(recs[q])[:k]) / k for q in nul])
        print(f"   chunk khớp đủ thực thể trong top-{k:2d} (câu Null): {fb:.3f} → {fa:.3f} ({100 * (fa / fb - 1):+.0f}%)")

    json.dump({"cats": dict(cats), "cut": cut, "new": new, "lost": lost}, open(
        os.path.join(ROOT, "logs", "rerank", "ce1_eval.json"), "w", encoding="utf-8"), ensure_ascii=False)


if __name__ == "__main__":
    main()
