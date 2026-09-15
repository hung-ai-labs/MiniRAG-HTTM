"""Tập câu tầng D: 435 câu phân biệt ngoài dev, theo thứ tự query_set.csv (dòng lặp văn bản chỉ giữ lần đầu).

    .venv/bin/python reproduce/stage_d/make_nondev435.py
"""
import csv, os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
dev = {r["Question"] for r in csv.DictReader(open(os.path.join(ROOT, "logs", "devset.csv"), encoding="utf-8"))}
rows, seen = [], set()
for r in csv.DictReader(open(os.path.join(ROOT, "dataset", "LiHua-World", "qa", "query_set.csv"), encoding="utf-8")):
    if r["Question"] not in dev and r["Question"] not in seen:
        seen.add(r["Question"])
        rows.append(r)
assert len(rows) == 435, len(rows)
out = os.path.join(ROOT, "reproduce", "stage_d", "nondev435.csv")
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["Question", "Gold Answer", "Evidence", "Type"], lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
print(f"{out}: {len(rows)} câu ·", {t: sum(r['Type'] == t for r in rows) for t in ('Single', 'Multi', 'Null')})
