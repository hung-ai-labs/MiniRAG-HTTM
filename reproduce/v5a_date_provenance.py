"""V5a narrow rule: every date the answer cites must be a chunk date whose text contains one of the
answer's own (non-question) content units. Corpus-level, so it flags at most what a Sources-level rule would miss."""
import csv, json, re, collections
qs={r["Question"]:r for r in csv.DictReader(open("dataset/LiHua-World/qa/query_set.csv"))}
ans={r["Question"]:r["minirag"] for r in csv.DictReader(open("logs/qwen637_v3.csv"))}
votes=collections.defaultdict(list)
for r in csv.DictReader(open("logs/qwen637_v3_judged.csv")): votes[r["question"]].append(r["verdict"])
maj={q:collections.Counter(v).most_common(1)[0][0] for q,v in votes.items()}
Q=[q for q in maj if q in ans and q in qs]; typ={q:qs[q]["Type"] for q in Q}
chunks=json.load(open("LiHua-World-qwen-modal/kv_store_text_chunks.json"))
bydate=collections.defaultdict(str)
for c in chunks.values():
    m=re.match(r"Time:\s*(\d{8})",c["content"]); 
    if m: bydate[m.group(1)]+=" "+c["content"].lower()
MON={m:i+1 for i,m in enumerate("january february march april may june july august september october november december".split())}
def dates(t):
    out=set(re.findall(r"\b(20\d{6})(?:_\d{2}:\d{2})?\b",t))
    for mo,d,y in re.findall(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d\d)",t):
        out.add(f"{y}{MON[mo.lower()]:02d}{int(d):02d}")
    return out
STOP=set("based during however additionally specifically this there from according their these those overall therefore also while when after before regarding although given source sources conversation conversations recorded provided data li hua lihua".split())
def units(t, q):
    ql=q.lower(); u=set()
    for m in re.findall(r"\b[A-Z][A-Za-z'’]+(?:\s+[A-Z][A-Za-z'’]+)*|\b\d+(?:\.\d+)?\b|[\"“][^\"”]{3,60}[\"”]",t):
        m=m.strip('"“”'); w=m.lower()
        if len(w)>=3 and w not in STOP and w not in ql and not re.fullmatch(r"20\d{6}|\d{1,2}|20\d\d",w): u.add(w)
    return u
cnt=collections.Counter(); ex=[]
for q in Q:
    a=ans[q]; D=dates(a)
    if not D: continue
    cls=("Null-" if typ[q]=="Null" else "nonNull-")+maj[q]; cnt[cls+" cites_date"]+=1
    U=units(a,q)
    bad=[d for d in D if not bydate.get(d) or not any(u in bydate[d] for u in U)]
    if bad:
        cnt[cls+" FLAG"]+=1
        if typ[q]=="Null" or maj[q]=="accurate": ex.append((cls,sorted(bad)[:2],q[:80]))
tot=collections.Counter(("Null-" if typ[q]=="Null" else "nonNull-")+maj[q] for q in Q)
for k in sorted(tot): print(f"{k:<20} n={tot[k]:>3}  cites a date {cnt[k+' cites_date']:>3}  flagged {cnt[k+' FLAG']:>3}")
print("\nflagged examples (Null or nonNull-accurate):")
for e in ex[:14]: print(" ",e)
