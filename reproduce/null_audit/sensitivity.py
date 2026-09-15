"""Độ nhạy Null trên 637 câu (phán quyết đa số 3 lượt chấm): bỏ câu nhãn sai, rồi coi câu rào đón bị chấm error là neither.
Chỉ để kiểm thước đo — KHÔNG thay số chính thức."""
import csv, re, collections, sys
HEDGE = re.compile(r"not (explicitly |specifically |directly )?(mention|state|specif|provide|detail|clear)|no (specific|particular|explicit|direct) (mention|information|detail|type|brand|record|comparison)|isn'?t (a )?(direct |explicit )?mention|there is no (information|mention|record|specific)|there isn'?t|does not (say|specify|mention|indicate)|doesn'?t (say|specify|mention|indicate)|unclear|no information", re.I)
qs = list(csv.DictReader(open("dataset/LiHua-World/qa/query_set.csv", encoding="utf-8")))
null = list(dict.fromkeys(r["Question"] for r in qs if r["Type"] == "Null"))
WIN = "What specific measurements did Li Hua take for the window size before the installation of the curtain?"
BAK = "What flavor of new bread products did Li Hua really enjoy at the bakery's anniversary event?"
YUR = [q for q in null if q.startswith("What specific feedback did Yuriko give to Li Hua about the demo website")][0]
sets = {"chính thức": set(), "bỏ 1 (cửa sổ)": {WIN}, "bỏ 3 (cửa sổ, bánh, Yuriko)": {WIN, BAK, YUR}}
print("Null acc / err / neither — phán quyết đa số, 637 câu")
for tag in ("fix", "v3", "v3_r2", "v3_r3", "vec"):
    ans = {r["Question"]: r["minirag"] for r in csv.DictReader(open(f"logs/qwen637_{tag}.csv", encoding="utf-8"))}
    votes = collections.defaultdict(list)
    for r in csv.DictReader(open(f"logs/qwen637_{tag}_judged.csv", encoding="utf-8")):
        votes[r["question"]].append(r["verdict"])
    maj = {q: collections.Counter(v).most_common(1)[0][0] for q, v in votes.items()}
    cells = []
    for name, excl in sets.items():
        qq = [q for q in null if q in maj and q not in excl]; c = collections.Counter(maj[q] for q in qq)
        cells.append(f"{name}: {100*c['accurate']/len(qq):.1f} / {100*c['error']/len(qq):.1f} / {100*c['neither']/len(qq):.1f} (n={len(qq)})")
    qq = [q for q in null if q in maj and q not in sets["bỏ 3 (cửa sổ, bánh, Yuriko)"]]
    adj = collections.Counter(("neither" if maj[q] == "error" and HEDGE.search(ans.get(q, "")) else maj[q]) for q in qq)
    cells.append(f"bỏ 3 + rào đón → neither: {100*adj['accurate']/len(qq):.1f} / {100*adj['error']/len(qq):.1f} / {100*adj['neither']/len(qq):.1f}")
    print(f"{tag}: " + " · ".join(cells))
