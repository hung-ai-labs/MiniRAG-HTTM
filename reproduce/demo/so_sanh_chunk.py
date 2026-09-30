"""Demo đối chiếu truy hồi: hỏi một câu → xem CHUNK CẦN LẤY trong tài liệu, rồi xem hai bên lấy được gì.

    .venv/bin/python reproduce/demo/so_sanh_chunk.py            # chế độ hỏi đáp
    .venv/bin/python reproduce/demo/so_sanh_chunk.py --acc      # bảng % độ chính xác truy hồi (toàn tập)
    .venv/bin/python reproduce/demo/so_sanh_chunk.py --list win # câu B2 sửa được lỗi của bản gốc
    .venv/bin/python reproduce/demo/so_sanh_chunk.py --q 7      # mở thẳng câu số 7

Mỗi câu hiển thị cho CẢ HAI bên:
  · số chunk ứng viên được xếp hạng
  · số chunk thực sự đưa vào Sources (sau khi cắt 4.000 token)
  · THỨ HẠNG của từng chunk cần lấy trong danh sách xếp hạng
  · tỉ lệ lấy đúng của câu đó

Đọc hoàn toàn từ log đã lưu — KHÔNG gọi LLM, không tốn quota. Phạm vi: 200 câu dev set đã đóng băng.
Cột Evidence chỉ dùng để CHẤM ĐIỂM màn demo; hệ thống lúc chạy không hề đọc nó.
"""
import argparse, collections, csv, json, os, re, statistics as st, sys, textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHUNKS = json.load(open(os.path.join(ROOT, "LiHua-World-qwen-modal", "kv_store_text_chunks.json"), encoding="utf-8"))
GOC = os.path.join(ROOT, "logs", "retrieval_audit", "goc_dev_ctx.jsonl")
B2C = os.path.join(ROOT, "logs", "retrieval_audit", "vector_bm25_dev_ctx.jsonl")
BUDGET = 4000

C = {"đ": "\033[92m", "s": "\033[91m", "v": "\033[93m", "m": "\033[96m", "x": "\033[0m", "b": "\033[1m", "d": "\033[2m"}
if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
    C = dict.fromkeys(C, "")


def ctime(cid):
    m = re.search(r"Time:\s*(\S+)", CHUNKS[cid]["content"])
    return m.group(1) if m else "—"


def line1(cid, n=62):
    for l in CHUNKS[cid]["content"].split("\n"):
        l = l.strip()
        if l and not l.startswith("Time:"):
            return (l[:n] + "…") if len(l) > n else l
    return ""


def load():
    meta = {r["Question"]: r for r in csv.DictReader(
        open(os.path.join(ROOT, "dataset", "LiHua-World", "qa", "query_set.csv"), encoding="utf-8"))}
    dev = [r["Question"] for r in csv.DictReader(open(os.path.join(ROOT, "logs", "devset.csv"), encoding="utf-8"))]

    def ctx(path, how):
        if not os.path.exists(path):
            sys.exit(f"thiếu {path}\n  dựng lại bằng: {how}")
        return {r["question"]: r for r in (json.loads(l) for l in open(path, encoding="utf-8"))}

    goc = ctx(GOC, 'reproduce/retrieval_audit/run_offline.sh dump_contexts.py --fusion "" --tag goc')
    b2 = ctx(B2C, "reproduce/retrieval_audit/run_offline.sh dump_contexts.py --fusion vector_bm25")
    ans = {r["Question"]: r["minirag"] for r in csv.DictReader(
        open(os.path.join(ROOT, "logs", "qwen637_fix.csv"), encoding="utf-8"))}
    vd = collections.defaultdict(list)
    for r in csv.DictReader(open(os.path.join(ROOT, "logs", "qwen637_fix_judged.csv"), encoding="utf-8")):
        vd[r["question"]].append(r["verdict"])
    vd = {q: collections.Counter(v).most_common(1)[0][0] for q, v in vd.items()}
    b2a = {}
    for l in open(os.path.join(ROOT, "logs", "screening", "b2", "answers.jsonl"), encoding="utf-8"):
        x = json.loads(l)
        b2a.setdefault(x["question"], {}).update(x)
    gold = {}
    for line in open(os.path.join(ROOT, "logs", "diag_path2chunk.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        if r.get("gold"):
            gold[r["question"]] = r["gold"]
    return dev, meta, goc, b2, ans, vd, b2a, gold


def stats(rec, gold_ids):
    """Số ứng viên, số chunk vào Sources, thứ hạng từng chunk cần lấy, tỉ lệ lấy đúng."""
    if rec is None or rec.get("none"):
        return {"none": True, "n_cand": 0, "n_src": 0, "tok": 0, "ranks": [], "hit": 0, "n_gold": len(gold_ids)}
    cand, src = rec["ranked_ids"], rec["chunk_ids"]
    ranks = []
    for g in gold_ids:
        r = cand.index(g) + 1 if g in cand else None
        ranks.append({"cid": g, "rank": r, "in_src": g in src})
    return {"none": False, "n_cand": len(cand), "n_src": len(src),
            "tok": rec.get("sources_tok") or sum(len(CHUNKS[c]["content"]) // 4 for c in src),
            "ranks": ranks, "hit": sum(1 for x in ranks if x["in_src"]), "n_gold": len(gold_ids)}


def mark(v):
    return {"accurate": f"{C['đ']}ĐÚNG{C['x']}", "error": f"{C['s']}SAI{C['x']}",
            "neither": f"{C['v']}KHÔNG BIẾT{C['x']}"}.get(v, str(v))


def side(title, s, rec, gold_ids, answer, verdict):
    print(f"\n{C['b']}{title}{C['x']}")
    if s["none"]:
        print(f"   {C['d']}(đồ thị không ra node/cạnh → không có context){C['x']}")
    else:
        print(f"   Ứng viên được xếp hạng : {C['b']}{s['n_cand']:2d}{C['x']} chunk")
        print(f"   Đưa vào Sources        : {C['b']}{s['n_src']:2d}{C['x']} chunk  ({s['tok']} token, trần {BUDGET})")
        if s["n_gold"]:
            pct = 100 * s["hit"] / s["n_gold"]
            col = C["đ"] if s["hit"] == s["n_gold"] else (C["v"] if s["hit"] else C["s"])
            print(f"   Lấy đúng chunk cần lấy : {col}{s['hit']}/{s['n_gold']} = {pct:.0f}%{C['x']}")
            for x in s["ranks"]:
                if x["rank"] is None:
                    where = f"{C['s']}không có trong ứng viên{C['x']}"
                elif x["in_src"]:
                    where = f"hạng {C['đ']}#{x['rank']}{C['x']} → {C['đ']}✓ vào Sources{C['x']}"
                else:
                    where = f"hạng {C['v']}#{x['rank']}{C['x']} → {C['s']}✗ bị cắt khỏi Sources{C['x']}"
                print(f"      · [{ctime(x['cid']):>16s}] {where}")
        print(f"   {C['d']}Sources (thứ tự xếp hạng):{C['x']}")
        for i, cid in enumerate(rec["chunk_ids"][:10], 1):
            st_ = f"{C['đ']}★{C['x']}" if cid in gold_ids else " "
            print(f"    {st_} {i:2d}. [{ctime(cid):>16s}] {line1(cid)}")
        if len(rec["chunk_ids"]) > 10:
            print(f"       {C['d']}… còn {len(rec['chunk_ids']) - 10} chunk{C['x']}")
    print(f"   {C['m']}Trả lời :{C['x']} {textwrap.shorten(str(answer or '(trống)'), 190)}")
    print(f"   {C['m']}Giám khảo:{C['x']} {mark(verdict)}")


def show(i, q, meta, goc, b2, ans, vd, b2a, gold):
    m = meta[q]
    g = gold.get(q, [])
    print("\n" + "=" * 102)
    print(f"{C['b']}[{i}] {q}{C['x']}")
    print(f"   Loại: {m['Type']} · Đáp án vàng: {C['b']}{m['Gold Answer']}{C['x']}")
    print(f"\n   {C['m']}📌 CHUNK CẦN LẤY trong tài liệu (cột Evidence — chỉ dùng để chấm demo):"
          f" {len(g)} chunk{C['x']}")
    for cid in g:
        print(f"      ★ [{ctime(cid):>16s}] {line1(cid, 68)}")
    if not g:
        print(f"      {C['d']}(câu Null — đáp án đúng là \"không đủ thông tin\", không có chunk nào cần lấy){C['x']}")
    print("=" * 102)
    sg, sb = stats(goc.get(q), g), stats(b2.get(q), g)
    side("── ❶ MiniRAG GỐC  (xếp hạng bằng đường đi đồ thị) ──", sg, goc.get(q), g, ans.get(q), vd.get(q))
    side("── ❷ B2 — BẢN CỦA NHÓM  (RRF: vector + BM25) ──", sb, b2.get(q), g,
         b2a.get(q, {}).get("answer"), b2a.get(q, {}).get("verdict"))
    if g:
        print(f"\n   {C['b']}→ Truy hồi: gốc {sg['hit']}/{sg['n_gold']} ({100 * sg['hit'] / sg['n_gold']:.0f}%)"
              f"   so với   B2 {sb['hit']}/{sb['n_gold']} ({100 * sb['hit'] / sb['n_gold']:.0f}%){C['x']}")
    a, b = vd.get(q), b2a.get(q, {}).get("verdict")
    if a != b:
        tag = (f"{C['đ']}B2 SỬA ĐƯỢC{C['x']}" if b == "accurate"
               else f"{C['s']}B2 LÀM HỎNG{C['x']}" if a == "accurate" else "đổi, cả hai đều chưa đúng")
        print(f"   {C['b']}→ Câu trả lời: {tag}{C['x']}  ({a} → {b})")
    else:
        print(f"   {C['b']}→ Câu trả lời: hai bên cùng {mark(a)}{C['x']}")


def accuracy(dev, meta, goc, b2, gold):
    """Bảng % độ chính xác truy hồi trên toàn tập — con số để đưa vào slide."""
    ev = [q for q in dev if q in gold and gold[q]]
    rows = {"MiniRAG gốc": goc, "B2 (của nhóm)": b2}
    out = {}
    for name, ctx in rows.items():
        cand_hit = kept = tot = full_cand = full_src = 0
        precision, ranks, nsrc, ncand = [], [], [], []
        for q in ev:
            s = stats(ctx.get(q), gold[q])
            if s["none"]:
                tot += len(gold[q])
                continue
            tot += s["n_gold"]
            cand_hit += sum(1 for x in s["ranks"] if x["rank"])
            kept += s["hit"]
            full_cand += all(x["rank"] for x in s["ranks"])
            full_src += s["hit"] == s["n_gold"]
            precision.append(s["hit"] / s["n_src"] if s["n_src"] else 0)
            ranks += [x["rank"] for x in s["ranks"] if x["rank"]]
            nsrc.append(s["n_src"])
            ncand.append(s["n_cand"])
        out[name] = {"cand": 100 * cand_hit / tot, "kept": 100 * kept / tot,
                     "full_cand": 100 * full_cand / len(ev), "full_src": 100 * full_src / len(ev),
                     "prec": 100 * st.mean(precision), "rank": st.median(ranks),
                     "nsrc": st.median(nsrc), "ncand": st.median(ncand)}
    print(f"\n{C['b']}ĐỘ CHÍNH XÁC TRUY HỒI — {len(ev)} câu dev có Evidence{C['x']}")
    print(f"(chunk cần lấy = chunk chứa bằng chứng thật; hệ thống lúc chạy KHÔNG đọc nhãn này)\n")
    g, b = out["MiniRAG gốc"], out["B2 (của nhóm)"]
    rowspec = [
        ("Chunk cần lấy TÌM RA được (trong ứng viên)", "cand", "%"),
        ("Chunk cần lấy GIỮ ĐƯỢC (vào Sources)", "kept", "%"),
        ("Câu lấy ĐỦ mọi chunk cần — trong ứng viên", "full_cand", "%"),
        ("Câu lấy ĐỦ mọi chunk cần — sau khi cắt", "full_src", "%"),
        ("Độ chính xác Sources (chunk đúng / chunk lấy)", "prec", "%"),
        ("Hạng trung vị của chunk cần lấy", "rank", ""),
        ("Số chunk ứng viên, trung vị", "ncand", ""),
        ("Số chunk vào Sources, trung vị", "nsrc", ""),
    ]
    print(f"   {'Chỉ số':46s} | {'gốc':>8s} | {'B2':>8s} | {'chênh':>8s}")
    print("   " + "-" * 80)
    for label, key, unit in rowspec:
        d = b[key] - g[key]
        col = C["đ"] if (d > 0) == (key not in ("rank", "ncand", "nsrc")) and d != 0 else (C["s"] if d else "")
        fmt = "{:7.1f}" + unit if unit else "{:7.1f} "
        print(f"   {label:46s} | {fmt.format(g[key]):>8s} | {fmt.format(b[key]):>8s} | "
              f"{col}{d:+7.1f}{C['x']}")
    print(f"\n   {C['b']}Đọc hai dòng đầu:{C['x']} bản gốc chỉ giữ được {g['kept']:.1f}% chunk chứa bằng chứng,")
    print(f"   B2 giữ được {C['đ']}{b['kept']:.1f}%{C['x']} — cùng ngân sách {BUDGET} token, cùng model sinh.")
    print(f"\n   {C['d']}⚠ Truy hồi tốt hơn KHÔNG tự động thành accuracy tốt hơn ở nhóm Null:")
    print(f"   Null acc 73,33 → 57,78. Xem docs/CAI_TIEN_VA_BENCHMARK.md mục 5.{C['x']}")


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--acc", action="store_true", help="bảng % độ chính xác truy hồi toàn tập")
    ap.add_argument("--list", nargs="?", const="all", choices=["all", "win", "lose", "null", "multi"])
    ap.add_argument("--q", type=int)
    a = ap.parse_args()
    dev, meta, goc, b2, ans, vd, b2a, gold = load()

    def cat(q):
        x, y = vd.get(q), b2a.get(q, {}).get("verdict")
        return "same" if x == y else ("win" if y == "accurate" else "lose" if x == "accurate" else "same")

    def listing(f="all"):
        print(f"\n{'#':>4s} | {'loại':6s} | {'lấy đúng chunk':14s} | {'gốc':9s} | {'B2':9s} | câu hỏi")
        print("-" * 104)
        for i, q in enumerate(dev, 1):
            c, t = cat(q), meta[q]["Type"]
            if (f == "win" and c != "win") or (f == "lose" and c != "lose"):
                continue
            if (f == "null" and t != "Null") or (f == "multi" and t != "Multi"):
                continue
            g = gold.get(q, [])
            sg, sb = stats(goc.get(q), g), stats(b2.get(q), g)
            ret = f"{sg['hit']}/{sg['n_gold']} → {sb['hit']}/{sb['n_gold']}" if g else "— (Null)"
            tag = {"win": C["đ"] + "sửa " + C["x"], "lose": C["s"] + "hỏng" + C["x"]}.get(c, "    ")
            print(f"{i:4d} | {t:6s} | {ret:14s} | {str(vd.get(q)):9s} | "
                  f"{str(b2a.get(q, {}).get('verdict')):9s} | {tag} {q[:48]}")
        n = collections.Counter(cat(q) for q in dev)
        print(f"\nDev 200: B2 sửa được {C['đ']}{n['win']}{C['x']} câu · làm hỏng {C['s']}{n['lose']}{C['x']} câu · "
              f"giữ nguyên {n['same']}")

    if a.acc:
        accuracy(dev, meta, goc, b2, gold)
        return
    if a.list:
        listing(a.list)
        return
    if a.q:
        show(a.q, dev[a.q - 1], meta, goc, b2, ans, vd, b2a, gold)
        return

    print(f"{C['b']}SO SÁNH TRUY HỒI: MiniRAG gốc  ⟷  B2 (bản của nhóm){C['x']}")
    print(f"{len(dev)} câu dev · đọc từ log đã lưu, không gọi LLM\n")
    accuracy(dev, meta, goc, b2, gold)
    print(f"\n{C['b']}Lệnh:{C['x']} số câu 1–{len(dev)} · từ khoá để tìm · "
          f"{C['b']}acc{C['x']} bảng % · {C['b']}win{C['x']}/{C['b']}lose{C['x']}/{C['b']}null{C['x']}/"
          f"{C['b']}multi{C['x']}/{C['b']}all{C['x']} lọc · {C['b']}q{C['x']} thoát")
    while True:
        try:
            s = input(f"\n{C['b']}>{C['x']} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if s in ("q", "quit", "exit"):
            return
        if s == "acc":
            accuracy(dev, meta, goc, b2, gold)
        elif s in ("all", "win", "lose", "null", "multi"):
            listing(s)
        elif s.isdigit() and 1 <= int(s) <= len(dev):
            show(int(s), dev[int(s) - 1], meta, goc, b2, ans, vd, b2a, gold)
        elif s:
            hits = [(i, q) for i, q in enumerate(dev, 1) if s.lower() in q.lower()]
            if not hits:
                print("   không có câu nào chứa từ khoá đó")
            elif len(hits) == 1:
                show(hits[0][0], hits[0][1], meta, goc, b2, ans, vd, b2a, gold)
            else:
                for i, q in hits[:20]:
                    print(f"   {i:4d} | {meta[q]['Type']:6s} | {q[:78]}")


if __name__ == "__main__":
    main()
