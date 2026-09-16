"""Đ1 — dựng phiếu để người chấm lại nhóm Null, mù cấu hình và mù phán quyết của Gemini.

Đăng ký trước: reproduce/null_audit/preregistration/D1_nguoi_cham_lai_null.md

    .venv/bin/python reproduce/null_audit/make_judge_audit_sheet.py

Ra: logs/null_audit/d1_judge_audit/{sheet_A.csv, sheet_B.csv, key_KHONG_MO_TRUOC.csv}
Hai người chấm điền sheet_A / sheet_B, KHÔNG mở file key.
"""
import collections
import csv
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from answer_kind import ASSERT, MIXED, PURE, kind  # noqa: E402

SEED = 16092026
QUOTA = {PURE: 8, MIXED: 8, ASSERT: 9}
OUT = "logs/null_audit/d1_judge_audit"
SHEET_COLS = ["id", "cau_hoi", "cau_tra_loi", "phan_quyet", "noi_ro_khong_co", "khang_dinh_them", "ghi_chu"]
ARMS = {
    "V3": [("v3", "logs/qwen637_v3.csv", "logs/qwen637_v3_judged.csv"),
           ("v3_r2", "logs/qwen637_v3_r2.csv", "logs/qwen637_v3_r2_judged.csv"),
           ("v3_r3", "logs/qwen637_v3_r3.csv", "logs/qwen637_v3_r3_judged.csv")],
    "VEC": [("vec", "logs/qwen637_vec.csv", "logs/qwen637_vec_judged.csv"),
            ("vec_s202", "logs/stage_d/vec_s202.csv", "logs/stage_d/vec_s202_judged.csv"),
            ("vec_s303", "logs/stage_d/vec_s303.csv", "logs/stage_d/vec_s303_judged.csv")],
    "B1": [(f"b1_s{s}", f"logs/stage_d/b1_s{s}.csv", f"logs/stage_d/b1_s{s}_judged.csv") for s in (101, 202, 303)],
    "B2": [(f"b2_s{s}", f"logs/stage_d/b2_s{s}.csv", f"logs/stage_d/b2_s{s}_judged.csv") for s in (101, 202, 303)],
}


def null_questions():
    rows = list(csv.DictReader(open("reproduce/stage_d/nondev435.csv", encoding="utf-8")))
    return {r["Question"] for r in rows if r["Type"] == "Null"}


def pool(keep):
    """Mọi câu-lượt Null: (nhánh, lượt, kiểu, câu hỏi, câu trả lời, phán quyết Gemini của lượt chấm 1)."""
    items = collections.defaultdict(list)
    for arm, runs in ARMS.items():
        for tag, ans_path, judged_path in runs:
            answers = {r["Question"]: r["minirag"] for r in csv.DictReader(open(ans_path, encoding="utf-8"))
                       if r["Question"] in keep}
            votes = collections.defaultdict(collections.Counter)
            lines = collections.Counter()
            rows = [r for r in csv.DictReader(open(judged_path, encoding="utf-8"))
                    if r["run"] == "1" and r["question"] in keep]
            for r in rows:
                lines[r["question"]] += 1
            for r in rows:
                votes[r["question"]][r["verdict"]] += 1 / lines[r["question"]]
            for q, counter in votes.items():
                a = answers.get(q, "")
                items[arm].append({"arm": arm, "run": tag, "kind": kind(a), "question": q, "answer": a,
                                   "gemini": counter.most_common(1)[0][0]})
    return items


def sample(items, rng):
    chosen = []
    for arm in ARMS:
        by_kind = collections.defaultdict(list)
        for it in items[arm]:
            by_kind[it["kind"]].append(it)
        for v in by_kind.values():
            rng.shuffle(v)
        picked, leftover = [], []
        for k, quota in QUOTA.items():
            picked += by_kind[k][:quota]
            leftover += by_kind[k][quota:]
        rng.shuffle(leftover)
        picked += leftover[:sum(QUOTA.values()) - len(picked)]     # lớp thiếu thì bù từ lớp còn lại
        chosen += picked
        print(f"  {arm}: {len(picked)} câu · " + " · ".join(f"{k} {sum(1 for x in picked if x['kind'] == k)}" for k in QUOTA))
    return chosen


def main():
    keep = null_questions()
    rng = random.Random(SEED)
    print(f"Đ1 — rút mẫu từ {len(keep)} câu Null ngoài dev × 4 nhánh × 3 lượt sinh (seed {SEED}):")
    chosen = sample(pool(keep), rng)
    rng.shuffle(chosen)
    os.makedirs(OUT, exist_ok=True)
    for name in ("A", "B"):
        with open(f"{OUT}/sheet_{name}.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(SHEET_COLS)
            for i, it in enumerate(chosen, 1):
                w.writerow([f"N{i:03d}", it["question"], it["answer"], "", "", "", ""])
    with open(f"{OUT}/key_KHONG_MO_TRUOC.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "nhanh", "luot", "kieu_cau_tra_loi", "phan_quyet_gemini", "cau_hoi"])
        for i, it in enumerate(chosen, 1):
            w.writerow([f"N{i:03d}", it["arm"], it["run"], it["kind"], it["gemini"], it["question"]])
    print(f"\nĐã ghi {len(chosen)} dòng vào {OUT}/sheet_A.csv và sheet_B.csv (cột phán quyết để trống).")
    print("Giá trị hợp lệ: phan_quyet = CHINH_XAC / SAI / KHONG_BIET · noi_ro_khong_co và khang_dinh_them = CO / KHONG")
    print("Chấm xong chạy: .venv/bin/python reproduce/null_audit/score_judge_audit.py")


if __name__ == "__main__":
    main()
