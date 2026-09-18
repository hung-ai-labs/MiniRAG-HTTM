"""Đ3 — chấm điểm phiếu rà nhãn Null: κ giữa hai người, và độ nhạy Null cho MỌI cấu hình cùng lúc.

Đăng ký trước: reproduce/null_audit/preregistration/D3_ra_nhan_65_null.md
Chỉ dùng cho độ nhạy và Limitations — không thay số chính thức, không đụng cổng tầng D.

    .venv/bin/python reproduce/null_audit/score_label_audit.py | tee logs/null_audit/d3_label_audit/ket_qua.txt
"""
import collections
import csv
import os
import statistics as st
import sys

IN = "logs/null_audit/d3_label_audit"
LABELS = ("accurate", "error", "neither")
# Bốn dòng bị hướng dẫn chỉ sẵn nhãn (xem phần "Nhiễm" trong preregistration/D3_ra_nhan_65_null.md) — không phải phán đoán độc
# lập, nên phải báo kèm một cột đã bỏ chúng.
NHIEM = ("L005", "L023", "L031", "L054")
ARMS_637 = {"Baseline": "fix", "V3 lượt 1": "v3", "V3 lượt 2": "v3_r2", "V3 lượt 3": "v3_r3", "Vector thuần": "vec"}
ARMS_D = {"B1": [f"b1_s{s}" for s in (101, 202, 303)], "B2": [f"b2_s{s}" for s in (101, 202, 303)],
          # lượt vector thuần chính thức nằm ở file 637 câu, không phải trong logs/stage_d/
          "VEC (tầng D)": ["vec_official", "vec_s202", "vec_s303"]}


def kappa(pairs):
    if not pairs:
        return float("nan")
    labels = sorted({x for p in pairs for x in p})
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    ca, cb = collections.Counter(a for a, _ in pairs), collections.Counter(b for _, b in pairs)
    pe = sum(ca[l] * cb[l] for l in labels) / n ** 2
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


def null_all():
    rows = list(csv.DictReader(open("dataset/LiHua-World/qa/query_set.csv", encoding="utf-8")))
    return list(dict.fromkeys(r["Question"] for r in rows if r["Type"] == "Null"))


def verdicts_637(tag, keep):
    votes = collections.defaultdict(collections.Counter)
    lines = collections.Counter()
    rows = [r for r in csv.DictReader(open(f"logs/qwen637_{tag}_judged.csv", encoding="utf-8")) if r["question"] in keep]
    for r in rows:
        lines[(r["question"], r["run"])] += 1
    for r in rows:
        votes[r["question"]][r["verdict"]] += 1 / lines[(r["question"], r["run"])]
    return {q: c.most_common(1)[0][0] for q, c in votes.items()}


def nondev_null():
    rows = csv.DictReader(open("reproduce/stage_d/nondev435.csv", encoding="utf-8"))
    return {r["Question"] for r in rows if r["Type"] == "Null"}


def verdicts_stage_d(tag, keep):
    # Tầng D chỉ có 45 câu Null ngoài dev. Lượt vector thuần chính thức nằm ở file 637 câu, nên phải lọc về đúng 45 câu đó,
    # nếu không nhánh này bị trộn 65 câu với 45 câu.
    keep = keep & nondev_null()
    path = "logs/qwen637_vec_judged.csv" if tag == "vec_official" else f"logs/stage_d/{tag}_judged.csv"
    return {r["question"]: r["verdict"] for r in csv.DictReader(open(path, encoding="utf-8"))
            if r["run"] == "1" and r["question"] in keep}


def rates(verdict_of_q, exclude):
    qs = [q for q in verdict_of_q if q not in exclude]
    n = len(qs) or 1
    c = collections.Counter(verdict_of_q[q] for q in qs)
    return {l: 100 * c[l] / n for l in LABELS}, len(qs)


def main():
    if not os.path.exists(f"{IN}/sheet_A.csv"):
        sys.exit("Chưa có phiếu. Chạy make_label_audit_sheet.py trước.")
    a = {r["id"]: r for r in csv.DictReader(open(f"{IN}/sheet_A.csv", encoding="utf-8")) if r["nhan"].strip()}
    b = {r["id"]: r for r in csv.DictReader(open(f"{IN}/sheet_B.csv", encoding="utf-8")) if r["nhan"].strip()}
    sheet = {r["id"]: r["cau_hoi"] for r in csv.DictReader(open(f"{IN}/sheet_A.csv", encoding="utf-8"))}
    print(f"Đ3 — người A đã rà {len(a)}/{len(sheet)} câu · người B {len(b)}/{len(sheet)}")
    if not a:
        sys.exit("Chưa ai rà — cột nhan còn trống.")

    if b:
        both = sorted(set(a) & set(b))
        pairs = [(a[i]["nhan"].strip().upper(), b[i]["nhan"].strip().upper()) for i in both]
        print(f"\n1. Hai người trên {len(both)} câu: trùng {100 * sum(x == y for x, y in pairs) / len(pairs):.1f}% · κ = {kappa(pairs):.3f}")
        p2 = [(a[i]["doi_mot_chi_tiet"].strip().upper(), b[i]["doi_mot_chi_tiet"].strip().upper()) for i in both]
        print(f"   doi_mot_chi_tiet: trùng {100 * sum(x == y for x, y in p2) / len(p2):.1f}% · κ = {kappa(p2):.3f}")
        agreed = {i: a[i]["nhan"].strip().upper() for i in both if a[i]["nhan"].strip().upper() == b[i]["nhan"].strip().upper()}
    else:
        agreed = {i: a[i]["nhan"].strip().upper() for i in a}
        both = sorted(a)
        print("\n1. CHỈ MỘT NGƯỜI RÀ (sửa đăng ký 16/09) — không tính được κ.")
        print("   Mọi con số dưới đây là cách đọc của một người; phải ghi đúng như vậy trong Limitations.")
    co_du = {sheet[i] for i, v in agreed.items() if v == "CO_DU"}
    mot_phan = {sheet[i] for i, v in agreed.items() if v == "CO_MOT_PHAN"}
    nhiem = {sheet[i] for i in NHIEM if i in sheet}
    print(f"\n   ⚠ {len(nhiem)} dòng nhiễm ({', '.join(NHIEM)}): hướng dẫn phát cho người rà đã nêu sẵn nhãn của đúng các dòng này.")
    print("     Cột cuối bỏ hẳn chúng khỏi phân tích. Chi tiết: preregistration/D3_ra_nhan_65_null.md, mục Nhiễm.")
    print(f"\n2. CO_DU {len(co_du)} câu · CO_MOT_PHAN {len(mot_phan)} câu · "
          f"bất đồng {len(both) - len(agreed)} câu (cần người thứ ba)")

    keep = set(null_all())
    print("\n3. Độ nhạy Null acc / err / neither — áp cùng lúc cho mọi cấu hình (KHÔNG thay số chính thức)")
    print(f"   {'cấu hình':14s} {'chính thức':>22s} {'bỏ CO_DU':>22s} {'bỏ CO_DU + CO_MOT_PHAN':>26s} "
          f"{'bỏ thêm 4 dòng nhiễm':>26s}")
    rows = [(name, [verdicts_637(tag, keep)]) for name, tag in ARMS_637.items()]
    rows += [(name, [verdicts_stage_d(t, keep) for t in tags]) for name, tags in ARMS_D.items()]
    for name, runs in rows:
        cells = []
        for exclude in (set(), co_du, co_du | mot_phan, co_du | mot_phan | nhiem):
            trio = [rates(r, exclude)[0] for r in runs]
            n = rates(runs[0], exclude)[1]
            cells.append(f"{st.mean(c['accurate'] for c in trio):.1f}/{st.mean(c['error'] for c in trio):.1f}/"
                         f"{st.mean(c['neither'] for c in trio):.1f} (n={n})")
        print(f"   {name:14s} {cells[0]:>22s} {cells[1]:>22s} {cells[2]:>26s} {cells[3]:>26s}")
    print("\n   Câu `doi_mot_chi_tiet = CO` vẫn tính là Null đúng thiết kế (quy tắc chốt trước ở D3).")


if __name__ == "__main__":
    main()
