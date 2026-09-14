"""Chốt canary 100 câu cho quy trình sàng lọc theo tầng (ROADMAP, sửa đổi đăng ký trước BM25, 14/09).

Toàn bộ 21 Multi + 20 Null + 59 Single rút ngẫu nhiên từ dev 200, seed 20260914, xếp ba lô phân tầng
40 / 40 / 20. qid = chỉ số dòng (0-based) đầu tiên của câu hỏi trong dataset/LiHua-World/qa/query_set.csv.
KHÔNG chạy lại để đổi thành phần sau khi đã sinh câu trả lời canary.

    python reproduce/screening/make_canary.py
"""
import collections, csv, hashlib, os, random

SEED = 20260914
PLAN = {1: (24, 8, 8), 2: (24, 8, 8), 3: (11, 5, 4)}   # (Single, Multi, Null) mỗi lô
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "canary100.csv")

qs = list(csv.DictReader(open("dataset/LiHua-World/qa/query_set.csv", encoding="utf-8")))
first = {}
for i, r in enumerate(qs):
    first.setdefault(r["Question"], i)
dev = list(csv.DictReader(open("logs/devset.csv", encoding="utf-8")))
assert len(dev) == 200 and all(r["Question"] in first for r in dev)

by = collections.defaultdict(list)
for r in dev:
    by[r["Type"]].append(r)
for t in by:
    by[t].sort(key=lambda r: first[r["Question"]])    # thứ tự ổn định trước khi rút
rng = random.Random(SEED)
single = rng.sample(by["Single"], 59)
multi, null = list(by["Multi"]), list(by["Null"])
assert len(multi) == 21 and len(null) == 20
for lst in (single, multi, null):
    rng.shuffle(lst)

rows, pos = [], {"S": 0, "M": 0, "N": 0}
for batch, (ns, nm, nn) in PLAN.items():
    part = ([("S", x) for x in single[pos["S"]:pos["S"] + ns]]
            + [("M", x) for x in multi[pos["M"]:pos["M"] + nm]]
            + [("N", x) for x in null[pos["N"]:pos["N"] + nn]])
    pos["S"] += ns; pos["M"] += nm; pos["N"] += nn
    rng.shuffle(part)
    rows += [(batch, r) for _, r in part]
assert len(rows) == 100 and pos == {"S": 59, "M": 21, "N": 20}

with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["order", "batch", "qid", "Type", "Question", "Gold Answer", "Evidence"])
    for i, (b, r) in enumerate(rows, 1):
        w.writerow([i, b, first[r["Question"]], r["Type"], r["Question"], r["Gold Answer"], r["Evidence"]])

comp = collections.Counter((b, r["Type"]) for b, r in rows)
print("canary:", OUT)
for b in PLAN:
    print(f"  lô {b}: " + ", ".join(f"{t} {comp[(b, t)]}" for t in ("Single", "Multi", "Null")))
print("sha256:", hashlib.sha256(open(OUT, "rb").read()).hexdigest())
