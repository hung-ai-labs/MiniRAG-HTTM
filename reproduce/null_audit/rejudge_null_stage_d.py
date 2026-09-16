"""Đ2 — chấm lại nhóm Null của tầng D thêm 2 lượt, làm phân tích ĐỘ NHẠY.

Đăng ký trước: reproduce/null_audit/preregistration/D2_cham_lai_null_3_luot.md
KHÔNG thay số chính thức trong logs/stage_d/stage_d_report.*, KHÔNG dùng để xét lại cổng E4.

    .venv/bin/python reproduce/null_audit/rejudge_null_stage_d.py            # lọc, chấm thêm 2 lượt, rồi tổng hợp
    .venv/bin/python reproduce/null_audit/rejudge_null_stage_d.py --summary  # chỉ tổng hợp từ file đã có
"""
import argparse
import collections
import csv
import os
import statistics as st
import subprocess
import sys

OUT = "logs/null_audit/d2_rejudge"
PY = os.environ.get("PYTHON", ".venv/bin/python")
TAGS = [f"{v}_s{s}" for s in (101, 202, 303) for v in ("b1", "b2")] + ["vec_s202", "vec_s303"]
ARMS = {"B1": ["b1_s101", "b1_s202", "b1_s303"], "B2": ["b2_s101", "b2_s202", "b2_s303"],
        "VEC": ["vec_official", "vec_s202", "vec_s303"]}
# Lượt vector thuần chính thức nằm ở file 637 câu và ĐÃ có sẵn 3 lượt chấm — không phải chấm lại.
OFFICIAL_VEC = "logs/qwen637_vec_judged.csv"
LABELS = ("accurate", "error", "neither")


def null_questions():
    rows = list(csv.DictReader(open("reproduce/stage_d/nondev435.csv", encoding="utf-8")))
    return {r["Question"] for r in rows if r["Type"] == "Null"}


def filter_answers(tag, keep):
    src, dst = f"logs/stage_d/{tag}.csv", f"{OUT}/{tag}_null.csv"
    rows = [r for r in csv.DictReader(open(src, encoding="utf-8")) if r["Question"] in keep]
    assert len(rows) == len(keep), f"{tag}: lọc được {len(rows)} câu, cần {len(keep)}"
    with open(dst, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["Question", "Gold Answer", "minirag"])
        w.writeheader()
        w.writerows({k: r[k] for k in w.fieldnames} for r in rows)
    return dst


def official(tag, keep):
    """Lượt chấm chính thức (run = 1) — cùng lượt mà analyze_stage_d.py dùng."""
    path = OFFICIAL_VEC if tag == "vec_official" else f"logs/stage_d/{tag}_judged.csv"
    out = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        if r["run"] == "1" and r["question"] in keep:
            out[r["question"]] = r["verdict"]
    return out


def extra(tag, keep):
    """Hai lượt chấm bổ sung: {câu: [phán quyết, phán quyết]}. Với vector thuần chính thức là lượt 2 và 3 sẵn có."""
    if tag == "vec_official":
        votes = collections.defaultdict(dict)
        for r in csv.DictReader(open(OFFICIAL_VEC, encoding="utf-8")):
            if r["run"] in ("2", "3") and r["question"] in keep:
                votes[r["question"]][r["run"]] = r["verdict"]
        return {q: list(v.values()) for q, v in votes.items()}
    path = f"{OUT}/{tag}_judged2.csv"
    votes = collections.defaultdict(dict)
    if os.path.exists(path):
        for r in csv.DictReader(open(path, encoding="utf-8")):
            if r["question"] in keep:
                votes[r["question"]][r["run"]] = r["verdict"]
    return {q: list(v.values()) for q, v in votes.items()}


TIES = collections.Counter()


def majority(verdicts, tag=""):
    c = collections.Counter(verdicts)
    top, n = c.most_common(1)[0]
    if n > len(verdicts) / 2:
        return top
    TIES[tag] += 1
    return "neither"      # chia đều -> không tính là đúng, cùng luật với analyze_stage_d.py


def rates(verdict_of_q):
    n = len(verdict_of_q) or 1
    c = collections.Counter(verdict_of_q.values())
    return {l: 100 * c[l] / n for l in LABELS}


def summarize(keep):
    one, three = {}, {}
    for tag in TAGS + ["vec_official"]:
        off, ex = official(tag, keep), extra(tag, keep)
        one[tag] = off
        if len(ex) == len(keep) and all(len(v) == 2 for v in ex.values()):
            three[tag] = {q: majority([off[q]] + ex[q], tag) for q in off}
    print("Đ2 — ĐỘ NHẠY nhóm Null của tầng D: 1 lượt chấm (chính thức) so với đa số 3 lượt")
    print(f"Số câu Null: {len(keep)} · lượt đã chấm đủ 3: {len(three)}/{len(TAGS)}\n")
    print(f"{'nhánh':5s} {'acc 1 lượt':>12s} {'acc 3 lượt':>12s} {'err 1':>8s} {'err 3':>8s} {'nei 1':>8s} {'nei 3':>8s}")
    for arm, tags in ARMS.items():
        got = [t for t in tags if t in three]
        f = lambda src, l, ts: st.mean(rates(src[t])[l] for t in ts) if ts else float("nan")  # noqa: E731
        print(f"{arm:5s} {f(one, 'accurate', tags):12.1f} {f(three, 'accurate', got):12.1f} "
              f"{f(one, 'error', tags):8.1f} {f(three, 'error', got):8.1f} {f(one, 'neither', tags):8.1f} {f(three, 'neither', got):8.1f}")
    if TIES:
        print(f"\nCâu có 3 phiếu chia đều (bị tính là `neither` theo luật): {dict(TIES)} — tổng {sum(TIES.values())}")
    pairs = [("H2 = B2 với vector thuần", [("b2_s101", "vec_official"), ("b2_s202", "vec_s202"), ("b2_s303", "vec_s303")]),
             ("H3 = B2 với B1", [("b2_s101", "b1_s101"), ("b2_s202", "b1_s202"), ("b2_s303", "b1_s303")])]
    print("\nNull net từng cặp lượt (dương = biến thể tốt hơn); cổng E4 đăng ký trước là trung bình ≥ −3")
    for name, ps in pairs:
        for src, label in ((one, "1 lượt"), (three, "3 lượt")):
            nets = [sum(src[x][q] == "accurate" and src[y][q] != "accurate" for q in keep)
                    - sum(src[y][q] == "accurate" and src[x][q] != "accurate" for q in keep)
                    for x, y in ps if x in src and y in src]
            if nets:
                print(f"   {name} · {label}: {nets} · trung bình {st.mean(nets):+.2f}")
    print("\nĐây là ĐỘ NHẠY. Số chính thức của tầng D không đổi; cổng E4 không xét lại (đăng ký trước D2).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", action="store_true", help="chỉ tổng hợp, không gọi giám khảo")
    args = ap.parse_args()
    keep = null_questions()
    os.makedirs(OUT, exist_ok=True)
    if not args.summary:
        for tag in TAGS:
            src = filter_answers(tag, keep)
            print(f"=== {tag}: chấm thêm 2 lượt cho {len(keep)} câu Null", flush=True)
            cmd = [PY, "reproduce/Step_2_evaluate.py", "--inputpath", src, "--output", f"{OUT}/{tag}_judged2.csv",
                   "--repeats", "2", "--column", "minirag"]
            if subprocess.call(cmd) != 0:
                sys.exit(f"{tag}: chấm lỗi — dừng, không tổng hợp nửa vời")
    summarize(keep)


if __name__ == "__main__":
    main()
