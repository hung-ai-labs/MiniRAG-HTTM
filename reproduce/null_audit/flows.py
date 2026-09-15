"""Nhóm Null: câu mất `accurate` đi đâu, và giám khảo chấm từng kiểu câu trả lời thế nào (rà soát 15/09/2026).
Offline, không gọi API, không dùng dữ liệu tầng D. Phân loại câu trả lời bằng regex — heuristic, cần người rà (G1)."""
import csv, json, re, collections
qs = list(csv.DictReader(open("dataset/LiHua-World/qa/query_set.csv", encoding="utf-8")))
null = list(dict.fromkeys(r["Question"] for r in qs if r["Type"] == "Null"))
L = ("accurate", "error", "neither")
# mở đầu (250 ký tự) nói không có thông tin / không được nhắc tới
NEG = re.compile(r"insufficient information|no information|there (is|are) no\b|(is|are)n'?t (any |a )?(explicit |specific |direct |clear )?(mention|information|record|detail)|no (explicit|specific|direct|clear|particular) (mention|information|record|detail)|not (explicitly |specifically |directly |clearly )?(mentioned|specified|stated|provided|detailed)|does(n'?t| not) (mention|specify|provide|state|say|indicate)|cannot (be )?determine|unable to determine", re.I)
# sau đó vẫn suy đoán / đưa chi tiết
SPEC = re.compile(r"\b(however|likely|it appears|appears to|suggests?|infer|inferred|probably|might|may have|could be)\b", re.I)
def kind(a):
    m = NEG.search(a[:250])
    if not m: return "khẳng định (không mở đầu bằng từ chối)"
    return "từ chối rồi suy đoán" if SPEC.search(a[m.end():]) else "từ chối thuần"
def load(tag):
    ans = {r["Question"]: r["minirag"] for r in csv.DictReader(open(f"logs/qwen637_{tag}.csv", encoding="utf-8"))}
    votes = collections.defaultdict(list)
    for r in csv.DictReader(open(f"logs/qwen637_{tag}_judged.csv", encoding="utf-8")):
        votes[r["question"]].append(r["verdict"])
    return ans, votes, {q: collections.Counter(v).most_common(1)[0][0] for q, v in votes.items()}
runs = {t: load(t) for t in ("fix", "v1", "v2", "v3", "v3_r2", "v3_r3", "v4", "vec")}
b = runs["fix"][2]
print("1. DÒNG CHUYỂN NHÓM NULL, baseline → cấu hình (phán quyết đa số 3 lượt chấm, 65 câu)")
print("   cấu hình | acc giữ | acc→err | acc→nei | err/nei→acc | nei→err | err→nei | Null neither (đa số): baseline → cấu hình")
for t in ("v1", "v2", "v3", "v3_r2", "v3_r3", "v4", "vec"):
    m = runs[t][2]; c = collections.Counter((b[q], m[q]) for q in null)
    nb = sum(b[q] == "neither" for q in null); nr = sum(m[q] == "neither" for q in null)
    print(f"   {t:7s} | {c[('accurate','accurate')]:7d} | {c[('accurate','error')]:7d} | {c[('accurate','neither')]:7d} | "
          f"{c[('error','accurate')] + c[('neither','accurate')]:11d} | {c[('neither','error')]:7d} | {c[('error','neither')]:7d} | {nb} → {nr}")
print("\n2. KIỂU CÂU TRẢ LỜI CHO CÂU NULL × PHIẾU CHẤM (mọi lượt chấm; regex)")
for t in ("fix", "v3", "v3_r2", "v3_r3", "vec"):
    ans, votes, maj = runs[t]
    by = collections.defaultdict(collections.Counter); nq = collections.Counter(); split = collections.Counter()
    for q in null:
        k = kind(ans.get(q, "")); nq[k] += 1; by[k].update(votes[q])
        if {"accurate", "neither"} <= set(votes[q]): split[k] += 1
    cells = []
    for k in ("từ chối thuần", "từ chối rồi suy đoán", "khẳng định (không mở đầu bằng từ chối)"):
        v = by[k]; n = sum(v.values()) or 1
        cells.append(f"{k}: {nq[k]} câu, acc {100*v['accurate']/n:.0f}% / err {100*v['error']/n:.0f}% / nei {100*v['neither']/n:.0f}%, phiếu tách acc–nei {split[k]} câu")
    print(f"   {t}:\n     " + "\n     ".join(cells))
print("\n3. CÂU MẤT accurate → neither: thuộc kiểu nào, phiếu có tách không")
for t in ("v3", "v3_r2", "v3_r3", "vec"):
    ans, votes, maj = runs[t]
    moved = [q for q in null if b[q] == "accurate" and maj[q] == "neither"]
    kinds = collections.Counter(kind(ans[q]) for q in moved)
    print(f"   {t}: {len(moved)} câu · {dict(kinds)} · phiếu không đồng nhất {sum(len(set(votes[q])) > 1 for q in moved)}")
print("\n4. TẦNG B/C: 20 câu Null của dev 200 có trùng câu trả lời canary không")
dev_null = {r["Question"] for r in csv.DictReader(open("logs/devset.csv", encoding="utf-8")) if r["Type"] == "Null"}
for v in ("b1", "b2"):
    recs = collections.defaultdict(list)
    for l in open(f"logs/screening/{v}/answers.jsonl", encoding="utf-8"):
        if l.strip():
            r = json.loads(l); recs[r["question"]].append(r["answer"])
    same = sum(1 for q in dev_null if len(recs[q]) >= 2 and len(set(recs[q])) == 1)
    print(f"   {v}: {len(dev_null)} câu Null dev · {sum(1 for q in dev_null if len(recs[q]) >= 2)} câu có bản ghi canary + dev · câu trả lời giống hệt {same}")
