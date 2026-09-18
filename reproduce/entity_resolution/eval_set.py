"""Chot tap cau hoi dung cho chi so E1 -- KHONG phai code danh gia truy hoi.

E1 do tren tap 180 cau dev CO EVIDENCE, khong phai toan bo 200 cau dev. 20 cau Null khong co
nhan evidence nen khong the tinh "full-evidence retention"; neu lo lot vao mau so, moi ti le
deu sai. Module nay chi lam mot viec: nap tap do va CHAN NGANG neu thanh phan khong dung.

    .venv/Scripts/python.exe reproduce/entity_resolution/eval_set.py

Nguon du lieu (dung lai cua sang loc, chi doc):
    logs/devset.csv             -- 200 cau dev dong bang (seed 13)
    logs/diag_path2chunk.jsonl  -- nhan chunk dap an ('gold') tung cau

Chunk id giu nguyen sau merge (CHECK9/CHECK10 cua merge_entities.py), nen nhan gold dung lai
duoc cho ca hai index.
"""

import csv
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

DEVSET_CSV = os.path.join(ROOT, "logs", "devset.csv")
GOLD_JSONL = os.path.join(ROOT, "logs", "diag_path2chunk.jsonl")

# Dang ky truoc 17/09/2026: thanh phan BAT BUOC cua tap do E1.
EXPECTED_TOTAL = 180
EXPECTED_BY_TYPE = {"Single": 159, "Multi": 21, "Null": 0}
EXPECTED_DEV_TOTAL = 200


def dev_rows(path=DEVSET_CSV):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    if len(rows) != EXPECTED_DEV_TOTAL or len({r["Question"] for r in rows}) != EXPECTED_DEV_TOTAL:
        raise SystemExit(f"devset.csv phai co dung {EXPECTED_DEV_TOTAL} cau khac nhau, "
                         f"dang co {len(rows)} dong / {len({r['Question'] for r in rows})} cau")
    return rows


def gold_map(path=GOLD_JSONL):
    gold = {}
    for line in open(path, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            if r.get("gold"):
                gold[r["question"]] = r["gold"]
    return gold


def evidence_rows(strict=True):
    """Tra ve (rows, gold). rows = cac cau dev CO evidence, da kiem thanh phan."""
    rows = dev_rows()
    gold = gold_map()
    ev = [r for r in rows if r["Question"] in gold]
    by_type = Counter(r["Type"] for r in ev)
    observed = {t: by_type.get(t, 0) for t in EXPECTED_BY_TYPE}

    if strict:
        problems = []
        if len(ev) != EXPECTED_TOTAL:
            problems.append(f"tong = {len(ev)}, phai la {EXPECTED_TOTAL}")
        for t, n in EXPECTED_BY_TYPE.items():
            if observed[t] != n:
                problems.append(f"{t} = {observed[t]}, phai la {n}")
        extra = set(by_type) - set(EXPECTED_BY_TYPE)
        if extra:
            problems.append(f"loai cau la: {sorted(extra)}")
        outside = set(gold) - {r["Question"] for r in rows}
        if outside:
            problems.append(f"{len(outside)} cau co gold nhung khong nam trong dev 200")
        if problems:
            raise SystemExit("TAP DO E1 SAI THANH PHAN:\n  - " + "\n  - ".join(problems))

    return ev, gold


def main():
    ev, gold = evidence_rows(strict=True)
    by_type = Counter(r["Type"] for r in ev)
    print(f"devset.csv            : {EXPECTED_DEV_TOTAL} cau")
    print(f"tap do E1 (co evidence): {len(ev)} cau")
    for t in ("Single", "Multi", "Null"):
        print(f"  {t:7s}: {by_type.get(t, 0)}")
    n_gold = sum(len(gold[r['Question']]) for r in ev)
    print(f"tong chunk dap an     : {n_gold} "
          f"(trung binh {n_gold / len(ev):.2f} chunk/cau)")
    print("STATUS: PASS -- thanh phan dung dang ky truoc (180 = 159 Single + 21 Multi + 0 Null)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
