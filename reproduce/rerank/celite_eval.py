"""CE-lite — đánh giá XÁC NHẬN cho luật đã chốt trong CE4. Offline: không sinh, không chấm.

    .venv/bin/python reproduce/rerank/celite_eval.py | tee logs/rerank/celite_eval.txt

Luật đã chốt (CE4): xếp lại bằng CE1 chỉ 25 ứng viên đầu theo RRF; phần còn lại giữ thứ tự RRF và nằm sau;
rồi A1@4000 như cũ. Điểm từng cặp (câu hỏi, chunk) không phụ thuộc chunk nào khác được chấm, nên dùng lại
điểm CE1 đã lưu là CHÍNH XÁC. Độ trễ thì phải ĐO THẬT trên đúng tiền tố 25.

Evidence và đáp án vàng chỉ dùng để đánh giá.
"""
import collections, csv, json, math, os, re, statistics as st, sys, time

import torch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "reproduce", "retrieval_audit"))
sys.path.insert(0, HERE)
import diagnose as d  # noqa: E402
import ranking_depth as rd  # noqa: E402
from ce_score import BATCH, CHUNKS, DEVICE, load_model, windows  # noqa: E402

N_PREFIX = 25
SC = json.load(open(os.path.join(ROOT, "logs", "rerank", "ce1_scores.json"), encoding="utf-8"))["scores"]
ON = os.path.join(ROOT, "logs", "retrieval_audit", "ce1_on_dev_ctx.jsonl")
MISLEAD = {"L002": "20260112_10:00", "L055": "20261113_13:00", "L052": "20260214_16:00"}
WARMUP = 5


def ce1_order(r):
    s, ids = SC[r["question"]]["maxp"], r["ranked_ids"]
    pos = {c: i for i, c in enumerate(ids)}
    return sorted(ids, key=lambda c: (-s[c], pos[c]))


def celite_order(r):
    s, ids = SC[r["question"]]["maxp"], r["ranked_ids"]
    head, tail = ids[:N_PREFIX], ids[N_PREFIX:]
    pos = {c: i for i, c in enumerate(head)}
    return sorted(head, key=lambda c: (-s[c], pos[c])) + tail


def mcnemar(b, c):
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n)


def norm(s):
    return " ".join(re.findall(r"[a-z0-9]+", s.lower()))


def measure_latency(recs):
    """Đo thật độ trễ khi chỉ chấm 25 ứng viên đầu — cùng model, cùng lô, cùng MaxP, cùng CPU."""
    tok, model, _ = load_model()
    chunks = json.load(open(CHUNKS, encoding="utf-8"))
    cache, per_q, n_win = {}, [], []
    for n, r in enumerate(recs):
        q_ids = tok(r["question"], add_special_tokens=False)["input_ids"]
        items = windows(r["ranked_ids"][:N_PREFIX], len(q_ids), tok, chunks, cache)
        t = time.perf_counter()
        for i in range(0, len(items), BATCH):
            b = items[i:i + BATCH]
            enc = tok.pad({"input_ids": [[tok.cls_token_id] + q_ids + [tok.sep_token_id] + p + [tok.sep_token_id]
                                         for _, _, p in b],
                           "token_type_ids": [[0] * (len(q_ids) + 2) + [1] * (len(p) + 1) for _, _, p in b]},
                          return_tensors="pt")
            with torch.no_grad():
                model(**{k: v.to(DEVICE) for k, v in enc.items()}).logits.squeeze(-1).float().cpu()
        if n >= WARMUP:
            per_q.append(1000 * (time.perf_counter() - t))
            n_win.append(len(items))
    return per_q, n_win


def main():
    recs = {r["question"]: r for r in (json.loads(l) for l in open(d.CTX, encoding="utf-8")) if not r.get("none")}
    on = {r["question"]: r for r in (json.loads(l) for l in open(ON, encoding="utf-8")) if not r.get("none")}
    gold = d.gold_map()
    answers = {r["Question"]: r["Gold Answer"] for r in csv.DictReader(
        open(os.path.join(ROOT, "dataset", "LiHua-World", "qa", "query_set.csv"), encoding="utf-8"))}
    refs = json.load(open(os.path.join(ROOT, "logs", "rerank", "ce1_refs.json"), encoding="utf-8"))
    cut, resc1 = refs["cut"], set(refs["rescued"])

    S = {"B2": {q: r["chunk_ids"] for q, r in recs.items()},
         "CE1": {q: d.a1(ce1_order(r)) for q, r in recs.items()},
         "CE-lite": {q: d.a1(celite_order(r)) for q, r in recs.items()}}
    assert all(S["CE1"][q] == on[q]["chunk_ids"] for q in on), "CE1 dựng lại lệch bản đã ghi"
    print(f"CE-lite · tiền tố {N_PREFIX} theo RRF · model/MaxP/lô giống hệt CE1")
    print(f"Kiểm: CE1 dựng lại từ điểm đã lưu khớp context runtime đã ghi {len(on)}/{len(on)} câu\n")

    # ---------------------------------------------------------------- PHASE 2A
    print("=== PHASE 2A — chi phí")
    per_q, n_win = measure_latency(list(recs.values()))
    p = lambda x, q: sorted(x)[min(len(x) - 1, int(q * len(x)))]  # noqa: E731
    full_c = st.mean([len(r["ranked_ids"]) for r in recs.values()])
    lite_c = st.mean([min(N_PREFIX, len(r["ranked_ids"])) for r in recs.values()])
    ce1_ms = sorted(r["rerank_ms"] for r in on.values() if r.get("rerank_ms") is not None)
    print(f"   ứng viên xếp lại/câu: CE1 {full_c:.1f} → CE-lite {lite_c:.1f} ({100 * lite_c / full_c:.0f}%)")
    print(f"   cửa sổ MaxP/câu:      CE1 93,6 → CE-lite {st.mean(n_win):.1f} ({100 * st.mean(n_win) / 93.6:.0f}%)")
    print(f"   ước tính tuyến tính từ CE1: max {max(ce1_ms) * st.mean(n_win) / 93.6:.0f} ms")
    print(f"   ĐO THẬT (CPU, bỏ {WARMUP} câu khởi động, n={len(per_q)}): p50 {p(per_q, .5):.0f} · "
          f"p95 {p(per_q, .95):.0f} · max {max(per_q):.0f} ms · vượt 3000: {sum(1 for x in per_q if x > 3000)}")
    print(f"   CE1 để đối chiếu: p50 {p(ce1_ms, .5):.0f} · p95 {p(ce1_ms, .95):.0f} · max {max(ce1_ms):.0f} ms")

    # 11 ca CE1 cứu
    keep = [q for q in resc1 if all(g in S["CE-lite"][q] for g in gold[q])]
    extra = [q for q in cut if q not in resc1 and all(g in S["CE-lite"][q] for g in gold[q])]
    print(f"\n   Trong 11 ca CE1 cứu được, CE-lite còn cứu: {len(keep)}/11" +
          (f" · thêm {len(extra)} ca CE1 không cứu được" if extra else ""))

    # ---------------------------------------------------------------- bảng chính
    ev = [q for q in recs if q in gold]
    extr = [q for q in ev if len(norm(answers[q])) >= 3
            and any(norm(answers[q]) in norm(d.CHUNKS[g]["content"]) for g in gold[q])]
    nul = [q for q in recs if recs[q]["type"] == "Null"]

    def full(q, v):
        return all(g in S[v][q] for g in gold[q])

    def verb(q, v):
        return norm(answers[q]) in norm(" ".join(d.CHUNKS[c]["content"] for c in S[v][q]))

    print("\n=== BẢNG CHÍNH — B2 vs CE1 đầy đủ vs CE-lite")
    print(f"   {'Chỉ số':44s} | {'B2':>9s} | {'CE1':>9s} | {'CE-lite':>9s}")
    def row(name, f):
        print(f"   {name:44s} | {f('B2'):>9s} | {f('CE1'):>9s} | {f('CE-lite'):>9s}")
    row("đủ bằng chứng (180 câu có evidence)", lambda v: f"{sum(full(q, v) for q in ev)}/180")
    row("đáp án nguyên văn trong Sources (94)", lambda v: f"{sum(verb(q, v) for q in extr)}/94")
    row("trong 20 ca độ sâu: đủ bằng chứng", lambda v: f"{sum(full(q, v) for q in cut)}/20")
    row("Single đủ bằng chứng", lambda v: f"{sum(full(q, v) for q in ev if recs[q]['type'] == 'Single')}/159")
    row("Multi đủ bằng chứng", lambda v: f"{sum(full(q, v) for q in ev if recs[q]['type'] == 'Multi')}/21")
    row("token Sources trung vị", lambda v: f"{st.median([sum(d.tok(c) for c in S[v][q]) for q in recs]):.0f}")
    row("số chunk Sources trung vị", lambda v: f"{st.median([len(S[v][q]) for q in recs]):.0f}")
    row("sự kiện phân biệt Null, trung vị", lambda v: f"{st.median([len({d.ctime(c) or c for c in S[v][q]}) for q in nul]):.1f}")
    row("xếp lại ms/câu (p50)", lambda v: "0" if v == "B2" else (f"{p(ce1_ms, .5):.0f}" if v == "CE1" else f"{p(per_q, .5):.0f}"))
    row("xếp lại ms/câu (max)", lambda v: "0" if v == "B2" else (f"{max(ce1_ms):.0f}" if v == "CE1" else f"{max(per_q):.0f}"))

    print("\n=== Chuyển dịch giữ bằng chứng")
    for a, b in (("B2", "CE-lite"), ("CE1", "CE-lite")):
        for label, pop, fn in (("đủ bằng chứng", ev, full), ("đáp án nguyên văn", extr, verb)):
            u = sum(fn(q, b) and not fn(q, a) for q in pop)
            w = sum(fn(q, a) and not fn(q, b) for q in pop)
            print(f"   {b} so với {a:8s} · {label:18s}: {u} mất→giữ / {w} giữ→mất · net {u - w:+d} · p = {mcnemar(u, w):.3g}")
            for t in ("Single", "Multi"):
                pt = [q for q in pop if recs[q]["type"] == t]
                u2 = sum(fn(q, b) and not fn(q, a) for q in pt)
                w2 = sum(fn(q, a) and not fn(q, b) for q in pt)
                print(f"      {t:6s} {u2} lên / {w2} xuống · net {u2 - w2:+d}")

    # ---------------------------------------------------------------- PHASE 2B
    print("\n=== PHASE 2B — an toàn Null (bắt buộc)")
    E = {q: rd.entities(q) for q in nul}
    for v in ("CE1", "CE-lite"):
        pulled = sum(len([c for c in S[v][q] if c not in S["B2"][q]]) for q in nul)
        drop = sum(len([c for c in S["B2"][q] if c not in S[v][q]]) for q in nul)
        full_ent = sum(1 for q in nul if any((rd.ent_cov(q, c, E[q]) or 0) == 1.0
                                             for c in S[v][q] if c not in S["B2"][q]))
        print(f"   {v:8s}: chunk mới vào {pulled} · rời đi {drop} · câu có chunk mới khớp đủ thực thể "
              f"{full_ent}/20 (cổng ≤ 7)")
    # so trực tiếp CE-lite với CE1
    pull_vs = sum(1 for q in nul if any((rd.ent_cov(q, c, E[q]) or 0) == 1.0
                                        for c in S["CE-lite"][q] if c not in S["CE1"][q]))
    print(f"   CE-lite kéo thêm chunk khớp đủ thực thể mà CE1 KHÔNG có: {pull_vs}/20 câu")

    print("\n   Ba chunk gây nhầm đã biết (luật CE2: THOÁI LUI chỉ khi bị đẩy lên so với B2)")
    sheet = {r["cau_hoi"]: r["id"] for r in csv.DictReader(
        open(os.path.join(ROOT, "logs", "null_audit", "d3_label_audit", "sheet_A.csv"), encoding="utf-8"))}
    reg = 0
    for q in nul:
        lid = sheet.get(q)
        if lid not in MISLEAD:
            continue
        r = recs[q]
        tgt = next((c for c in r["ranked_ids"] if (d.ctime(c) or "") == MISLEAD[lid]), None)
        if tgt is None:
            continue
        rb = r["ranked_ids"].index(tgt) + 1
        r1 = ce1_order(r).index(tgt) + 1
        rl = celite_order(r).index(tgt) + 1
        v = "THOÁI LUI" if rl < rb else "CẢI THIỆN" if rl > rb else "TRUNG TÍNH"
        reg += v == "THOÁI LUI"
        print(f"      {lid}: B2 {rb} → CE1 {r1} → CE-lite {rl} · Sources CE-lite "
              f"{'có' if tgt in S['CE-lite'][q] else '—'} · {v}")
    print(f"      → THOÁI LUI {reg}/3 (cổng ≤ 1)")


if __name__ == "__main__":
    main()
