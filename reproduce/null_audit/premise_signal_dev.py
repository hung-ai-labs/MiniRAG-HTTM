"""Khả thi 'độ phủ tiền đề câu hỏi' — CHỈ dev 200 (thăm dò, chưa đăng ký). Nhãn Type chỉ dùng để đo."""
import csv, json, re, sys
sys.path.insert(0, ".")
from minirag.bm25 import STOP
dev = list(csv.DictReader(open("logs/devset.csv", encoding="utf-8")))
def jl(p):
    d = {}
    for l in open(p, encoding="utf-8"):
        if l.strip():
            r = json.loads(l); d[r["question"]] = r
    return d
fz, b2 = jl("logs/screening/frozen/v3.jsonl"), jl("logs/screening/b2/answers.jsonl")
chunks = {k: v["content"].lower() for k, v in json.load(open("LiHua-World-qwen-modal/kv_store_text_chunks.json", encoding="utf-8")).items()}
tok = lambda s: [w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in STOP and len(w) >= 3]
def signals(q, ids):
    Q = sorted(set(tok(q)))
    if not Q: return 1.0, 1.0
    sets = [set(re.findall(r"[a-z0-9]+", chunks.get(i, ""))) for i in ids]
    union = set().union(*sets) if sets else set()
    return sum(t in union for t in Q) / len(Q), max((sum(t in s for t in Q) / len(Q) for s in sets), default=0.0)
def auc(pos, neg):   # xác suất một câu Null có độ phủ THẤP hơn một câu có đáp án
    return (sum((p < n) + 0.5 * (p == n) for p in pos for n in neg)) / (len(pos) * len(neg))
for name, src in (("V3", lambda q: fz[q]), ("B2", lambda q: b2.get(q) or fz[q])):
    rows = []
    for r in dev:
        rec = src(r["Question"]); u, b = signals(r["Question"], rec["chunk_ids"])
        rows.append((r["Type"], u, b, rec["verdict"]))
    for k, lab in ((1, "phủ hợp (union Sources)"), (2, "phủ trong 1 chunk tốt nhất")):
        pos = [x[k] for x in rows if x[0] == "Null"]; neg = [x[k] for x in rows if x[0] != "Null"]
        # oracle lạc quan: ngưỡng chọn bằng nhãn; câu Null bị từ chối coi như được chấm đúng
        best = (0, None, 0, 0)
        for th in sorted({x[k] for x in rows}):
            flag = [x for x in rows if x[k] <= th]
            rescued = sum(1 for x in flag if x[0] == "Null" and x[3] != "accurate")
            blocked = sum(1 for x in flag if x[0] != "Null" and x[3] == "accurate")
            if rescued - blocked > best[0]: best = (rescued - blocked, th, rescued, blocked)
        med = lambda xs: sorted(xs)[len(xs) // 2]
        print(f"{name} · {lab}: trung vị Null {med(pos):.2f} / có đáp án {med(neg):.2f} · AUC {auc(pos, neg):.3f} · "
              f"Null sai của {name}: {sum(1 for x in rows if x[0]=='Null' and x[3]!='accurate')}/20 · "
              f"net oracle tốt nhất {best[0]:+d} (ngưỡng {best[1]}, cứu {best[2]}, chặn nhầm {best[3]})")
