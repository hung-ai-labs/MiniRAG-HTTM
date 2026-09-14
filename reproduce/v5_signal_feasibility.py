"""Offline feasibility of V5a/V5b/V5c signals on V3's real answers. Labels (Type, verdict,
Evidence) are used ONLY to score signals, never to compute them."""
import csv, json, re, collections, random, os
import numpy as np, networkx as nx
os.environ["HF_HUB_OFFLINE"] = "1"
random.seed(0)
ROOT = "LiHua-World-qwen-modal"
qs = {r["Question"]: r for r in csv.DictReader(open("dataset/LiHua-World/qa/query_set.csv"))}
ans = {r["Question"]: r["minirag"] for r in csv.DictReader(open("logs/qwen637_v3.csv"))}
votes = collections.defaultdict(list)
for r in csv.DictReader(open("logs/qwen637_v3_judged.csv")):
    votes[r["question"]].append(r["verdict"])
maj = {q: collections.Counter(v).most_common(1)[0][0] for q, v in votes.items()}
Q = [q for q in maj if q in ans and q in qs]
typ = {q: qs[q]["Type"] for q in Q}
chunks = json.load(open(f"{ROOT}/kv_store_text_chunks.json"))
cids = list(chunks); ctext = [chunks[c]["content"] for c in cids]; ctok = [chunks[c]["tokens"] for c in cids]
norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
corpus_norm = norm(" ".join(ctext))
corpus_vocab = set(re.findall(r"[a-z]{4,}", " ".join(ctext).lower()))
time2cid = collections.defaultdict(set)
for c, t in zip(cids, ctext):
    m = re.match(r"Time:\s*(\d{8}_\d{2}:\d{2})", t)
    if m: time2cid[m.group(1)].add(c)

# ---------- V5a: deterministic units ----------
STOP = set("""based in the during however additionally specifically this there from according on at
it they he she his her their these those overall therefore first firstly secondly finally also while
when after before regarding although given in as for a an and but so if yes no not source sources
conversation conversations data table entities relationships lihua li hua""".split())
def units(a):
    u = set()
    u |= {x for x in re.findall(r"\d[\d,.:/]*\d|\d", a)}
    u |= {x.strip() for x in re.findall(r"[\"“]([^\"”]{3,80})[\"”]", a)}
    for m in re.findall(r"\b[A-Z][A-Za-z'’]+(?:\s+[A-Z][A-Za-z'’]+)*", a):
        w = [t for t in m.split() if t.lower() not in STOP]
        if w and len(norm(" ".join(w))) >= 4: u.add(" ".join(w))
    return {x for x in u if norm(x)}
T1 = re.compile(r"\b(no|not any|isn'?t any|aren'?t any)\s+(explicit|specific|direct|clear|further)?\s*(mention|information|details?|record|indication|evidence)"
                r"|\bnot\s+(explicitly|specifically|directly|clearly)?\s*(mentioned|stated|detailed|specified|provided|discussed|recorded|indicated|available)"
                r"|\bdoes(?: not|n'?t) (specify|mention|state|contain|provide|indicate)|\binsufficient information", re.I)
T2 = re.compile(r"\b(likely|probably|presumably|possibly|it can be inferred|can be inferred|appears? to|seems?|might|may have|suggesting that)\b", re.I)

# ---------- V5b: graph ----------
G = nx.read_graphml(f"{ROOT}/graph_chunk_entity_relation.graphml")
KEEP = {"PERSON","ORGANIZATION","LOCATION","PRODUCT","GAME","TECHNOLOGY","EVENT","FOOD ITEM","INGREDIENT"}
nodes = {}
for n, d in G.nodes(data=True):
    k = norm(n)
    if len(k) >= 5 and d.get("entity_type","").strip('"') in KEEP:
        nodes.setdefault(k, []).append(n)
def match_nodes(text):
    t = norm(text); return {n for k, ns in nodes.items() if k in t for n in ns}
node_chunks = {n: set(G.nodes[n].get("source_id","").split("<SEP>")) for n in G}

# ---------- V5c: MiniLM ----------
from sentence_transformers import SentenceTransformer
emb = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device="cpu")
E_c = emb.encode(ctext, normalize_embeddings=True, batch_size=64)
E_q = emb.encode(Q, normalize_embeddings=True, batch_size=64)
E_a = emb.encode([ans[q] for q in Q], normalize_embeddings=True, batch_size=64)

F = collections.defaultdict(dict); diag = collections.defaultdict(dict)
for i, q in enumerate(Q):
    a = ans[q]
    # vector-half proxy of Sources: vector ranking filled to the 4000-token A1 budget
    order = np.argsort(-(E_c @ E_q[i])); prox, tok = [], 0
    for j in order:
        if tok + ctok[j] > 4000: break
        prox.append(j); tok += ctok[j]
    prox_norm = norm(" ".join(ctext[j] for j in prox))
    U = units(a)
    F["a_units_absent_corpus"][q] = (sum(norm(u) not in corpus_norm for u in U) / len(U)) if U else 0.0
    F["a_units_absent_vecproxy"][q] = (sum(norm(u) not in prox_norm for u in U) / len(U)) if U else 0.0
    words = {w for w in re.findall(r"[a-z]{4,}", a.lower())} - set(re.findall(r"[a-z]{4,}", q.lower()))
    F["a_words_absent_corpus"][q] = (sum(w not in corpus_vocab for w in words) / len(words)) if words else 0.0
    F["hedge_absence_T1"][q] = len(T1.findall(a))
    F["hedge_speculative_T2"][q] = len(T2.findall(a))
    qn = match_nodes(q); an = match_nodes(a) - qn
    F["g_no_question_node"][q] = float(not qn)
    F["g_no_direct_edge_q_to_a"][q] = float(not any(G.has_edge(x, y) for x in qn for y in an))
    qc = set().union(*[node_chunks[x] for x in qn]) if qn else set()
    ac = set().union(*[node_chunks[y] for y in an]) if an else set()
    F["g_no_shared_chunk_q_a"][q] = float(not (qc & ac))
    F["m_neg_answer_to_best_chunk"][q] = -float((E_c @ E_a[i]).max())
    F["m_neg_answer_to_vecproxy"][q] = -float((E_c[prox] @ E_a[i]).max())
    F["m_neg_query_to_best_chunk"][q] = -float((E_c @ E_q[i]).max())
    F["m_answer_query_cos"][q] = float(E_a[i] @ E_q[i])
    diag["n_units"][q] = len(U); diag["n_qnodes"][q] = len(qn); diag["n_anodes"][q] = len(an)
    gold = set()
    for t in re.split(r"<and>", qs[q]["Evidence"]):
        gold |= time2cid.get(t.strip(), set())
    diag["gold_in_qnode_chunks"][q] = bool(gold & qc) if gold else None
    diag["gold_in_vecproxy"][q] = bool(gold & {cids[j] for j in prox}) if gold else None
    diag["direct_edge_with_gold_provenance"][q] = any(G.has_edge(x, y) and gold & set(G.edges[x, y].get("source_id","").split("<SEP>")) for x in qn for y in an) if gold else None

def auc(pos, neg):
    s = 0.0
    for p in pos:
        for n in neg: s += 1.0 if p > n else 0.5 if p == n else 0.0
    return s / (len(pos) * len(neg))
def boot(pos, neg, B=500):
    v = sorted(auc(random.choices(pos, k=len(pos)), random.choices(neg, k=len(neg))) for _ in range(B))
    return v[int(.025*B)], v[int(.975*B)]
grp = lambda t, v: [q for q in Q if (typ[q] == "Null") == (t == "Null") and maj[q] in v]
NULL_ERR = grp("Null", {"error"}); NULL_BAD = grp("Null", {"error","neither"})
NN_ACC = grp("x", {"accurate"}); NN_ERR = grp("x", {"error"})
print(f"classes: Null-error {len(NULL_ERR)}, Null-error+neither {len(NULL_BAD)}, nonNull-accurate {len(NN_ACC)}, nonNull-error {len(NN_ERR)}")
print(f"\n{'signal (higher = more suspicious)':<34}{'AUC NullErr/NNacc':>20}{'95% CI':>14}{'AUC NNerr/NNacc':>17}{'oracle net':>12}{'FAR@best':>10}")
for f, vals in F.items():
    pos = [vals[q] for q in NULL_ERR]; neg = [vals[q] for q in NN_ACC]
    lo, hi = boot(pos, neg)
    # label-optimised threshold = optimistic upper bound on net accuracy change
    best = (0, 0.0)
    for t in sorted(set(vals.values())):
        tp = sum(vals[q] >= t for q in NULL_BAD); fp = sum(vals[q] >= t for q in NN_ACC)
        if tp - fp > best[0]: best = (tp - fp, fp / len(NN_ACC))
    print(f"{f:<34}{auc(pos,neg):>20.3f}{f'[{lo:.2f},{hi:.2f}]':>14}{auc([vals[q] for q in NN_ERR],neg):>17.3f}{best[0]:>+12d}{best[1]*100:>9.1f}%")
names = list(F); M = np.array([[F[f][q] for q in Q] for f in names])
from scipy.stats import spearmanr
rho = spearmanr(M.T).correlation
print("\nSpearman |rho| >= 0.3 pairs:")
for i in range(len(names)):
    for j in range(i+1, len(names)):
        if abs(rho[i,j]) >= 0.3: print(f"  {names[i]} ~ {names[j]}: {rho[i,j]:+.2f}")
def rate(key, qset):
    vals = [diag[key][q] for q in qset if diag[key][q] is not None]; return f"{sum(vals)}/{len(vals)}"
print("\nDIAGNOSTIC (gold Evidence, evaluation only)")
for k in ("gold_in_qnode_chunks","gold_in_vecproxy","direct_edge_with_gold_provenance"):
    print(f"  {k:<36} nonNull-accurate {rate(k, NN_ACC):>9}   nonNull-error {rate(k, NN_ERR):>9}")
for k in ("n_units","n_qnodes","n_anodes"):
    med = lambda s: sorted(diag[k][q] for q in s)[len(s)//2]
    zero = lambda s: sum(diag[k][q] == 0 for q in s)
    print(f"  {k:<12} median NullErr {med(NULL_ERR)} / NNacc {med(NN_ACC)};  zero: NullErr {zero(NULL_ERR)}/{len(NULL_ERR)}, NNacc {zero(NN_ACC)}/{len(NN_ACC)}")
yn = re.compile(r"^(did|does|do|is|was|were|are|has|have|had|will|can|could)\b", re.I)
print("  yes/no questions among nonNull-accurate:", sum(bool(yn.match(q)) for q in NN_ACC), "| among Null:", sum(bool(yn.match(q)) for q in Q if typ[q]=="Null"))
print("\nNull-error answers: units absent from corpus")
for q in NULL_ERR:
    U = units(ans[q]); miss = [u for u in U if norm(u) not in corpus_norm]
    print(f"  {len(miss)}/{len(U)} {miss[:5]}  T1={F['hedge_absence_T1'][q]} | {q[:70]}")
