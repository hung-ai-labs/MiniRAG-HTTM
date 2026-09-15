"""Mô phỏng cắt context theo độ phủ trên dev 200, đếm theo phán quyết thật (một lượt, seed sàng lọc). Cận trên lạc quan: giả định
câu Null sai bị cắt context sẽ chuyển thành đúng; câu đúng mất đủ bằng chứng giả định chuyển thành sai."""
import csv, json, re, sys
sys.path.insert(0, ".")
from minirag.bm25 import STOP
dev = list(csv.DictReader(open("logs/devset.csv", encoding="utf-8")))
gold = {}
for l in open("logs/diag_path2chunk.jsonl", encoding="utf-8"):
    if l.strip():
        r = json.loads(l)
        if r.get("gold"): gold[r["question"]] = set(r["gold"])
def jl(p):
    d = {}
    for l in open(p, encoding="utf-8"):
        if l.strip():
            r = json.loads(l); d[r["question"]] = r
    return d
fz, b2 = jl("logs/screening/frozen/v3.jsonl"), jl("logs/screening/b2/answers.jsonl")
words = {k: set(re.findall(r"[a-z0-9]+", v["content"].lower()))
         for k, v in json.load(open("LiHua-World-qwen-modal/kv_store_text_chunks.json", encoding="utf-8")).items()}
tok = lambda s: {w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in STOP and len(w) >= 3}
for name, src in (("V3", lambda q: fz[q]), ("B2", lambda q: b2.get(q) or fz[q])):
    print(f"{name} (dev 200, phán quyết một lượt):")
    print("  ngưỡng | N | Null sai bị gắn cờ (có thể cứu) | câu đúng bị gắn cờ | câu đúng mất đủ bằng chứng (có thể mất) | net lạc quan")
    for th in (0.3, 0.4, 0.5):
        for N in (2, 4):
            save = lose = flag_ok = 0
            for r in dev:
                q = r["Question"]; rec = src(q); ids = rec["chunk_ids"]; Q = tok(q)
                cov = {i: len(Q & words.get(i, set())) / max(1, len(Q)) for i in ids}
                if max(cov.values(), default=0.0) > th:
                    continue
                if r["Type"] == "Null":
                    save += rec["verdict"] != "accurate"
                elif rec["verdict"] == "accurate":
                    flag_ok += 1
                    if q in gold and gold[q] <= set(ids):
                        kept = sorted(ids, key=lambda i: (-cov[i], ids.index(i)))[:N]
                        lose += not gold[q] <= set(kept)
            print(f"  ≤ {th:.1f}  | {N} | {save:2d}                              | {flag_ok:3d}               | {lose:2d}                                     | {save - lose:+d}")
