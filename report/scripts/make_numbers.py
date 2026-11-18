"""Sinh mọi con số của bài từ file phán quyết và báo cáo trong logs/ — bài KHÔNG chứa số gõ tay.

    .venv/Scripts/python.exe report/scripts/make_numbers.py        (Windows)
    .venv/bin/python        report/scripts/make_numbers.py        (Linux/macOS)

Ghi: report/generated/numbers.tex, table_*.tex, evidence.csv

Định nghĩa (giống hệt đăng ký trước tầng D, ROADMAP mục "Tầng D" và "Xử lý phán quyết và mẫu số"):
  * tập đánh giá chính: 435 câu ngoài dev (reproduce/stage_d/nondev435.csv);
  * mỗi lượt sinh lấy lượt chấm run = 1; "đúng" = đa số tuyệt đối có trọng số;
  * acc/err/neither của một nhánh = trung bình qua các lượt sinh;
  * kiểm định chính: hoán vị đổi dấu ghép cặp trên hiệu accuracy trung bình theo câu (100.000 lần, seed 20260914);
  * KTC 95%: bootstrap ghép cặp theo câu (10.000 lần, seed 20260914) trên cùng hiệu số.
Phép so với MiniRAG tái lập KHÔNG nằm trong đăng ký trước (khám phá) và mốc này chỉ có MỘT lượt sinh.
"""
import collections, csv, importlib.util, json, os, re, statistics as st, subprocess, sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GEN = os.path.join(ROOT, "report", "generated")
os.makedirs(GEN, exist_ok=True)

spec = importlib.util.spec_from_file_location("sd", os.path.join(ROOT, "reproduce", "stage_d", "analyze_stage_d.py"))
sd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sd)

SEED, NBOOT = 20260914, 10_000
TYPES = ("Single", "Multi", "Null")

# Mã nội bộ -> khoá macro (chỉ chữ cái) và tên trong bài
ARM_INFO = {
    "BASE": ("Base", r"MiniRAG (tái lập)"),
    "V3":   ("GV",   r"RRF(đồ thị, vectơ)"),
    "VEC":  ("V",    r"Vectơ thuần"),
    "B1":   ("GVK",  r"RRF(đồ thị, vectơ, BM25)"),
    "B2":   ("VK",   r"RRF(vectơ, BM25)"),
}
ARMS = dict(sd.ARMS)
ARMS["BASE"] = [("logs/qwen637_fix_judged.csv", "1", None)]
ORDER = ["BASE", "V3", "VEC", "B1", "B2"]

evidence = []          # sổ bằng chứng sinh tự động: (macro, giá trị, nguồn, ghi chú)
macros = {}


def commit_of(path):
    try:
        return subprocess.check_output(["git", "log", "-1", "--format=%h", "--", path], cwd=ROOT,
                                       text=True).strip() or "chưa commit"
    except Exception:
        return "?"


def num(x, d=2):
    """Số thập phân kiểu Việt: dấu phẩy."""
    s = f"{x:.{d}f}".replace(".", "{,}")
    return s.replace("-", "\\textminus{}") if s.startswith("-") else s


def signed(x, d=2):
    if abs(x) < 0.5 * 10 ** -d:
        return num(0.0, d)
    return ("+" if x >= 0 else "\\textminus{}") + num(abs(x), d)


P_FLOOR = 1 / (sd.NPERM + 1)          # p nhỏ nhất kiểm định hoán vị có thể cho


def pval(p, floor_mult=1):
    """floor_mult: số phép so Holm nhân vào (p sàn × m)."""
    if p <= P_FLOOR * floor_mult * 1.000001:
        return (f"\\ensuremath{{\\le {floor_mult}\\cdot 10^{{-5}}}}" if floor_mult > 1
                else "\\ensuremath{\\le 10^{-5}}")
    if p >= 0.001:
        return num(p, 3)
    e = int(np.floor(np.log10(p)))
    m = round(p / 10 ** e, 1)
    if m >= 10:
        m, e = m / 10, e + 1
    return f"\\ensuremath{{{num(m, 1)}\\cdot 10^{{{e}}}}}"


def put(name, value, source, note=""):
    assert re.fullmatch(r"[A-Za-z]+", name), name
    assert name not in macros, f"trùng macro {name}"
    macros[name] = value
    evidence.append((name, value, source, commit_of(source.split(" ")[0]), note))


def check_text(path, needle):
    """Số chỉ có trong báo cáo văn bản: kiểm nó thật sự có mặt trong file nguồn, không thì dừng."""
    txt = open(os.path.join(ROOT, path), encoding="utf-8").read()
    if needle not in txt:
        sys.exit(f"KHÔNG KHỚP: '{needle}' không có trong {path}")
    return needle


# ---------------------------------------------------------------- QA, 435 câu ngoài dev
qs, types = sd.questions()
runs = {}
for a in ORDER:
    rr, bad = sd.load_arm(a, qs, ARMS)
    if rr is None or bad:
        sys.exit(f"nhánh {a}: {bad}")
    runs[a] = rr

def type_rate(path, run, label, tq):
    """Tỉ lệ phiếu `label` có trọng số trong nhóm câu tq — cùng định nghĩa với cột tổng (load_run 'rate')."""
    tset = set(tq)
    rows = [r for r in csv.DictReader(open(os.path.join(ROOT, path), encoding="utf-8"))
            if r["run"] == run and r["question"] in tset]
    lines = collections.Counter(r["question"] for r in rows)
    w = sum(1 / lines[r["question"]] for r in rows if r["verdict"] == label)
    return 100 * w / len(lines)


summary = {}
for a in ORDER:
    rr = runs[a]
    acc = [r["rate"]["accurate"] for r in rr]
    err = [r["rate"]["error"] for r in rr]
    nei = [r["rate"]["neither"] for r in rr]
    by = {}
    for t in TYPES:
        tq = [q for q in qs if types[q] == t]
        by[t] = st.mean(type_rate(p, run, "accurate", tq) for p, run, _ in ARMS[a])
    s = {"acc": st.mean(acc), "sd": st.stdev(acc) if len(acc) > 1 else None, "err": st.mean(err),
         "nei": st.mean(nei), "runs": acc, "by": by, "n_runs": len(rr)}
    s["prec"] = 100 * s["acc"] / (s["acc"] + s["err"])
    summary[a] = s
    k = ARM_INFO[a][0]
    src = "; ".join(p for p, _, _ in ARMS[a])
    put(f"acc{k}", num(s["acc"]), src, f"{len(rr)} lượt sinh × chấm run 1, 435 câu ngoài dev")
    put(f"err{k}", num(s["err"]), src)
    put(f"nei{k}", num(s["nei"]), src)
    put(f"prec{k}", num(s["prec"]), src, "acc/(acc+err)")
    put(f"sd{k}", num(s["sd"]) if s["sd"] is not None else "--", src, "sd giữa các lượt sinh")
    for t in TYPES:
        put(f"acc{k}{t}", num(by[t]), src)

n_type = {t: sum(types[q] == t for q in qs) for t in TYPES}
put("nHeld", str(len(qs)), "reproduce/stage_d/nondev435.csv")
for t in TYPES:
    put(f"nHeld{t}", str(n_type[t]), "reproduce/stage_d/nondev435.csv")


def boot_ci(d):
    d = np.asarray(d, float)
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(d), size=(NBOOT, len(d)))
    m = d[idx].mean(axis=1)
    return 100 * np.percentile(m, 2.5), 100 * np.percentile(m, 97.5)


def compare(A, B):
    c = sd.compare(runs[A], runs[B], qs, types)
    common = [q for q in qs if all(q in r["correct"] for r in runs[A] + runs[B])]
    d = [st.mean(r["correct"][q] for r in runs[A]) - st.mean(r["correct"][q] for r in runs[B]) for q in common]
    c["ci"] = boot_ci(d)
    c["d"] = d
    for t in TYPES:
        c["groups"][t]["ci"] = boot_ci([x for q, x in zip(common, d) if types[q] == t])
    return c


# Giả thuyết đã đăng ký (Holm trên 3) + phép so khám phá (Holm riêng trên 4)
PRE = [("H1", "B1", "V3"), ("H2", "B2", "VEC"), ("H3", "B2", "B1")]
EXP = [("X1", "V3", "BASE"), ("X2", "VEC", "BASE"), ("X3", "B2", "BASE"), ("X4", "VEC", "V3")]
res = {h: compare(a, b) for h, a, b in PRE + EXP}
for fam in (PRE, EXP):
    adj = sd.holm({h: res[h]["p_perm"] for h, _, _ in fam})
    for h, _, _ in fam:
        res[h]["p_holm"] = adj[h]

# đối chiếu với báo cáo tầng D đã công bố (phải trùng tới 2 chữ số)
rep = json.load(open(os.path.join(ROOT, "logs", "stage_d", "stage_d_report.json"), encoding="utf-8"))
for h, _, _ in PRE:
    got, pub = res[h]["diff_pts"], rep["comparisons"][h]["diff_pts"]
    assert abs(got - pub) < 1e-6, f"{h}: tính lại {got} khác báo cáo {pub}"
    assert rep["classes"][h] == {"H1": "ROBUST POSITIVE", "H2": "BORDERLINE", "H3": "ROBUST POSITIVE"}[h]

FAM_SIZE = {h: len(fam) for fam in (PRE, EXP) for h, _, _ in fam}
for h, a, b in PRE + EXP:
    c = res[h]
    src = f"logs (nhánh {a} vs {b})"
    K = f"{h[0]}{'ABCDEFG'[int(h[1]) - 1]}"
    put(f"diff{K}", signed(c["diff_pts"]), src, "điểm %, trung bình theo câu")
    put(f"ciLo{K}", signed(c["ci"][0]), src, "KTC 95% bootstrap")
    put(f"ciHi{K}", signed(c["ci"][1]), src)
    put(f"pHolm{K}", pval(c["p_holm"], FAM_SIZE[h]), src, "hoán vị đổi dấu, Holm trong họ")
    put(f"pairs{K}", " · ".join(f"{x['up']}/{x['down']}" for x in c["pairs"]), src, "lên/xuống từng cặp lượt")
    put(f"nullNet{K}", signed(c["null_net_mean"]), src, "Null net trung bình (câu)")
    for t in TYPES:
        g = c["groups"][t]
        put(f"diff{K}{t}", signed(g["diff_pts"]), src, f"n={g['n']}")
        put(f"ciLo{K}{t}", signed(g["ci"][0]), src, "KTC 95% bootstrap theo nhóm")
        put(f"ciHi{K}{t}", signed(g["ci"][1]), src)
        put(f"p{K}{t}", pval(g["p"]), src, "không hiệu chỉnh")
    put(f"dErr{K}", signed(c["delta_err_pts"]), src)

# lớp phân loại tầng D, nguyên văn từ báo cáo
for h, _, _ in PRE:
    put(f"class{h[0]}{'ABC'[int(h[1]) - 1]}", rep["classes"][h], "logs/stage_d/stage_d_report.json")

# token context trung vị (E5), từ báo cáo tầng D
toks = rep["comparisons"]["H2"]["tokens_median"]
put("tokVK", num(st.mean(toks), 0), "logs/stage_d/stage_d_report.json", "trung vị token Sources+Entities, TB 3 lượt")

# ---------------------------------------------------------------- nhiễu
base_judge = []
for run in ("1", "2", "3"):
    r = sd.load_run("logs/qwen637_fix_judged.csv", run, qs)
    base_judge.append(r["rate"]["accurate"])
put("sdJudgeBase", num(st.stdev(base_judge)), "logs/qwen637_fix_judged.csv", "sd acc giữa 3 lượt chấm, 1 lượt sinh")
put("sdGenGV", num(summary["V3"]["sd"]), "logs/qwen637_v3*_judged.csv", "sd acc giữa 3 lượt sinh")
put("Tthr", num(sd.T_PTS), "reproduce/stage_d/analyze_stage_d.py", "ngưỡng T đăng ký trước")

# ---------------------------------------------------------------- truy xuất (mô phỏng offline, 180 câu dev có evidence)
def grab(path, label, kind):
    txt = open(os.path.join(ROOT, path), encoding="utf-8").read()
    block = txt.split("--- Single")[0]                       # chỉ khối TỔNG
    for line in block.splitlines():
        if line.strip().startswith(label):
            nums = re.findall(r"(\d+\.\d)%", line)
            if kind == "sim":
                return float(nums[0]), float(nums[1])        # chunk giữ, câu đủ
            return float(nums[0]), float(nums[1])
    sys.exit(f"không thấy dòng '{label}' trong {path}")


RET = [
    ("Base", "logs/simulate_fusion.txt", "đồ thị có lỗi (hiện tại)", "sim"),
    ("V", "logs/simulate_fusion.txt", "vector thuần", "sim"),
    ("GV", "logs/simulate_fusion.txt", "RRF(đồ thị có lỗi, vector)", "sim"),
    ("GVK", "logs/probe_bm25_fusion.txt", "+K ", "probe"),
    ("VK", "logs/probe_bm25_fusion.txt", "RRF(V,K) bỏ đồ thị", "probe"),
]
ret = {}
for k, path, label, kind in RET:
    ret[k] = grab(path, label, kind)
    put(f"retChunk{k}", num(ret[k][0], 1), path, "chunk đáp án còn sau A1@4000, 207 chunk")
    put(f"retFull{k}", num(ret[k][1], 1), path, "câu đủ mọi chunk đáp án sau A1, 180 câu")
# V3 có mặt ở cả hai file: phải trùng, chứng tỏ hai mô phỏng cùng thước đo
v3_probe = grab("logs/probe_bm25_fusion.txt", "V3 = RRF(G,V)", "probe")
assert v3_probe == ret["GV"], (v3_probe, ret["GV"])

check_text("logs/diag_path2chunk_report.txt", "87.0%")
put("retVecTopThirty", num(87.0, 1), "logs/diag_path2chunk_report.txt", "chunk đáp án trong top-30 vectơ, trước cắt")
check_text("logs/diag_path2chunk_report.txt", "61.8%")
put("retGraphTopThirty", num(61.8, 1), "logs/diag_path2chunk_report.txt", "chunk đáp án trong 30 chunk đồ thị")
check_text("logs/retrieval_audit/diagnose.txt", "203/207 = 98.1%")
put("retCandVK", num(98.1, 1), "logs/retrieval_audit/diagnose.txt", "chunk đáp án trong ứng viên RRF(V,K)")
check_text("logs/retrieval_audit/diagnose.txt", "tìm được nhưng bị A1 cắt                  25 câu (86%)")
put("cutFailVK", "25", "logs/retrieval_audit/diagnose.txt", "câu thiếu đáp án do A1 cắt, trên 29")
put("failVK", "29", "logs/retrieval_audit/diagnose.txt")
check_text("logs/retrieval_audit/diagnose.txt", "Multi  đủ đáp án sau A1 15/21 = 71.4%")
put("retFullVKMulti", num(71.4, 1), "logs/retrieval_audit/diagnose.txt")
check_text("ROADMAP.md", "đã chứa **93,7%**")
put("unionGV", num(93.7, 1), "ROADMAP.md", "top-30 đồ thị ∪ top-30 vectơ chứa chunk đáp án")

# ---------------------------------------------------------------- Null: độ nhạy rubric (Đ6), mức F
NULLF = "logs/null_audit/d6_clarified/baseline_ket_qua.txt"
txt = open(os.path.join(ROOT, NULLF), encoding="utf-8").read()
for code, k in (("BASE", "Base"), ("V3", "GV"), ("VEC", "V"), ("B1", "GVK"), ("B2", "VK")):
    m = re.search(rf"^\s*{code}\s*\|\s*([\d.]+)\s*/\s*([\d.]+)\s*/\s*([\d.]+)\s*\|\s*([\d.]+)\s*/\s*([\d.]+)\s*/\s*([\d.]+)",
                  txt, re.M)
    assert m, code
    v = [float(x) for x in m.groups()]
    put(f"nullOrig{k}", f"{num(v[0], 1)} / {num(v[1], 1)} / {num(v[2], 1)}", NULLF, "3 lượt chấm, rubric gốc")
    put(f"nullClar{k}", f"{num(v[3], 1)} / {num(v[4], 1)} / {num(v[5], 1)}", NULLF, "3 lượt chấm, rubric làm rõ")
check_text("docs/KET_QUA_HIEN_TAI.md", "22/24 câu")
check_text("docs/KET_QUA_HIEN_TAI.md", "38/40, rubric gốc 15/40")
put("humanAgreeClar", "38/40", "docs/KET_QUA_HIEN_TAI.md", "rubric làm rõ khớp một người chấm")
put("humanAgreeOrig", "15/40", "docs/KET_QUA_HIEN_TAI.md")

# ---------------------------------------------------------------- tham chiếu bài gốc (mức G) và hằng số khác
for k, v in (("accPaper", "48,75"), ("errPaper", "26,02"), ("neiPaper", "25,23"), ("precPaper", "65,20")):
    check_text("CLAUDE.md", v)
    put(k, v.replace(",", "{,}"), "CLAUDE.md (bảng của bài MiniRAG, Qwen2.5-3B)", "tham chiếu, khác giám khảo")
check_text("CLAUDE.md", "~68.000 → 653 lời gọi")
put("callsBefore", "68.000", "CLAUDE.md", "ước lượng lời gọi LLM trước khi vá O(N^2), 267 tài liệu")
put("callsAfter", "653", "CLAUDE.md")
check_text("CLAUDE.md", "không cắt trung vị 22.839 token, max 33.412")
put("ctxNoCapMed", "22.839", "CLAUDE.md", "measure_sources_cap.py, dev 200")
put("ctxNoCapMax", "33.412", "CLAUDE.md")
check_text("CLAUDE.md", "ở\n  A1@4000 trung vị 3.743")
put("ctxCapMed", "3.743", "CLAUDE.md")
check_text("CLAUDE.md", "khớp **0 node** khi chưa vá, **49 node** khi đã vá")
put("atypeNodesFixed", "49", "CLAUDE.md")
check_text("CLAUDE.md", "44 lên / 40 xuống, net +4, p = 0,744")
put("atypeQwen", "44 lên / 40 xuống, p = 0{,}744", "CLAUDE.md", "McNemar, 635 câu, Qwen")
check_text("CLAUDE.md", "24 sai→đúng, 29 đúng→sai")
put("atypeGemini", "24 lên / 29 xuống, p = 0{,}583", "CLAUDE.md", "McNemar, 635 câu, Gemini")
check_text("docs/CAI_TIEN_VA_BENCHMARK.md", "1.556 node / 1.509 cạnh")
put("graphNodes", "1.556", "docs/CAI_TIEN_VA_BENCHMARK.md")
put("graphEdges", "1.509", "docs/CAI_TIEN_VA_BENCHMARK.md")
check_text("docs/CAI_TIEN_VA_BENCHMARK.md", "46% node cô lập")
put("graphIsolated", "46", "docs/CAI_TIEN_VA_BENCHMARK.md", "% node cô lập")
check_text("docs/KET_QUA_HIEN_TAI.md", "cho BM25 tốn ~1 ms")
put("bmMs", "1", "docs/KET_QUA_HIEN_TAI.md", "ms/câu, đo xen kẽ tầng B")
check_text("docs/CAI_TIEN_VA_BENCHMARK.md", "13/40 câu được chấm đúng vẫn chứa ngày/thứ tự/người nói mâu thuẫn")
put("judgeLenient", "13/40", "docs/CAI_TIEN_VA_BENCHMARK.md", "câu accurate vẫn mâu thuẫn Sources")

check_text("docs/KET_QUA_HIEN_TAI.md", "(cổng thời gian +61,7 ms)")
put("timeGateFail", "+61{,}7", "docs/KET_QUA_HIEN_TAI.md", "cổng thời gian canary gốc, ms")
check_text("docs/KET_QUA_HIEN_TAI.md", "so với V3: 80 / 61, p = 0,13")
put("vecVsGVpre", "80 lên / 61 xuống, \\ensuremath{p = 0{,}13}", "docs/KET_QUA_HIEN_TAI.md", "đăng ký trước, 1 lượt sinh, 635 câu")
check_text("docs/KET_QUA_HIEN_TAI.md", "| V4 · trộn RRF @2000 token | 52,28 ± 0,16 | 27,19 | 20,52 | 65,79 | 53,36 | 27,08 | 68,72 | 80 / 75, p = 0,748")
put("budgetTwoK", "80 lên / 75 xuống, \\ensuremath{p = 0{,}748}", "docs/KET_QUA_HIEN_TAI.md", "RRF(G,V)@2000 vs MiniRAG, 635 câu")
put("ptsPerNull", num(100 / n_type["Null"], 1), "reproduce/stage_d/nondev435.csv", "1 câu Null = ? điểm")
put("ratioXCT", num(res["X3"]["diff_pts"] / sd.T_PTS, 1), "tính từ X3 và T")
check_text("logs/retrieval_audit/BASELINE_B2.md", "| — trong 25 câu bị cắt: **chính chunk đáp án dài 1.200 token** | 16/25 |")
put("longAnsCut", "16", "logs/retrieval_audit/BASELINE_B2.md", "trong 25 câu bị cắt, chunk đáp án dài 1.200 token")
check_text("logs/null_audit/d6_clarified/full_ket_qua.txt", "Lời từ chối thuần: 0 câu bị chấm error ở mọi nhánh (175/175 accurate)")
put("refusalAcc", "175/175", "logs/null_audit/d6_clarified/full_ket_qua.txt")
check_text("docs/CAI_TIEN_VA_BENCHMARK.md", "19/32 câu Null bị chấm `error` là dạng này")
put("nullPremise", "19/32", "docs/CAI_TIEN_VA_BENCHMARK.md", "câu Null bị error do ghép sự thật gần giống")
check_text("docs/CAI_TIEN_VA_BENCHMARK.md", "đạt AUC 0,85")
put("premiseAUC", "0{,}85", "docs/CAI_TIEN_VA_BENCHMARK.md")
check_text("docs/KET_QUA_HIEN_TAI.md", "22/24 câu\nGemini chấm `neither` là đúng")
put("humanNeither", "22/24", "docs/KET_QUA_HIEN_TAI.md", "một người chấm 40 câu Null")
check_text("CLAUDE.md", "21% câu đổi phán quyết theo\nlượt lấy mẫu")
put("flipRate", "21", "CLAUDE.md", "% câu đổi phán quyết giữa hai lượt sinh cùng cấu hình")

# ---------------------------------------------------------------- ghi file
with open(os.path.join(GEN, "numbers.tex"), "w", encoding="utf-8") as f:
    f.write("% SINH TỰ ĐỘNG bởi report/scripts/make_numbers.py — không sửa tay.\n")
    for k, v in macros.items():
        f.write(f"\\newcommand{{\\{k}}}{{{v}}}\n")


def row(a, ital=False):
    s, k = summary[a], ARM_INFO[a][0]
    sdv = f" $\\pm$ {num(s['sd'])}" if s["sd"] is not None else ""
    name = ARM_INFO[a][1]
    cells = [name, f"{s['n_runs']}", f"{num(s['acc'])}{sdv}", num(s["err"]), num(s["nei"]), num(s["prec"]),
             num(s["by"]["Single"]), num(s["by"]["Multi"]), num(s["by"]["Null"])]
    return " & ".join(cells) + r" \\"


with open(os.path.join(GEN, "table_main.tex"), "w", encoding="utf-8") as f:
    f.write("% SINH TỰ ĐỘNG — make_numbers.py\n")
    f.write("\\begin{tabular}{lcccccccc}\n\\toprule\n")
    f.write("Cách xếp hạng đoạn & Lượt sinh & acc $\\uparrow$ & err $\\downarrow$ & neither & "
            "$\\frac{\\text{acc}}{\\text{acc+err}}$ & Single & Multi & Null \\\\\n")
    f.write(f" & & & & & & ({n_type['Single']}) & ({n_type['Multi']}) & ({n_type['Null']}) \\\\\n\\midrule\n")
    for a in ORDER:
        f.write(row(a) + "\n")
    f.write("\\midrule\n\\textit{Bài gốc, Qwen2.5-3B (tham chiếu)} & -- & \\textit{"
            f"{macros['accPaper']}" "} & \\textit{" f"{macros['errPaper']}" "} & \\textit{"
            f"{macros['neiPaper']}" "} & \\textit{" f"{macros['precPaper']}" "} & & & \\\\\n")
    f.write("\\bottomrule\n\\end{tabular}\n")

LBL = {"H1": "RRF(đồ thị, vectơ, BM25) vs RRF(đồ thị, vectơ)", "H2": "RRF(vectơ, BM25) vs vectơ thuần",
       "H3": "RRF(vectơ, BM25) vs RRF(đồ thị, vectơ, BM25)", "X1": "RRF(đồ thị, vectơ) vs MiniRAG",
       "X2": "Vectơ thuần vs MiniRAG", "X3": "RRF(vectơ, BM25) vs MiniRAG", "X4": "Vectơ thuần vs RRF(đồ thị, vectơ)"}
with open(os.path.join(GEN, "table_tests.tex"), "w", encoding="utf-8") as f:
    f.write("% SINH TỰ ĐỘNG — make_numbers.py\n\\begin{tabular}{llrcccl}\n\\toprule\n")
    f.write("& Phép so & $\\Delta$acc & KTC 95\\% & $p_{\\text{Holm}}$ & Lên / xuống từng cặp lượt & Null net \\\\\n\\midrule\n")
    f.write("\\multicolumn{7}{l}{\\textit{Đăng ký trước (Holm trên 3 phép so)}} \\\\\n")
    for h, _, _ in PRE + EXP:
        if h == "X1":
            f.write("\\midrule\n\\multicolumn{7}{l}{\\textit{Khám phá, không đăng ký trước (Holm trên 4 phép so); "
                    "MiniRAG chỉ có 1 lượt sinh}} \\\\\n")
        c = res[h]
        f.write(f"{h} & {LBL[h]} & {signed(c['diff_pts'])} & [{signed(c['ci'][0])}; {signed(c['ci'][1])}] & "
                f"{pval(c['p_holm'], FAM_SIZE[h])} & {' · '.join(str(x['up']) + '/' + str(x['down']) for x in c['pairs'])} & "
                f"{signed(c['null_net_mean'])} \\\\\n")
    f.write("\\bottomrule\n\\end{tabular}\n")

with open(os.path.join(GEN, "table_retrieval.tex"), "w", encoding="utf-8") as f:
    f.write("% SINH TỰ ĐỘNG — make_numbers.py\n\\begin{tabular}{lcc}\n\\toprule\n")
    f.write("Cách xếp hạng đoạn & Đoạn đáp án còn trong Sources & Câu đủ mọi đoạn đáp án \\\\\n")
    f.write(" & (207 đoạn) & (180 câu) \\\\\n\\midrule\n")
    for k, a in (("Base", "BASE"), ("GV", "V3"), ("V", "VEC"), ("GVK", "B1"), ("VK", "B2")):
        f.write(f"{ARM_INFO[a][1]} & {num(ret[k][0], 1)}\\% & {num(ret[k][1], 1)}\\% \\\\\n")
    f.write("\\bottomrule\n\\end{tabular}\n")

with open(os.path.join(GEN, "table_null.tex"), "w", encoding="utf-8") as f:
    f.write("% SINH TỰ ĐỘNG — make_numbers.py\n\\begin{tabular}{lcc}\n\\toprule\n")
    f.write("Cách xếp hạng đoạn & Rubric gốc (chính thức) & Rubric làm rõ (độ nhạy) \\\\\n")
    f.write(" & acc / err / neither & acc / err / neither \\\\\n\\midrule\n")
    for k, a in (("Base", "BASE"), ("GV", "V3"), ("V", "VEC"), ("GVK", "B1"), ("VK", "B2")):
        f.write(f"{ARM_INFO[a][1]} & {macros['nullOrig' + k]} & {macros['nullClar' + k]} \\\\\n")
    f.write("\\bottomrule\n\\end{tabular}\n")

with open(os.path.join(GEN, "table_runs.tex"), "w", encoding="utf-8") as f:
    f.write("% SINH TỰ ĐỘNG — make_numbers.py\n\\begin{tabular}{lccc}\n\\toprule\n")
    f.write("Cách xếp hạng đoạn & Lượt 1 & Lượt 2 & Lượt 3 \\\\\n\\midrule\n")
    for a in ORDER:
        cells = [num(x) for x in summary[a]["runs"]] + ["--"] * (3 - summary[a]["n_runs"])
        f.write(f"{ARM_INFO[a][1]} & " + " & ".join(cells) + " \\\\\n")
    f.write("\\bottomrule\n\\end{tabular}\n")

with open(os.path.join(GEN, "evidence.csv"), "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["macro", "giá trị", "nguồn", "commit nguồn", "ghi chú"])
    w.writerows(evidence)

print(f"OK: {len(macros)} macro, 5 bảng → {os.path.relpath(GEN, ROOT)}")
for a in ORDER:
    s = summary[a]
    print(f"  {a:5s} acc {s['acc']:6.2f}  err {s['err']:6.2f}  nei {s['nei']:6.2f}  runs {[round(x, 2) for x in s['runs']]}")
for h, a, b in PRE + EXP:
    c = res[h]
    print(f"  {h} {a} vs {b}: {c['diff_pts']:+.2f} [{c['ci'][0]:+.2f}; {c['ci'][1]:+.2f}] p_holm={c['p_holm']:.2g} "
          f"Null {c['groups']['Null']['diff_pts']:+.2f}")
