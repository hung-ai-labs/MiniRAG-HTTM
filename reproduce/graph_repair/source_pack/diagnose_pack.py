"""B1 - chẩn đoán L3/L2 từ log, chỉ đọc. Gold chỉ là nhãn chẩn đoán/đánh giá, không đi vào cơ chế.

Chạy từ gốc repo (offline):
  $env:TIKTOKEN_CACHE_DIR="$PWD\\data-gym-cache"
  .\\.venv\\Scripts\\python.exe -I reproduce\\graph_repair\\source_pack\\diagnose_pack.py
"""
import json
import os
import statistics as st
import sys
from collections import Counter, defaultdict

import networkx as nx
import tiktoken

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
BUDGET = 4000
DIAG = os.path.join(ROOT, "logs", "graph_repair", "p_pack", "c0_diag", "diag.jsonl")
GOLD = os.path.join(ROOT, "logs", "diag_path2chunk.jsonl")
INDEX = os.path.join(ROOT, "LiHua-World-qwen-modal")
OUT = os.path.join(ROOT, "logs", "graph_repair", "p_pack", "diagnosis.json")
ENC = tiktoken.encoding_for_model("gpt-4o")


def jl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def med(x):
    return round(st.median(x), 2) if x else None


# ---------------------------------------------------------------- nạp dữ liệu
store = json.load(open(os.path.join(INDEX, "kv_store_text_chunks.json"), encoding="utf-8"))
TOK = {c: len(ENC.encode(v["content"])) for c, v in store.items()}
gold = {}
for r in jl(GOLD):
    if r.get("gold"):
        gold[r["question"]] = (r["gold"], r.get("type"))
diag = {d["query"]: d for d in jl(DIAG)}
qs = [q for q in diag if q in gold]

G = nx.read_graphml(os.path.join(INDEX, "graph_chunk_entity_relation.graphml"))
degs = sorted(d for _, d in G.degree())
HUB5 = degs[int(0.95 * len(degs))]
print(f"graph {G.number_of_nodes()} node; hub top-5% = bậc >= {HUB5}")


def is_hub(seed):
    return seed in G and G.degree(seed) >= HUB5


# ---------------------------------------------------------------- tái dựng từng câu
def a1_prefix(order):
    """Đúng truncate_list_by_token_size: dừng ở chunk đầu tiên làm tràn."""
    used, kept = 0, []
    for c in order:
        if used + TOK[c] > BUDGET:
            break
        used += TOK[c]
        kept.append(c)
    return kept, used


def a1_firstfit(order):
    used, kept = 0, []
    for c in order:
        if used + TOK[c] <= BUDGET:
            used += TOK[c]
            kept.append(c)
    return kept, used


recs = {}
for q in qs:
    d = diag[q]
    order = [c for c in d["graph_ids"] if c in TOK]
    kept, used = a1_prefix(order)
    assert kept == d["chunk_ids"], f"không tái dựng được A1: {q}"
    G_ids, typ = gold[q]
    cand = set(d["contributions"])
    score = {c: sum(x["contribution"] for x in v) for c, v in d["contributions"].items()}
    kw = {c: sorted({x["keyword"] for x in v}) for c, v in d["contributions"].items()}
    domkw = {}
    for c, v in d["contributions"].items():
        per = Counter()
        for x in v:
            per[x["keyword"]] += x["contribution"]
        domkw[c] = per.most_common(1)[0][0]
    ks = set(kept)
    inorder = set(order)
    lay = {}
    for g in G_ids:
        if g in ks:
            lay[g] = "OK"
        elif g in inorder:
            lay[g] = "L3"
        elif g in cand:
            lay[g] = "L2"
        else:
            lay[g] = "L1/L0"
    recs[q] = dict(d=d, order=order, kept=kept, used=used, G=G_ids, type=typ, cand=cand, score=score,
                   kw=kw, domkw=domkw, lay=lay, full=all(v == "OK" for v in lay.values()))

full = [q for q in qs if recs[q]["full"]]
L3q = [q for q in qs if any(v == "L3" for v in recs[q]["lay"].values())]
L2q = [q for q in qs if any(v == "L2" for v in recs[q]["lay"].values())]
print(f"{len(qs)} câu; đủ đáp án {len(full)}; có chunk L3 {len(L3q)}; có chunk L2 {len(L2q)}")
cnt = Counter(v for q in qs for v in recs[q]["lay"].values())
print("chunk theo tầng:", dict(cnt))

R = {"n": len(qs), "full": len(full), "L3_questions": len(L3q), "L2_questions": len(L2q),
     "layers": dict(cnt), "hub5_degree": HUB5}

# ---------------------------------------------------------------- Q1: ngân sách bị lãng phí
def q1():
    out = {}
    slack, fits, over_tok = [], 0, []
    fits_all = 0
    ex = []
    for q in L3q:
        r = recs[q]
        sl = BUDGET - r["used"]
        slack.append(sl)
        lost = [g for g, v in r["lay"].items() if v == "L3"]
        nxt = r["order"][len(r["kept"])]  # chunk làm tràn
        over_tok.append(TOK[nxt])
        if any(TOK[g] <= sl for g in lost):
            fits += 1
        if all(TOK[g] <= sl for g in lost):
            fits_all += 1
    out["slack_median"] = med(slack)
    out["slack_min_max"] = [min(slack), max(slack)]
    out["overflow_chunk_tok_median"] = med(over_tok)
    out["L3_q_gold_fits_slack_any"] = fits
    out["L3_q_gold_fits_slack_all"] = fits_all
    out["L3_q_total"] = len(L3q)
    # đối chứng: 75 câu đủ đáp án
    out["full_slack_median"] = med([BUDGET - recs[q]["used"] for q in full])
    out["all_slack_median"] = med([BUDGET - recs[q]["used"] for q in qs])
    # gold chunk lost: token của nó
    gl = [TOK[g] for q in L3q for g, v in recs[q]["lay"].items() if v == "L3"]
    out["L3_gold_tok_median"] = med(gl)
    out["L3_gold_tok_p90"] = sorted(gl)[int(0.9 * len(gl))]
    # số chunk trong top30 / vào Sources
    out["n_order_median"] = med([len(recs[q]["order"]) for q in qs])
    out["n_kept_median"] = med([len(recs[q]["kept"]) for q in qs])
    return out


R["Q1"] = q1()

# ---------------------------------------------------------------- Q2: phía trên chunk đáp án
def q2():
    rows = []
    for q in L3q:
        r = recs[q]
        for g, v in r["lay"].items():
            if v != "L3":
                continue
            pos = r["order"].index(g)
            above = r["order"][:pos]
            tok = [TOK[c] for c in above]
            dom = Counter(r["domkw"].get(c) for c in above)
            top_kw, top_n = dom.most_common(1)[0] if dom else (None, 0)
            tok_by_kw = defaultdict(int)
            for c in above:
                tok_by_kw[r["domkw"].get(c)] += TOK[c]
            hub_tok = 0
            for c in above:
                best, bs = None, -1
                per = Counter()
                for x in r["d"]["contributions"][c]:
                    per[x["seed"]] += x["contribution"]
                best = per.most_common(1)[0][0]
                if is_hub(best):
                    hub_tok += TOK[c]
            rows.append(dict(
                q=q, rank=pos + 1, n_above=len(above), tok_above=sum(tok), max_above=max(tok) if tok else 0,
                long_above=sum(1 for t in tok if t >= 600),
                dom_kw_share_n=top_n / len(above) if above else 0,
                dom_kw_share_tok=max(tok_by_kw.values()) / sum(tok) if tok else 0,
                hub_share_tok=hub_tok / sum(tok) if tok else 0,
                gold_tok=TOK[g],
                # bỏ riêng chunk dài nhất phía trên rồi cắt lại tiền tố: chunk đáp án có vào Sources không
                fits_if_drop_longest=(g in a1_prefix([c for c in r["order"] if c != max(above, key=lambda x: TOK[x])])[0]) if above else None,
                # chunk phía trên cùng từ khoá chủ đạo với chunk đáp án
                same_dom_kw_as_gold=sum(1 for c in above if r["domkw"].get(c) == r["domkw"].get(g)),
            ))
    out = {"n_L3_gold": len(rows)}
    for k in ("rank", "n_above", "tok_above", "max_above", "long_above", "dom_kw_share_n",
              "dom_kw_share_tok", "hub_share_tok", "same_dom_kw_as_gold"):
        out[k + "_median"] = med([x[k] for x in rows])
    out["fits_if_drop_longest"] = sum(1 for x in rows if x["fits_if_drop_longest"])
    out["has_long_above(>=600)"] = sum(1 for x in rows if x["long_above"] > 0)
    out["same_kw_as_gold_ge1"] = sum(1 for x in rows if x["same_dom_kw_as_gold"] > 0)
    return out, rows


R["Q2"], q2rows = q2()

# ---------------------------------------------------------------- Q3: từ khoá
def kw_stats(r):
    kws = r["d"]["keywords"]
    in_src = Counter()
    for c in r["kept"]:
        for k in r["kw"][c]:
            in_src[k] += 1
    in_top30 = Counter()
    for c in r["order"]:
        for k in r["kw"][c]:
            in_top30[k] += 1
    return kws, in_src, in_top30


def q3():
    out = {}
    gold_kw_src, zero_total, zero_kw_gold = [], 0, 0
    cases = []
    for q in L3q + [x for x in L2q if x not in L3q]:
        r = recs[q]
        kws, in_src, in_top30 = kw_stats(r)
        for g, v in r["lay"].items():
            if v not in ("L3", "L2"):
                continue
            gk = r["kw"].get(g, [])
            gold_kw_src.append(min((in_src[k] for k in gk), default=0))
            cases.append(dict(q=q, layer=v, gold_kws=gk, src_per_gold_kw={k: in_src[k] for k in gk},
                              zero_kws=[k for k in kws if in_src[k] == 0]))
    out["n_cases"] = len(cases)
    out["gold_kw_min_chunks_in_sources_median"] = med(gold_kw_src)
    out["cases_gold_has_no_kw"] = sum(1 for c in cases if not c["gold_kws"])
    out["cases_any_gold_kw_has_0_in_sources"] = sum(1 for c in cases if any(v == 0 for v in c["src_per_gold_kw"].values()))
    out["cases_gold_kw_has_ge5_in_sources"] = sum(1 for c in cases if c["gold_kws"] and max(c["src_per_gold_kw"].values()) >= 5)
    # từ khoá không có chunk nào trong Sources, ở mọi câu
    nz, nk = 0, 0
    nz_L, nk_L = 0, 0
    nz_F, nk_F = 0, 0
    for q in qs:
        r = recs[q]
        kws, in_src, _ = kw_stats(r)
        z = sum(1 for k in kws if in_src[k] == 0)
        nz += z
        nk += len(kws)
        if q in L3q or q in L2q:
            nz_L += z
            nk_L += len(kws)
        if r["full"]:
            nz_F += z
            nk_F += len(kws)
    out["kw_zero_in_sources_all"] = f"{nz}/{nk}"
    out["kw_zero_in_sources_L"] = f"{nz_L}/{nk_L}"
    out["kw_zero_in_sources_full"] = f"{nz_F}/{nk_F}"
    out["q_with_zero_kw_L"] = sum(1 for q in set(L3q) | set(L2q) if any(kw_stats(recs[q])[1][k] == 0 for k in recs[q]["d"]["keywords"]))
    out["q_with_zero_kw_full"] = sum(1 for q in full if any(kw_stats(recs[q])[1][k] == 0 for k in recs[q]["d"]["keywords"]))
    return out, cases


R["Q3"], q3cases = q3()

# ---------------------------------------------------------------- Q4: so với câu đủ đáp án
def feat(q):
    r = recs[q]
    kws, in_src, in_top30 = kw_stats(r)
    toks = [TOK[c] for c in r["kept"]]
    tk = defaultdict(int)
    for c in r["kept"]:
        tk[r["domkw"].get(c)] += TOK[c]
    tot = sum(tk.values()) or 1
    return dict(
        n_kw=len(kws), n_kept=len(r["kept"]), slack=BUDGET - r["used"],
        max_tok_order=max(TOK[c] for c in r["order"]), med_tok_order=st.median(TOK[c] for c in r["order"]),
        top_kw_share=max(tk.values()) / tot if tk else 0,
        zero_kw_frac=sum(1 for k in kws if in_src[k] == 0) / max(1, len(kws)),
        n_distinct_dom_kw_kept=len({r["domkw"].get(c) for c in r["kept"]}),
        n_seeds_total=len(r["d"]["seeds"]),
    )


def q4():
    groups = {"full(75)": full, "L3|L2": sorted(set(L3q) | set(L2q)),
              "not_full_other": [q for q in qs if not recs[q]["full"] and q not in L3q and q not in L2q]}
    out = {}
    for name, g in groups.items():
        f = [feat(q) for q in g]
        out[name] = {"n": len(g), **{k: med([x[k] for x in f]) for k in f[0]}}
    return out


R["Q4"] = q4()

# ---------------------------------------------------------------- mô phỏng offline
def evaluate(name, picker, note=""):
    """picker(r) -> list chunk (đã cắt ngân sách). Gold chỉ để đo."""
    n_full = gain = lost = 0
    gold_kept = 0
    fullset = set(full)
    toks, jacc = [], []
    for q in qs:
        r = recs[q]
        kept = picker(r)
        ks = set(kept)
        ok = all(g in ks for g in r["G"])
        n_full += ok
        gold_kept += sum(1 for g in r["G"] if g in ks)
        if ok and not r["full"]:
            gain += 1
        if r["full"] and not ok:
            lost += 1
        toks.append(sum(TOK[c] for c in kept))
        j = len(ks & set(r["kept"])) / max(1, len(ks | set(r["kept"])))
        jacc.append(j)
    tot = sum(len(recs[q]["G"]) for q in qs)
    row = dict(name=name, full_q=n_full, gold_kept=f"{gold_kept}/{tot}", q_up=gain, q_down=lost,
               tok_median=med(toks), jaccard_vs_C0_median=med(jacc), note=note)
    SIM.append(row)
    return row


SIM = []


def pick_C0(r):
    return r["kept"]


def pick_firstfit(r):
    return a1_firstfit(r["order"])[0]


def keyword_round(r, pool):
    """Mỗi từ khoá lấy chunk hạng cao nhất của nó (theo thứ tự điểm toàn cục), rồi phần còn lại theo hạng."""
    order = list(pool)
    chosen, seen = [], set()
    for k in r["d"]["keywords"]:
        for c in order:
            if c not in seen and k in r["kw"].get(c, []):
                chosen.append(c)
                seen.add(c)
                break
    rest = [c for c in order if c not in seen]
    return chosen + rest


def pick_cov_prefix(r):
    return a1_prefix(keyword_round(r, r["order"]))[0]


def pick_cov_firstfit(r):
    return a1_firstfit(keyword_round(r, r["order"]))[0]


def density_order(r, pool):
    return sorted(pool, key=lambda c: -r["score"][c] / TOK[c])


def pick_dens_prefix(r):
    return a1_prefix(density_order(r, r["order"]))[0]


def pick_dens_firstfit(r):
    return a1_firstfit(density_order(r, r["order"]))[0]


def pick_dens_stable(r):
    """Giữ thứ tự điểm; chỉ xếp lại bằng mật độ khi chunk làm tràn."""
    used, kept = 0, []
    for c in r["order"]:
        if used + TOK[c] <= BUDGET:
            kept.append(c)
            used += TOK[c]
    return kept


def pool_all(r):
    # mọi ứng viên (không cắt top 30), theo điểm
    allc = sorted((c for c in r["cand"] if c in TOK), key=lambda c: -r["score"][c])
    return allc


def pick_cov_all_prefix(r):
    return a1_prefix(keyword_round(r, pool_all(r)))[0]


def pick_cov_dens(r):
    """Phủ từ khoá trước (mỗi từ khoá lấy chunk điểm/token cao nhất), rồi phần còn lại theo mật độ; first-fit."""
    order = list(r["order"])
    chosen, seen = [], set()
    for k in r["d"]["keywords"]:
        best = None
        for c in order:
            if c in seen or k not in r["kw"].get(c, []):
                continue
            if best is None or r["score"][c] / TOK[c] > r["score"][best] / TOK[best]:
                best = c
        if best is not None:
            chosen.append(best)
            seen.add(best)
    rest = sorted((c for c in order if c not in seen), key=lambda c: -r["score"][c] / TOK[c])
    return a1_firstfit(chosen + rest)[0]


def pick_cov_dens_prefixcut(r):
    order = list(r["order"])
    chosen, seen = [], set()
    for k in r["d"]["keywords"]:
        best = None
        for c in order:
            if c in seen or k not in r["kw"].get(c, []):
                continue
            if best is None or r["score"][c] / TOK[c] > r["score"][best] / TOK[best]:
                best = c
        if best is not None:
            chosen.append(best)
            seen.add(best)
    rest = sorted((c for c in order if c not in seen), key=lambda c: -r["score"][c] / TOK[c])
    return a1_prefix(chosen + rest)[0]


def rescored(r, agg):
    sc = {}
    for c, v in r["d"]["contributions"].items():
        if c not in TOK:
            continue
        per = defaultdict(list)
        for x in v:
            per[x["keyword"]].append(x["contribution"])
        sc[c] = agg(per)
    return sc


def pick_kwmax(r):
    """Điểm chunk = Σ_từ khoá max_thực thể (một từ khoá không cộng dồn nhiều thực thể cùng trỏ vào chunk)."""
    sc = rescored(r, lambda per: sum(max(x) for x in per.values()))
    top = sorted(sc, key=lambda c: -sc[c])[:30]
    return a1_prefix(top)[0]


def pick_kwmax_dens(r):
    sc = rescored(r, lambda per: sum(max(x) for x in per.values()))
    top = sorted(sc, key=lambda c: -sc[c])[:30]
    return a1_prefix(sorted(top, key=lambda c: -sc[c] / TOK[c]))[0]


def pick_nkw(r):
    """Xếp theo số từ khoá khác nhau cùng trỏ tới chunk, hoà thì theo điểm."""
    top = sorted(r["order"], key=lambda c: (-len(r["kw"].get(c, [])), -r["score"][c]))
    return a1_prefix(top)[0]


def pick_sqrt(r):
    top = sorted(r["order"], key=lambda c: -r["score"][c] / (TOK[c] ** 0.5))
    return a1_prefix(top)[0]


evaluate("S0 C0 (tái dựng)", pick_C0)
evaluate("S1 first-fit (sửa bước cắt, = finding sửa baseline)", pick_firstfit)
evaluate("S2 phủ từ khoá, cắt tiền tố", pick_cov_prefix)
evaluate("S3 phủ từ khoá + first-fit", pick_cov_firstfit)
evaluate("S4 mật độ điểm/token, cắt tiền tố", pick_dens_prefix)
evaluate("S5 mật độ điểm/token + first-fit", pick_dens_firstfit)
evaluate("S6 phủ từ khoá (chunk mật độ cao nhất mỗi từ khoá) + phần còn lại mật độ, cắt tiền tố", pick_cov_dens_prefixcut)
evaluate("S7 như S6 + first-fit", pick_cov_dens)
evaluate("S8 phủ từ khoá trên TOÀN BỘ ứng viên (không cắt top-30), tiền tố", pick_cov_all_prefix,
         "khám phá: đổi trần 30")
evaluate("S9 điểm chunk = Σ từ khoá max thực thể, top-30, tiền tố", pick_kwmax)
evaluate("S10 như S9 rồi xếp lại theo mật độ", pick_kwmax_dens)
evaluate("S11 xếp theo số từ khoá khác nhau cùng trỏ tới chunk, rồi điểm", pick_nkw)
evaluate("S12 điểm/sqrt(token), tiền tố", pick_sqrt)
R["SIM"] = SIM

print(json.dumps({k: v for k, v in R.items() if k != "SIM"}, ensure_ascii=False, indent=1))
print("\nMÔ PHỎNG")
for s in SIM:
    print(f"{s['name']:<95} đủ={s['full_q']:>3} gold={s['gold_kept']:>8} lên={s['q_up']:>2} xuống={s['q_down']:>2} tok_med={s['tok_median']} jacc={s['jaccard_vs_C0_median']}")
json.dump(R, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
json.dump({"q2": q2rows, "q3": q3cases}, open(OUT.replace("diagnosis.json", "diagnosis_cases.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1, default=str)

def dom_seed(r, c):
    per = Counter()
    for x in r["d"]["contributions"][c]:
        per[x["seed"]] += x["contribution"]
    return per.most_common(1)[0][0]


def interleave(r, keyf):
    """Chunk đầu của mỗi nhóm (nhóm = thực thể xuất phát/từ khoá chủ đạo) lên trước, rồi chunk thứ hai, ... (giữ thứ tự điểm trong nhóm)."""
    seen = Counter()
    keyed = []
    for i, c in enumerate(r["order"]):
        g = keyf(r, c)
        keyed.append((seen[g], i, c))
        seen[g] += 1
    return [c for _, _, c in sorted(keyed)]


evaluate("S13 xen kẽ theo thực thể xuất phát chủ đạo, tiền tố", lambda r: a1_prefix(interleave(r, dom_seed))[0])
evaluate("S14 xen kẽ theo từ khoá chủ đạo, tiền tố", lambda r: a1_prefix(interleave(r, lambda rr, c: rr["domkw"][c]))[0])
R["SIM"] = SIM
for s_ in SIM[-2:]:
    print(f"{s_['name']:<95} đủ={s_['full_q']:>3} gold={s_['gold_kept']:>8} lên={s_['q_up']:>2} xuống={s_['q_down']:>2} tok_med={s_['tok_median']} jacc={s_['jaccard_vs_C0_median']}")

# ---------------------------------------------------------------- trần oracle + độ dài/điểm (gold chỉ làm nhãn đánh giá)
def spearman(a, b):
    def rk(x):
        o = sorted(range(len(x)), key=lambda i: x[i])
        r = [0] * len(x)
        for p, i in enumerate(o):
            r[i] = p
        return r
    ra, rb = rk(a), rk(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return num / den if den else 0


corr = [spearman([TOK[c] for c in recs[q]["order"]], [recs[q]["score"][c] for c in recs[q]["order"]]) for q in qs]
all_tok = [TOK[c] for c in TOK]
gold_tok_all = [TOK[g] for q in qs for g in recs[q]["G"] if g in TOK]
ORA = {
    "spearman_tok_vs_score_in_top30_median": med(corr),
    "chunk_tok_median_corpus": med(all_tok),
    "gold_tok_median_all": med(gold_tok_all),
    "gold_tok_median_kept(OK)": med([TOK[g] for q in qs for g, v in recs[q]["lay"].items() if v == "OK"]),
    "gold_tok_median_L3": med([TOK[g] for q in qs for g, v in recs[q]["lay"].items() if v == "L3"]),
    "oracle_top30_full_questions": sum(1 for q in qs if all(g in set(recs[q]["order"]) for g in recs[q]["G"])
                                      and sum(TOK[g] for g in recs[q]["G"]) <= BUDGET),
    "oracle_cand_full_questions": sum(1 for q in qs if all(g in recs[q]["cand"] for g in recs[q]["G"])
                                     and sum(TOK[g] for g in recs[q]["G"]) <= BUDGET),
    "q_gold_in_top30_but_gold_sum_over_budget": sum(1 for q in qs if all(g in set(recs[q]["order"]) for g in recs[q]["G"])
                                                   and sum(TOK[g] for g in recs[q]["G"]) > BUDGET),
}
R["ORACLE"] = ORA
print("\nORACLE / ĐỘ DÀI", json.dumps(ORA, ensure_ascii=False, indent=1))
json.dump(R, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
