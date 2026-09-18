"""Chấm điểm ba lượt bật công tắc P1 / P2 trên dev 200, đặt cạnh ba lượt V3 chính thức.

    .venv/bin/python reproduce/path/score_qa_switches.py | tee logs/path_qa/ket_qua.txt

Chỉ dùng cho thăm dò trên dev — không thay số chính thức, không đụng cổng tầng D.
"""
import collections
import csv
import os
import statistics as st

DEV = "logs/devset.csv"
LABELS = ("accurate", "error", "neither")
BASE = {"V3 lượt 1": "logs/qwen637_v3_judged.csv",
        "V3 lượt 2": "logs/qwen637_v3_r2_judged.csv",
        "V3 lượt 3": "logs/qwen637_v3_r3_judged.csv"}
NEW = {"V3 + P1 (cắt tỉa)": "logs/path_qa/v3_p1_judged.csv",
       "V3 + P2 (trọng số)": "logs/path_qa/v3_p2_judged.csv",
       "V3 + cả hai": "logs/path_qa/v3_p12_judged.csv"}


def dev_types():
    rows = list(csv.DictReader(open(DEV, encoding="utf-8")))
    return {r["Question"]: r["Type"] for r in rows}


def verdicts(path, keep):
    """Phán quyết đa số của từng câu; file 3 lượt chấm thì lấy đa số, file 1 lượt thì chính nó."""
    votes = collections.defaultdict(collections.Counter)
    lines = collections.Counter()
    rows = [r for r in csv.DictReader(open(path, encoding="utf-8")) if r["question"] in keep]
    for r in rows:
        lines[(r["question"], r["run"])] += 1          # câu hỏi trùng: chia đôi phiếu
    for r in rows:
        votes[r["question"]][r["verdict"]] += 1 / lines[(r["question"], r["run"])]
    return {q: c.most_common(1)[0][0] for q, c in votes.items()}


def rates(v, qs):
    qs = [q for q in qs if q in v]
    n = len(qs) or 1
    c = collections.Counter(v[q] for q in qs)
    return [100 * c[l] / n for l in LABELS], len(qs)


def main():
    types = dev_types()
    keep = set(types)
    groups = {"Tất cả": list(keep)}
    for t in ("Single", "Multi", "Null"):
        groups[t] = [q for q, x in types.items() if x == t]

    rows = []
    for name, path in BASE.items():
        if os.path.exists(path):
            rows.append((name, verdicts(path, keep)))
    missing = [p for p in NEW.values() if not os.path.exists(p)]
    for name, path in NEW.items():
        if os.path.exists(path):
            rows.append((name, verdicts(path, keep)))

    print("Dev 200 câu · cấu hình V3 (MINIRAG_CHUNK_FUSION=rrf) · công tắc P1/P2 của thành viên 1")
    print("THĂM DÒ TRÊN DEV — không thay số chính thức, không đụng cổng tầng D\n")
    print(f"   {'cấu hình':22s} " + " ".join(f"{g + ' (n=' + str(len(groups[g])) + ')':>26s}" for g in groups))
    print(f"   {'':22s} " + " ".join(f"{'acc / err / neither':>26s}" for _ in groups))
    for name, v in rows:
        cells = []
        for g, qs in groups.items():
            r, n = rates(v, qs)
            cells.append(f"{r[0]:5.1f} / {r[1]:5.1f} / {r[2]:5.1f}")
        print(f"   {name:22s} " + " ".join(f"{c:>26s}" for c in cells))

    base = [v for n, v in rows if n.startswith("V3 lượt")]
    if len(base) >= 2:
        print("\n   Dải nhiễu giữa ba lượt V3 (cùng cấu hình, khác lượt sinh):")
        for g, qs in groups.items():
            accs = [rates(v, qs)[0][0] for v in base]
            print(f"     {g:8s} acc {min(accs):5.1f} … {max(accs):5.1f}  (rộng {max(accs) - min(accs):4.1f} điểm)")
        print("   Chênh lệch nhỏ hơn dải này KHÔNG kết luận được (CLAUDE.md §3).")

    print(f"\n   Null chỉ có {len(groups['Null'])} câu trên dev: mỗi câu đổi phán quyết là {100 / len(groups['Null']):.0f} điểm.")
    if missing:
        print("\n   ⚠ Chưa có: " + ", ".join(missing))


if __name__ == "__main__":
    main()
