"""Dựng dữ liệu cho trang UI so sánh truy hồi (một file JSON nhúng thẳng vào HTML).

    .venv/bin/python reproduce/demo/make_ui.py

Ra: logs/demo/du_lieu.json  — dùng bởi reproduce/demo/ui.html
Đọc hoàn toàn từ log đã lưu. Không gọi LLM.
"""
import collections, csv, json, os, re, statistics as st, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "logs", "demo", "du_lieu.json")
MAXCHARS = 2600            # cắt phần hiển thị của chunk cho nhẹ trang
BUDGET = 4000


def main():
    chunks = json.load(open(os.path.join(ROOT, "LiHua-World-qwen-modal", "kv_store_text_chunks.json"),
                            encoding="utf-8"))
    meta = {r["Question"]: r for r in csv.DictReader(
        open(os.path.join(ROOT, "dataset", "LiHua-World", "qa", "query_set.csv"), encoding="utf-8"))}
    dev = [r["Question"] for r in csv.DictReader(open(os.path.join(ROOT, "logs", "devset.csv"), encoding="utf-8"))]

    def ctx(p):
        return {r["question"]: r for r in (json.loads(l) for l in open(os.path.join(ROOT, p), encoding="utf-8"))}

    goc = ctx("logs/retrieval_audit/goc_dev_ctx.jsonl")
    b2c = ctx("logs/retrieval_audit/vector_bm25_dev_ctx.jsonl")
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

    def ctime(cid):
        m = re.search(r"Time:\s*(\S+)", chunks[cid]["content"])
        return m.group(1) if m else ""

    def arm(rec, g, answer, verdict):
        if rec is None or rec.get("none"):
            return {"none": True, "answer": answer, "verdict": verdict}
        cand, src = rec["ranked_ids"], rec["chunk_ids"]
        return {"none": False, "cand": len(cand), "src": src,
                "tok": rec.get("sources_tok") or 0,
                "ranks": [{"c": x, "r": (cand.index(x) + 1 if x in cand else None), "in": x in src} for x in g],
                "answer": answer, "verdict": verdict}

    used, qs = set(), []
    for i, q in enumerate(dev, 1):
        g = gold.get(q, [])
        a = arm(goc.get(q), g, ans.get(q), vd.get(q))
        b = arm(b2c.get(q), g, b2a.get(q, {}).get("answer"), b2a.get(q, {}).get("verdict"))
        used |= set(g) | set(a.get("src") or []) | set(b.get("src") or [])
        qs.append({"i": i, "q": q, "type": meta[q]["Type"], "gold_ans": meta[q]["Gold Answer"],
                   "gold": g, "base": a, "b2": b})

    # thống kê tổng hợp — chỉ câu có Evidence
    ev = [x for x in qs if x["gold"]]
    agg = {}
    for key in ("base", "b2"):
        found = kept = tot = fc = fs = 0
        prec, ranks, nsrc, ncand = [], [], [], []
        for x in ev:
            a = x[key]
            tot += len(x["gold"])
            if a["none"]:
                continue
            found += sum(1 for r in a["ranks"] if r["r"])
            hit = sum(1 for r in a["ranks"] if r["in"])
            kept += hit
            fc += all(r["r"] for r in a["ranks"])
            fs += hit == len(x["gold"])
            prec.append(hit / len(a["src"]) if a["src"] else 0)
            ranks += [r["r"] for r in a["ranks"] if r["r"]]
            nsrc.append(len(a["src"]))
            ncand.append(a["cand"])
        agg[key] = {"found": 100 * found / tot, "kept": 100 * kept / tot,
                    "full_cand": 100 * fc / len(ev), "full_src": 100 * fs / len(ev),
                    "prec": 100 * st.mean(prec), "rank": st.median(ranks),
                    "ncand": st.median(ncand), "nsrc": st.median(nsrc), "n": len(ev)}

    data = {"agg": agg, "budget": BUDGET,
            # U+FFFD có sẵn trong corpus gốc (1 chunk, một byte hỏng) — bỏ khi hiển thị
            "chunks": {c: {"t": ctime(c), "x": chunks[c]["content"][:MAXCHARS].replace("\ufffd", ""),
                           "cut": len(chunks[c]["content"]) > MAXCHARS} for c in sorted(used)},
            "questions": qs}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    # nhúng thẳng vào HTML để có MỘT file mở được offline, không cần server
    tpl = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_template.html"),
               encoding="utf-8").read()
    html = os.path.join(ROOT, "logs", "demo", "ui.html")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    open(html, "w", encoding="utf-8").write(
        "<!doctype html>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\">\n"
        + tpl.replace("/*__DATA__*/", payload))
    print(f"{OUT}  ({os.path.getsize(OUT) / 1e6:.2f} MB) · {len(qs)} câu · {len(used)} chunk")
    print(f"{html}  ({os.path.getsize(html) / 1e6:.2f} MB)  ← mở file này bằng trình duyệt")
    print(f"   truy hồi: giữ được {agg['base']['kept']:.1f}% → {agg['b2']['kept']:.1f}%")


if __name__ == "__main__":
    main()
