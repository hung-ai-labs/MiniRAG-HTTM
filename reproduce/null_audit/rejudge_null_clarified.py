"""Đ6 — chấm lại nhóm Null với rubric được làm rõ, làm phân tích ĐỘ NHẠY.

Đăng ký trước: reproduce/null_audit/preregistration/D6_cham_lai_null_rubric_lam_ro.md
KHÔNG thay số chính thức của tầng D, KHÔNG xét lại E4 hay H1–H3, KHÔNG dùng để chọn biến thể.

    .venv/bin/python reproduce/null_audit/rejudge_null_clarified.py --prompt   # in prompt và mã băm
    .venv/bin/python reproduce/null_audit/rejudge_null_clarified.py --gate     # bước 2: cổng kiểm trên 40 dòng Đ1
    .venv/bin/python reproduce/null_audit/rejudge_null_clarified.py --full     # bước 3: chỉ chạy được khi cổng QUA

Prompt = prompt gốc của reproduce/Step_2_evaluate.py + đúng một đoạn làm rõ cho câu có đáp án vàng "Insufficient information".
Mã băm được khoá trong đăng ký; sửa bất kỳ ký tự nào của prompt thì script dừng.
"""
import argparse
import asyncio
import collections
import csv
import hashlib
import os
import random
import statistics as st
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "reproduce"))

CLARIFICATION = """
When the gold answer is "Insufficient information": if the system answer clearly
states that the specific detail asked for is not available in the information it
has, reply "accurate", even if it also describes related events. Reply "error"
only if it presents the missing detail as a fact.
"""
PROMPT_SHA256 = "78e5a15278535b893d6cec1dff38aa0e3901cbe425766145f35181432e94240b"   # khoá trong đăng ký Đ6
MODEL = "gemini-flash-lite-latest"
PASSES = 3
SEED = 13                                  # cùng seed xáo thứ tự mặc định của Step_2_evaluate.py
NULL_GOLD = "Insufficient information"
OUT = "logs/null_audit/d6_clarified"
D1 = "logs/null_audit/d1_judge_audit"
LABELS = ("accurate", "error", "neither")
HUMAN = {"CHINH_XAC": "accurate", "SAI": "error", "KHONG_BIET": "neither"}
RUNS = {
    "V3": [("v3", "logs/qwen637_v3.csv"), ("v3_r2", "logs/qwen637_v3_r2.csv"), ("v3_r3", "logs/qwen637_v3_r3.csv")],
    "VEC": [("vec", "logs/qwen637_vec.csv"), ("vec_s202", "logs/stage_d/vec_s202.csv"), ("vec_s303", "logs/stage_d/vec_s303.csv")],
    "B1": [(f"b1_s{s}", f"logs/stage_d/b1_s{s}.csv") for s in (101, 202, 303)],
    "B2": [(f"b2_s{s}", f"logs/stage_d/b2_s{s}.csv") for s in (101, 202, 303)],
}
PAIRS = {
    "H1 = B1 với V3": [("b1_s101", "v3"), ("b1_s202", "v3_r2"), ("b1_s303", "v3_r3")],
    "H2 = B2 với vector thuần": [("b2_s101", "vec"), ("b2_s202", "vec_s202"), ("b2_s303", "vec_s303")],
    "H3 = B2 với B1": [("b2_s101", "b1_s101"), ("b2_s202", "b1_s202"), ("b2_s303", "b1_s303")],
}


def load_s2():
    import Step_2_evaluate as s2          # nạp .env; dùng key pool, bộ giới hạn tốc độ và cơ chế thử lại sẵn có
    return s2


def prompt_text(s2):
    return s2.JUDGE_PROMPT + CLARIFICATION


def check_prompt(s2):
    h = hashlib.sha256(prompt_text(s2).encode("utf-8")).hexdigest()
    if h != PROMPT_SHA256:
        sys.exit(f"⛔ Prompt không khớp mã băm đã đăng ký ({h[:12]}… ≠ {PROMPT_SHA256[:12]}…). "
                 "Rubric đã bị sửa sau khi chốt — dừng.")


def null45():
    rows = csv.DictReader(open("reproduce/stage_d/nondev435.csv", encoding="utf-8"))
    return {r["Question"] for r in rows if r["Type"] == "Null"}


async def judge_all(s2, items, path):
    """items: [{key, question, answer}]. Ghi từng phán quyết ngay khi có; chạy lại được (resume theo key và lượt)."""
    s2.JUDGE_PROMPT = prompt_text(s2)
    done = set()
    if os.path.exists(path) and os.path.getsize(path) > 0:
        done = {(r["key"], int(r["luot"])) for r in csv.DictReader(open(path, encoding="utf-8"))}
        print(f"tiếp tục: đã có {len(done)} phán quyết")
    sem = asyncio.Semaphore(4)
    new_file = not (os.path.exists(path) and os.path.getsize(path) > 0)
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new_file:
            w.writerow(["key", "luot", "verdict"])
        for p in range(1, PASSES + 1):
            order = list(items)
            random.Random(SEED + p).shuffle(order)
            todo = [it for it in order if (it["key"], p) not in done]
            if not todo:
                continue
            print(f"lượt chấm {p}: {len(todo)} câu", flush=True)
            for i in range(0, len(todo), 20):
                chunk = todo[i:i + 20]
                rows = [{"Question": it["question"], "Gold Answer": NULL_GOLD, "minirag": it["answer"]} for it in chunk]
                got = await asyncio.gather(*[s2.judge(sem, MODEL, r, "minirag") for r in rows])
                for it, v in zip(chunk, got):
                    if v != s2.JUDGE_FAILED:
                        w.writerow([it["key"], p, v])
                fh.flush()
                print(f"  {min(i + len(chunk), len(todo))}/{len(todo)}", flush=True)


def majority_of(path):
    votes = collections.defaultdict(dict)
    for r in csv.DictReader(open(path, encoding="utf-8")):
        votes[r["key"]][int(r["luot"])] = r["verdict"]
    out, incomplete = {}, []
    for k, v in votes.items():
        if len(v) < PASSES:
            incomplete.append(k)
            continue
        top, n = collections.Counter(v.values()).most_common(1)[0]
        out[k] = top if n > PASSES / 2 else "neither"          # chia đều -> không tính là đúng
    return out, incomplete


def gate(s2):
    os.makedirs(OUT, exist_ok=True)
    sheet = list(csv.DictReader(open(f"{D1}/sheet_A.csv", encoding="utf-8")))
    key = {r["id"]: r for r in csv.DictReader(open(f"{D1}/key_KHONG_MO_TRUOC.csv", encoding="utf-8"))}
    assert len(sheet) == 40 and all(r["phan_quyet"].strip() for r in sheet), "phiếu Đ1 phải đủ 40 dòng đã chấm"
    items = [{"key": r["id"], "question": r["cau_hoi"], "answer": r["cau_tra_loi"]} for r in sheet]
    asyncio.run(judge_all(s2, items, f"{OUT}/gate_judged.csv"))
    new, incomplete = majority_of(f"{OUT}/gate_judged.csv")
    if incomplete or len(new) != 40:
        sys.exit(f"⛔ Chưa đủ 3 lượt chấm cho {len(incomplete)} dòng — chạy lại lệnh --gate để chấm nốt.")
    human = {r["id"]: HUMAN[r["phan_quyet"].strip().upper()] for r in sheet}
    orig = {i: key[i]["phan_quyet_gemini"] for i in human}

    agree = sum(new[i] == human[i] for i in human)
    disputed = [i for i in human if orig[i] == "neither"]
    agree_disp = sum(new[i] == human[i] for i in disputed)
    human_err = [i for i in human if human[i] == "error"]
    caught = sum(new[i] == "error" for i in human_err)
    orig_agree = sum(orig[i] == human[i] for i in human)
    a_ok, b_ok, c_ok = agree >= 32, agree_disp >= 20, caught >= 5
    passed = a_ok and b_ok and c_ok

    print("Đ6 — BƯỚC 2: CỔNG KIỂM trên 40 dòng Đ1 (nhãn người: Djicz, một người chấm)")
    print(f"   prompt sha256 {PROMPT_SHA256[:16]}… · {PASSES} lượt chấm · đa số tuyệt đối\n")
    print(f"   (a) khớp với người trên 40 dòng        : {agree}/40  (cần ≥ 32) → {'ĐẠT' if a_ok else 'TRƯỢT'}")
    print(f"   (b) khớp trên 24 câu gốc chấm `neither` : {agree_disp}/{len(disputed)}  (cần ≥ 20) → {'ĐẠT' if b_ok else 'TRƯỢT'}")
    print(f"   (c) bắt được câu người chấm SAI        : {caught}/{len(human_err)}  (cần ≥ 5) → {'ĐẠT' if c_ok else 'TRƯỢT'}")
    print(f"\n   Đối chiếu: rubric GỐC (1 lượt chính thức) khớp với người {orig_agree}/40")
    tab = collections.Counter((human[i], new[i]) for i in human)
    print("\n   người \\ rubric mới | " + " | ".join(f"{l:>9s}" for l in LABELS))
    for h in LABELS:
        print(f"   {h:>18s} | " + " | ".join(f"{tab[(h, g)]:9d}" for g in LABELS))
    moved = collections.Counter((orig[i], new[i]) for i in human if orig[i] != new[i])
    print(f"\n   Rubric gốc → rubric mới, các dòng đổi phán quyết: {dict(moved)}")
    print(f"\n   KẾT LUẬN CỔNG: {'QUA' if passed else 'KHÔNG QUA'}")
    if not passed:
        print("   Theo đăng ký: dừng, KHÔNG sửa câu chữ rubric để thử lại trên 40 dòng này.")
    open(f"{OUT}/gate_status.txt", "w", encoding="utf-8").write(("QUA" if passed else "KHONG_QUA") + "\n")


def official_one(tag, keep):
    path = f"logs/qwen637_{tag}_judged.csv" if tag in ("v3", "v3_r2", "v3_r3", "vec") else f"logs/stage_d/{tag}_judged.csv"
    return {r["question"]: r["verdict"] for r in csv.DictReader(open(path, encoding="utf-8"))
            if r["run"] == "1" and r["question"] in keep}


def rates(verdicts):
    n = len(verdicts) or 1
    c = collections.Counter(verdicts.values())
    return {l: 100 * c[l] / n for l in LABELS}


def full(s2):
    status = open(f"{OUT}/gate_status.txt", encoding="utf-8").read().strip() if os.path.exists(f"{OUT}/gate_status.txt") else ""
    if status != "QUA":
        sys.exit("⛔ Cổng kiểm chưa QUA (hoặc chưa chạy) — theo đăng ký không được chạy bước 3.")
    keep = null45()
    items = []
    for arm, runs in RUNS.items():
        for tag, path in runs:
            rows = [r for r in csv.DictReader(open(path, encoding="utf-8")) if r["Question"] in keep]
            assert len(rows) == len(keep), f"{tag}: {len(rows)} câu, cần {len(keep)}"
            items += [{"key": f"{tag}|{r['Question']}", "question": r["Question"], "answer": r["minirag"]} for r in rows]
    asyncio.run(judge_all(s2, items, f"{OUT}/full_judged.csv"))
    new, incomplete = majority_of(f"{OUT}/full_judged.csv")
    if incomplete:
        sys.exit(f"⛔ Chưa đủ 3 lượt chấm cho {len(incomplete)} câu — chạy lại lệnh --full để chấm nốt.")
    by_tag = collections.defaultdict(dict)
    for k, v in new.items():
        tag, q = k.split("|", 1)
        by_tag[tag][q] = v

    print("Đ6 — BƯỚC 3: nhóm Null ngoài dev (45 câu) × 4 nhánh × 3 lượt sinh, rubric làm rõ, 3 lượt chấm")
    print("ĐỘ NHẠY — số chính thức của tầng D, cổng E4 và H1–H3 KHÔNG đổi\n")
    print(f"   {'nhánh':5s} | {'rubric gốc (chính thức)':>26s} | {'rubric làm rõ':>22s}")
    print(f"   {'':5s} | {'acc / err / neither':>26s} | {'acc / err / neither':>22s}")
    for arm, runs in RUNS.items():
        tags = [t for t, _ in runs]
        o = [rates(official_one(t, keep)) for t in tags]
        n = [rates(by_tag[t]) for t in tags]
        f = lambda rs: " / ".join(f"{st.mean(r[l] for r in rs):4.1f}" for l in LABELS)  # noqa: E731
        print(f"   {arm:5s} | {f(o):>26s} | {f(n):>22s}")
    print("\nNull net từng cặp lượt (dương = biến thể tốt hơn); cổng E4 gốc là trung bình ≥ −3")
    for name, ps in PAIRS.items():
        for label, src in (("rubric gốc", {t: official_one(t, keep) for pair in ps for t in pair}), ("rubric làm rõ", by_tag)):
            nets = [sum(src[x][q] == "accurate" and src[y][q] != "accurate" for q in keep)
                    - sum(src[y][q] == "accurate" and src[x][q] != "accurate" for q in keep) for x, y in ps]
            print(f"   {name:26s} · {label:13s}: {nets} · trung bình {st.mean(nets):+.2f}")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--prompt", action="store_true")
    g.add_argument("--gate", action="store_true")
    g.add_argument("--full", action="store_true")
    args = ap.parse_args()
    s2 = load_s2()
    if args.prompt:
        text = prompt_text(s2)
        print(text)
        print("sha256:", hashlib.sha256(text.encode("utf-8")).hexdigest())
        return
    check_prompt(s2)
    gate(s2) if args.gate else full(s2)


if __name__ == "__main__":
    main()
