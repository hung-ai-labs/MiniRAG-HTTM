"""Nhóm Null của B2 trên tầng D (16/09/2026) — chạy SAU khi phân tích tầng D đã xong, chỉ mô tả, không thay số chính thức.

Trả lời một câu: B2 mất điểm Null vì bịa thêm, hay vì câu trả lời rơi vào vùng `accurate` / `neither` mà rubric không nói rõ?
Phân loại câu trả lời bằng regex — heuristic, cần người rà (G1 trong docs/DE_XUAT_CAI_THIEN_NULL.md).

    .venv/bin/python reproduce/null_audit/b2_null_stage_d.py | tee logs/null_audit/b2_null_stage_d.txt
"""
import collections
import csv
import re
import statistics as st

NULL_TYPE = "Null"
L = ("accurate", "error", "neither")
# mở đầu câu trả lời (250 ký tự) nói không có thông tin
NEG = re.compile(r"insufficient information|no information|there (is|are) no\b|(is|are)n'?t (any |a )?(explicit |specific |direct |clear )?"
                 r"(mention|information|record|detail)|no (explicit|specific|direct|clear|particular) (mention|information|record|detail)|"
                 r"not (explicitly |specifically |directly |clearly )?(mentioned|specified|stated|provided|detailed)|"
                 r"does(n'?t| not) (mention|specify|provide|state|say|indicate)|cannot (be )?determine|unable to determine", re.I)
SPEC = re.compile(r"\b(however|likely|it appears|appears to|suggests?|infer|inferred|probably|might|may have|could be)\b", re.I)
# nói "không tìm thấy" ở BẤT KỲ đâu trong câu trả lời (không chỉ mở đầu)
SAYS_NO = re.compile(r"no (specific|explicit|direct|clear|particular)? ?(mention|information|record|detail|data)|"
                     r"there (is|are)n?'?t? (any |no )|not (explicitly |specifically |directly |clearly )?"
                     r"(mentioned|specified|stated|provided|detailed|documented)|does(n'?t| not) (mention|specify|provide|state|say|indicate)|"
                     r"insufficient information|no mention", re.I)
ARMS = {
    "V3": [("logs/qwen637_v3.csv", "logs/qwen637_v3_judged.csv"), ("logs/qwen637_v3_r2.csv", "logs/qwen637_v3_r2_judged.csv"),
           ("logs/qwen637_v3_r3.csv", "logs/qwen637_v3_r3_judged.csv")],
    "VEC": [("logs/qwen637_vec.csv", "logs/qwen637_vec_judged.csv")]
           + [(f"logs/stage_d/vec_s{s}.csv", f"logs/stage_d/vec_s{s}_judged.csv") for s in (202, 303)],
    "B1": [(f"logs/stage_d/b1_s{s}.csv", f"logs/stage_d/b1_s{s}_judged.csv") for s in (101, 202, 303)],
    "B2": [(f"logs/stage_d/b2_s{s}.csv", f"logs/stage_d/b2_s{s}_judged.csv") for s in (101, 202, 303)],
}


def kind(answer):
    m = NEG.search(answer[:250])
    if not m:
        return "khẳng định"
    return "từ chối rồi suy đoán" if SPEC.search(answer[m.end():]) else "từ chối thuần"


def null_questions():
    rows = list(csv.DictReader(open("reproduce/stage_d/nondev435.csv", encoding="utf-8")))
    return {r["Question"] for r in rows if r["Type"] == NULL_TYPE}


def load(ans_path, judged_path, keep):
    ans = {r["Question"]: r["minirag"] for r in csv.DictReader(open(ans_path, encoding="utf-8")) if r["Question"] in keep}
    rows = [r for r in csv.DictReader(open(judged_path, encoding="utf-8")) if r["run"] == "1" and r["question"] in keep]
    lines = collections.Counter(r["question"] for r in rows)
    votes = collections.defaultdict(collections.Counter)
    for r in rows:
        votes[r["question"]][r["verdict"]] += 1 / lines[r["question"]]
    verdict = {q: v.most_common(1)[0][0] for q, v in votes.items()}
    return ans, verdict


def main():
    null = null_questions()
    print(f"NHÓM NULL TRÊN TẦNG D — {len(null)} câu ngoài dev, mỗi lượt sinh chấm 1 lượt (mô tả, không thay số chính thức)\n")
    data = {name: [load(a, j, null) for a, j in paths] for name, paths in ARMS.items()}

    print("1. acc / err / neither của nhóm Null, trung bình các lượt sinh")
    for name, runs in data.items():
        cells = []
        for _, verdict in runs:
            c = collections.Counter(verdict.values())
            n = len(verdict)
            cells.append({l: 100 * c[l] / n for l in L})
        f = lambda l: f"{st.mean(c[l] for c in cells):5.1f}"  # noqa: E731
        per_run = " / ".join(f"{c['accurate']:.1f}" for c in cells)
        print(f"   {name:4s} acc {f('accurate')} · err {f('error')} · neither {f('neither')}  (acc từng lượt: {per_run})")

    print("\n2. Kiểu câu trả lời × phán quyết (cộng mọi lượt sinh; regex)")
    for name, runs in data.items():
        tab = collections.defaultdict(collections.Counter)
        for ans, verdict in runs:
            for q, v in verdict.items():
                tab[kind(ans.get(q, ""))][v] += 1
        print(f"   {name}:")
        for k in ("từ chối thuần", "từ chối rồi suy đoán", "khẳng định"):
            c = tab[k]
            print(f"     {k:22s} {sum(c.values()):3d} câu-lượt · accurate {c['accurate']:3d} · error {c['error']:3d} · neither {c['neither']:3d}")

    print("\n3. Câu bị chấm `neither`: có nói rõ 'không tìm thấy thông tin' ở đâu đó trong câu trả lời không?")
    lenient = {}
    for name, runs in data.items():
        says = nosays = total = 0
        for ans, verdict in runs:
            total += len(verdict)
            for q, v in verdict.items():
                if v == "neither":
                    if SAYS_NO.search(ans.get(q, "")):
                        says += 1
                    else:
                        nosays += 1
        base = st.mean(100 * sum(1 for v in verdict.values() if v == "accurate") / len(verdict) for _, verdict in runs)
        lenient[name] = (base, base + 100 * says / total)
        print(f"   {name:4s} {says + nosays:3d} câu-lượt `neither` · có nói rõ {says:3d} ({100 * says / max(1, says + nosays):.0f}%) · không nói {nosays:3d}")

    print("\n4. Độ nhạy (cận trên lạc quan): nếu mọi câu `neither` có nói rõ 'không tìm thấy' được tính là `accurate`")
    print("   nhánh | Null acc chính thức | Null acc theo cách đọc rộng")
    for name, (base, lo) in lenient.items():
        print(f"   {name:5s} | {base:19.1f} | {lo:.1f}")
    print("\n   Đây là CẬN, không phải số đã sửa: phân loại bằng regex và chưa có người rà (G1).")


if __name__ == "__main__":
    main()
