"""Đ1 — chấm điểm phiếu rà của người: κ, bảng nhầm lẫn, và Null acc chiếu theo hai cách đọc.

Đăng ký trước: reproduce/null_audit/preregistration/D1_nguoi_cham_lai_null.md
Chỉ dùng cho độ nhạy và Limitations — không thay số chính thức, không đụng cổng E4.

    .venv/bin/python reproduce/null_audit/score_judge_audit.py | tee logs/null_audit/d1_judge_audit/ket_qua.txt
"""
import collections
import csv
import math
import os
import sys

IN = "logs/null_audit/d1_judge_audit"
HUMAN2GEMINI = {"CHINH_XAC": "accurate", "SAI": "error", "KHONG_BIET": "neither"}
LABELS = ("accurate", "error", "neither")


def load(path):
    rows = {r["id"]: r for r in csv.DictReader(open(path, encoding="utf-8"))}
    filled = {i: r for i, r in rows.items() if r["phan_quyet"].strip()}
    return rows, filled


def kappa(pairs):
    """Cohen's κ trên các cặp nhãn (a, b)."""
    if not pairs:
        return float("nan")
    labels = sorted({x for p in pairs for x in p})
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    ca = collections.Counter(a for a, _ in pairs)
    cb = collections.Counter(b for _, b in pairs)
    pe = sum(ca[l] * cb[l] for l in labels) / n ** 2
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100 * max(0.0, c - h), 100 * min(1.0, c + h))


def lenient(row):
    return "CHINH_XAC" if row["noi_ro_khong_co"].strip().upper() == "CO" else row["phan_quyet"].strip().upper()


def main():
    if not os.path.exists(f"{IN}/sheet_A.csv"):
        sys.exit(f"Chưa có phiếu. Chạy make_judge_audit_sheet.py trước.")
    key = {r["id"]: r for r in csv.DictReader(open(f"{IN}/key_KHONG_MO_TRUOC.csv", encoding="utf-8"))}
    rows_a, a = load(f"{IN}/sheet_A.csv")
    rows_b, b = load(f"{IN}/sheet_B.csv")
    print(f"Đ1 — phiếu {len(rows_a)} dòng · người A đã chấm {len(a)} · người B đã chấm {len(b)}")
    if not a or not b:
        sys.exit("Chưa đủ hai người chấm — chưa tính được gì. (Cột phan_quyet còn trống.)")

    both = sorted(set(a) & set(b))
    print(f"\n1. Độ khớp giữa hai người trên {len(both)} dòng cùng chấm")
    pairs = [(a[i]["phan_quyet"].strip().upper(), b[i]["phan_quyet"].strip().upper()) for i in both]
    print(f"   trùng nhau {100 * sum(x == y for x, y in pairs) / max(1, len(pairs)):.1f}% · Cohen κ = {kappa(pairs):.3f}")
    for f in ("noi_ro_khong_co", "khang_dinh_them"):
        p2 = [(a[i][f].strip().upper(), b[i][f].strip().upper()) for i in both]
        print(f"   {f}: trùng {100 * sum(x == y for x, y in p2) / max(1, len(p2)):.1f}% · κ = {kappa(p2):.3f}")

    agreed = [i for i in both if pairs[both.index(i)][0] == pairs[both.index(i)][1]]
    print(f"\n2. Người (chỉ lấy {len(agreed)} dòng hai người đồng thuận) so với Gemini")
    for name, reader in (("đọc chặt", lambda i: a[i]["phan_quyet"].strip().upper()), ("đọc rộng", lambda i: lenient(a[i]))):
        pr = [(HUMAN2GEMINI.get(reader(i), "?"), key[i]["phan_quyet_gemini"]) for i in agreed]
        print(f"   {name}: trùng {100 * sum(x == y for x, y in pr) / max(1, len(pr)):.1f}% · κ = {kappa(pr):.3f}")
        tab = collections.Counter(pr)
        print("      người \\ gemini | " + " | ".join(f"{l:>9s}" for l in LABELS))
        for h in LABELS:
            print(f"      {h:>14s} | " + " | ".join(f"{tab[(h, g)]:9d}" for g in LABELS))

    print("\n3. Câu Gemini chấm `neither`: người đọc ra sao")
    for name, reader in (("đọc chặt", lambda i: a[i]["phan_quyet"].strip().upper()), ("đọc rộng", lambda i: lenient(a[i]))):
        nei = [i for i in agreed if key[i]["phan_quyet_gemini"] == "neither"]
        k = sum(1 for i in nei if reader(i) == "CHINH_XAC")
        lo, hi = wilson(k, len(nei))
        print(f"   {name}: {k}/{len(nei)} được người chấm là đúng ({100 * k / max(1, len(nei)):.0f}%, KTC 95% {lo:.0f}–{hi:.0f}%)")

    print("\n4. Chiếu sang Null acc từng nhánh (ước lượng, không thay số chính thức)")
    print("   Dùng tỉ lệ chuyển nhãn đo trên mẫu, áp cho phân bố phán quyết Gemini của từng nhánh.")
    rate = {}
    for g in LABELS:
        rows = [i for i in agreed if key[i]["phan_quyet_gemini"] == g]
        if rows:
            rate[g] = sum(1 for i in rows if a[i]["phan_quyet"].strip().upper() == "CHINH_XAC") / len(rows)
    print("   p(người chấm đúng | Gemini chấm X): " + " · ".join(f"{g} {100 * v:.0f}%" for g, v in rate.items()))
    print("   → nhân với phân bố trong logs/null_audit/b2_null_stage_d.txt để ra Null acc hiệu chỉnh từng nhánh.")


if __name__ == "__main__":
    main()
