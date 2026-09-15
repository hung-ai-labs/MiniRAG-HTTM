"""Phân loại tự động 32 câu Null từng bị chấm error (lượt đã có; không dữ liệu tầng D). Heuristic — cần người rà các câu nghi nhãn sai."""
import csv, json, re, collections, math, sys
sys.path.insert(0, ".")
from minirag.bm25 import STOP
HEDGE = re.compile(r"not (explicitly |specifically |directly )?(mention|state|specif|provide|detail|clear)|no (specific|particular|explicit|direct) (mention|information|detail|type|brand|record|comparison)|isn'?t (a )?(direct |explicit )?mention|there is no (information|mention|record|specific)|there isn'?t|does not (say|specify|mention|indicate)|doesn'?t (say|specify|mention|indicate)|unclear|no information", re.I)
qs = list(csv.DictReader(open("dataset/LiHua-World/qa/query_set.csv", encoding="utf-8")))
null = list(dict.fromkeys(r["Question"] for r in qs if r["Type"] == "Null"))
dev = {r["Question"] for r in csv.DictReader(open("logs/devset.csv", encoding="utf-8"))}
raw = json.load(open("LiHua-World-qwen-modal/kv_store_text_chunks.json", encoding="utf-8"))
cw = {k: set(re.findall(r"[a-z0-9]+", v["content"].lower())) for k, v in raw.items()}
df = collections.Counter(w for s in cw.values() for w in s)
tok = lambda s: {w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in STOP and len(w) >= 3}
IMPROVED = ("v3", "v3_r2", "v3_r3", "vec", "devV3", "devB1", "devB2")
errs, answers = collections.defaultdict(list), collections.defaultdict(dict)
for tag in ("fix", "v3", "v3_r2", "v3_r3", "vec"):
    ans = {r["Question"]: r["minirag"] for r in csv.DictReader(open(f"logs/qwen637_{tag}.csv", encoding="utf-8"))}
    votes = collections.defaultdict(list)
    for r in csv.DictReader(open(f"logs/qwen637_{tag}_judged.csv", encoding="utf-8")):
        votes[r["question"]].append(r["verdict"])
    for q in null:
        if q in votes and collections.Counter(votes[q]).most_common(1)[0][0] == "error":
            errs[q].append(tag); answers[q][tag] = ans.get(q, "")
def jl(p):
    d = {}
    for l in open(p, encoding="utf-8"):
        if l.strip():
            r = json.loads(l); d[r["question"]] = r
    return d
fz = jl("logs/screening/frozen/v3.jsonl")
for tag, path in (("devV3", None), ("devB1", "logs/screening/b1/answers.jsonl"), ("devB2", "logs/screening/b2/answers.jsonl")):
    a = jl(path) if path else {}
    for q in null:
        if q in fz:
            rec = a.get(q) or fz[q]
            if rec["verdict"] == "error":
                errs[q].append(tag); answers[q][tag] = rec["answer"]
cat = collections.Counter(); rows = []
for q in errs:
    hedged_runs = [t for t, a in answers[q].items() if HEDGE.search(a)]
    Q = tok(q)
    # nghi nhãn sai: một chunk phủ ≥ 50% từ câu hỏi VÀ chứa ≥ 2 từ hiếm (df ≤ 3) chỉ có trong câu trả lời (ở ≥ 1 lượt sai)
    susp = []
    for t, a in answers[q].items():
        rare = {w for w in tok(a) - Q if df.get(w, 0) and df[w] <= 3 and len(w) >= 4}
        for cid, s in cw.items():
            if len(Q & s) / max(1, len(Q)) >= 0.5 and len(rare & s) >= 2:
                susp.append((t, cid, sorted(rare & s)))
    new = "fix" not in errs[q]
    kind = "nghi nhãn sai" if susp else ("rào đón bị chấm error" if hedged_runs and len(hedged_runs) == len(answers[q]) else "tiền đề không có thật / ghép chi tiết lân cận")
    cat[(kind, "mới ở lượt cải tiến" if new else "có từ baseline")] += 1
    rows.append((q, errs[q], new, kind, hedged_runs, susp[:2]))
print("PHÂN LOẠI 32 câu Null từng bị chấm error:")
for (kind, origin), n in sorted(cat.items()):
    print(f"  {n:2d} × {kind} · {origin}")
print(f"\ncâu có ≥ 1 lượt rào đón bị chấm error: {sum(1 for r in rows if r[4])} · lượt error có rào đón / tổng lượt error: "
      f"{sum(len(r[4]) for r in rows)}/{sum(len(r[1]) for r in rows)}")
print("\nCÂU NGHI NHÃN SAI (cần người đọc chunk):")
for q, e, new, kind, h, susp in rows:
    if kind == "nghi nhãn sai":
        print(f"- [{'dev' if q in dev else 'ngoài dev'}; sai ở {','.join(e)}] {q[:120]}")
        for t, cid, words in susp:
            text = raw[cid]["content"]; tm = re.search(r"Time:\s*(\S+)", text)
            line = max(re.split(r"\n|(?<=[.!?])\s+", text), key=lambda l: sum(w in l.lower() for w in words))
            print(f"    {t} · chunk {tm.group(1) if tm else cid[:12]} · từ khớp {words[:6]} · «{line.strip()[:200]}»")
