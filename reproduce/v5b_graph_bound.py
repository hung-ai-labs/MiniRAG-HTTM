import csv, json, re, collections
import networkx as nx
ROOT="LiHua-World-qwen-modal"
qs={r["Question"]:r for r in csv.DictReader(open("dataset/LiHua-World/qa/query_set.csv"))}
ans={r["Question"]:r["minirag"] for r in csv.DictReader(open("logs/qwen637_v3.csv"))}
votes=collections.defaultdict(list)
for r in csv.DictReader(open("logs/qwen637_v3_judged.csv")): votes[r["question"]].append(r["verdict"])
maj={q:collections.Counter(v).most_common(1)[0][0] for q,v in votes.items()}
Q=[q for q in maj if q in ans and q in qs]; typ={q:qs[q]["Type"] for q in Q}
chunks=json.load(open(f"{ROOT}/kv_store_text_chunks.json")); cids=list(chunks)
norm=lambda s: re.sub(r"[^a-z0-9]","",s.lower())
time2cid=collections.defaultdict(set)
for c in cids:
    m=re.match(r"Time:\s*(\d{8}_\d{2}:\d{2})",chunks[c]["content"])
    if m: time2cid[m.group(1)].add(c)
G=nx.read_graphml(f"{ROOT}/graph_chunk_entity_relation.graphml")
KEEP={"PERSON","ORGANIZATION","LOCATION","PRODUCT","GAME","TECHNOLOGY","EVENT","FOOD ITEM","INGREDIENT"}
nodes={}
for n,d in G.nodes(data=True):
    k=norm(n)
    if len(k)>=5 and d.get("entity_type","").strip('"') in KEEP: nodes.setdefault(k,[]).append(n)
mn=lambda t:{n for k,ns in nodes.items() if k in norm(t) for n in ns}
esrc=lambda u,v:set(G.edges[u,v].get("source_id","").split("<SEP>"))
NN_ACC=[q for q in Q if typ[q]!="Null" and maj[q]=="accurate"]
cov=collections.Counter()
for q in NN_ACC:
    gold=set()
    for t in qs[q]["Evidence"].split("<and>"): gold|=time2cid.get(t.strip(),set())
    if not gold: continue
    qn=mn(q); an=mn(ans[q])-qn; cov["n"]+=1
    # graph support restricted to edges whose provenance is a gold chunk
    H=nx.Graph([(u,v) for u,v in G.edges() if esrc(u,v)&gold])
    d1=any(H.has_edge(x,y) for x in qn for y in an)
    d2=d1 or any(x in H and y in H and nx.has_path(H,x,y) and nx.shortest_path_length(H,x,y)<=2 for x in qn for y in an)
    anyq=any(x in H for x in qn)
    cov["1hop"]+=d1; cov["<=2hop"]+=d2; cov["q_node_touches_gold_edge"]+=anyq
    yn=bool(re.match(r"^(did|does|do|is|was|were|are|has|have|had|will|can|could)\b",q,re.I))
    cov["yesno"]+=yn; cov["1hop_nonyesno"]+=d1 and not yn; cov["nonyesno"]+=not yn
print("V5b upper bound: correct non-Null answers whose q-entity -> a-entity link is backed by a GOLD-provenance edge")
for k in ("1hop","<=2hop","q_node_touches_gold_edge"): print(f"  {k:<26} {cov[k]}/{cov['n']} = {cov[k]/cov['n']*100:.1f}%")
print(f"  1hop among non-yes/no      {cov['1hop_nonyesno']}/{cov['nonyesno']};  yes/no questions {cov['yesno']} (answer 'Yes/No' has no answer entity)")
# label-noise probe: best chunk for selected Null-error answers
probes={"window size":["150","120","window"],"Central Perk":["central perk"],"New Year's Eve":["star wars","new year"],
        "anniversary event":["sourdough","anniversary"],"protein supplements":["whey","protein"],"favorite type of exercise":["pull-up","favorite"]}
print("\nLabel-noise probe (chunks containing all probe terms)")
for key,terms in probes.items():
    q=next(q for q in Q if typ[q]=="Null" and maj[q]=="error" and key.lower() in q.lower())
    hits=[c for c in cids if all(t in chunks[c]["content"].lower() for t in terms)]
    print(f"- Q: {q[:110]}\n  terms {terms}: {len(hits)} chunk(s)")
    for c in hits[:2]:
        t=chunks[c]["content"]; i=max(0,t.lower().find(terms[0])-160)
        print("   ", t[:22].replace("\n"," "), "…", t[i:i+320].replace("\n"," | "))
