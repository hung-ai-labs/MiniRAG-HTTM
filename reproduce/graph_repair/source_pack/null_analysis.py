"""Mô tả (log-only) cách câu Null dùng ngân sách Sources, so với 180 câu có đáp án. Không có nhãn đáp án cho Null."""
import json, os, statistics as st
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PP = os.path.join(ROOT, "logs", "graph_repair", "p_pack")
jl = lambda p: [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
med = lambda x: round(st.median(x), 2) if x else None

def load(group, name):
    if group == "ans":
        d = {r["query"]: r for r in jl(f"{PP}/c0_diag/diag.jsonl")} if name == "c0" else None
        rec = {r["question"]: r for r in jl(f"{PP}/{ {'c0':'c0_reg','p_ff':'p_ff','p_d05f':'p_d05f'}[name] }/C0_records.jsonl")}
        return d, rec
    d = {r["query"]: r for r in jl(f"{PP}/null/{name}/diag.jsonl")}
    rec = {r["question"]: r for r in jl(f"{PP}/null/{name}/records.jsonl")}
    return d, rec

out = {}
for grp in ("ans", "null"):
    d0, r0 = load(grp, "c0")
    if grp == "ans":
        qs = list(d0)
    else:
        qs = list(r0)
        d0 = load("null", "c0")[0]
    sc = lambda q: {c: sum(x["contribution"] for x in v) for c, v in d0[q]["contributions"].items()}
    top30 = lambda q: d0[q]["graph_ids"]
    row = {"n": len(qs)}
    row["n_keywords_med"] = med([len(d0[q]["keywords"]) for q in qs])
    row["n_seeds_med"] = med([len(d0[q]["seeds"]) for q in qs])
    row["n_candidates_med"] = med([len(d0[q]["contributions"]) for q in qs])
    row["top1_score_med"] = med([max(sc(q).values()) for q in qs if sc(q)])
    row["top30_sum_score_med"] = med([sum(sc(q)[c] for c in top30(q)) for q in qs])
    row["C0_chunks_med"] = med([len(r0[q]["chunk_ids"]) for q in qs])
    row["C0_sources_tok_med"] = med([r0[q].get("sources_tok", 0) for q in qs])
    kept_share = [sum(sc(q).get(c, 0) for c in r0[q]["chunk_ids"]) / max(1e-9, sum(sc(q)[c] for c in top30(q))) for q in qs]
    row["score_share_kept_C0_med"] = med(kept_share)
    for name in ("p_ff", "p_d05f"):
        if grp == "ans":
            _, r1 = load("ans", name)
        else:
            _, r1 = load("null", name)
        j, added_rank, added_ratio, chg, dn, dt = [], [], [], 0, [], []
        for q in qs:
            a, b = set(r0[q]["chunk_ids"]), set(r1[q]["chunk_ids"])
            j.append(len(a & b) / max(1, len(a | b)))
            chg += a != b
            dn.append(len(r1[q]["chunk_ids"]) - len(r0[q]["chunk_ids"]))
            dt.append(r1[q].get("sources_tok", 0) - r0[q].get("sources_tok", 0))
            g = top30(q)
            s = sc(q)
            top = max(s.values()) if s else 1
            for c in b - a:
                if c in g:
                    added_rank.append(g.index(c) + 1)
                    added_ratio.append(s[c] / top)
        row[name] = {"questions_changed": f"{chg}/{len(qs)}", "jaccard_vs_C0_med": med(j),
                     "chunks_added_med_per_q": med(dn), "sources_tok_delta_med": med(dt),
                     "added_chunk_graph_rank_med": med(added_rank), "added_chunk_score_over_top1_med": med(added_ratio),
                     "n_added_total": len(added_rank)}
    out[grp] = row
print(json.dumps(out, ensure_ascii=False, indent=1))
json.dump(out, open(f"{PP}/null_summary.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
