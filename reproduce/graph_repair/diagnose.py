"""Offline attribution of graph-only retrieval losses from phase-1 diagnostic logs."""
import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import re
import statistics

import networkx as nx
import tiktoken

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "LiHua-World-qwen-modal"


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line]


def sources(data):
    return set((data or {}).get("source_id", "").split("<SEP>")) - {""}


def counts_by_layer(items):
    result = {}
    for typ in ("All", "Single", "Multi"):
        sub = [x for x in items if typ == "All" or x["type"] == typ]
        result[typ] = {
            layer: {"chunks": sum(x["layer"] == layer for x in sub),
                    "questions": len({x["question"] for x in sub if x["layer"] == layer})}
            for layer in ("L0_not_reachable", "L1_reach_not_cand", "L2_cand_not_top30",
                          "L3_top30_not_a1", "OK")
        }
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="Run directory under logs/graph_repair/phase1")
    ap.add_argument("--output", required=True)
    ap.add_argument("--rank-l0", action="store_true", help="Recompute full entity-name cosine ranks locally")
    args = ap.parse_args()
    base = ROOT / "logs" / "graph_repair" / "phase1" / args.run
    records = jsonl(base / "C0_records.jsonl")
    diagnostics = jsonl(base / "diag.jsonl")
    if len(records) != 180 or len(diagnostics) != 180:
        raise ValueError("Expected 180 records and diagnostic lines")
    recs = {r["question"]: r for r in records}
    diags = {d["query"]: d for d in diagnostics}
    if set(recs) != set(diags):
        raise ValueError("Record/diagnostic question mismatch")
    from sys import path
    path.insert(0, str(ROOT / "reproduce" / "screening"))
    from screen_variant import gold_map
    gold = gold_map()

    graph = nx.read_graphml(INDEX / "graph_chunk_entity_relation.graphml")
    chunks = json.loads((INDEX / "kv_store_text_chunks.json").read_text(encoding="utf-8"))
    encoder = tiktoken.get_encoding("o200k_base")
    chunk_tokens = {cid: len(encoder.encode(x["content"])) for cid, x in chunks.items()}
    entity_by_chunk = defaultdict(set)
    degree = dict(graph.degree())
    df = {}
    for name, data in graph.nodes(data=True):
        ids = sources(data)
        df[name] = len(ids)
        for cid in ids:
            entity_by_chunk[cid].add(name)
    n_hub_1 = max(1, math.ceil(len(graph) * .01))
    n_hub_5 = max(1, math.ceil(len(graph) * .05))
    top_degree = sorted(graph, key=lambda n: (-degree[n], n))
    top_df = sorted(graph, key=lambda n: (-df[n], n))
    hub_1 = set(top_degree[:n_hub_1]) | set(top_df[:n_hub_1])
    hub_5 = set(top_degree[:n_hub_5]) | set(top_df[:n_hub_5])

    full_ranks = {}
    if args.rank_l0:
        import base64
        import numpy as np
        import torch
        from transformers import AutoModel, AutoTokenizer
        store = json.loads((INDEX / "vdb_entities_name.json").read_text(encoding="utf-8"))
        matrix = np.frombuffer(base64.b64decode(store["matrix"]), dtype=np.float32).reshape(
            -1, store["embedding_dim"]
        ).copy()
        matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
        names = [row["entity_name"] for row in store["data"]]
        model_name = "sentence-transformers/all-MiniLM-L6-v2"
        tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=True)
        model = AutoModel.from_pretrained(model_name, local_files_only=True)
        all_keywords = sorted({kw for d in diags.values() for kw in d["keywords"]})
        for kw in all_keywords:
            ids = tokenizer([kw], return_tensors="pt", padding=True, truncation=True).input_ids
            with torch.no_grad():
                embedding = model(ids).last_hidden_state.mean(dim=1).numpy()[0]
            embedding = embedding / np.linalg.norm(embedding)
            scores = matrix @ embedding
            order = np.argsort(scores)[::-1]
            full_ranks[kw] = {names[int(i)]: (int(rank + 1), float(scores[i]))
                              for rank, i in enumerate(order)}

    items = []
    d1 = Counter()
    d3 = Counter()
    unique_removed_ids = set()
    seed_counts, removed_seed_counts, hub_questions = [], [], set()
    answer_lengths, path_a_positive = [], 0
    hub_token_1 = hub_token_5 = all_tokens = 0
    boost_results = {"x2": Counter(), "x10": Counter()}
    reconstructed_mismatch = 0
    reconstructed_a1_mismatch = 0
    a1_mismatch_questions = []
    hub_shares_1, hub_shares_5 = [], []
    for question, rec in recs.items():
        d = diags[question]
        if question not in gold:
            raise ValueError(f"Gold missing: {question}")
        typ = rec["type"]
        active_seeds = {n: s for n, s in d["seeds"].items() if not s["short_path_removed"]}
        seed_counts.append(len(active_seeds))
        removed_seed_counts.append(sum(s["short_path_removed"] for s in d["seeds"].values()))
        if set(active_seeds) & hub_1:
            hub_questions.add(question)
        answer_lengths.append(d["maybe_answer_count"])
        path_a_positive += d["path_a_positive"]
        d3["calls"] += d["levenshtein_calls"]
        d3["removed_events"] += sum(d["levenshtein_removed"].values())
        d3["questions_called"] += bool(d["levenshtein_calls"])
        d3["questions_removed"] += bool(d["levenshtein_removed"])
        unique_removed_ids.update(d["levenshtein_removed"])
        contributions = d["contributions"]
        original_scores = {cid: sum(c["contribution"] for c in cs)
                           for cid, cs in contributions.items()}
        full_rank = sorted(original_scores, key=lambda cid: -original_scores[cid])
        reconstructed = full_rank[:len(rec["graph_ids"])]
        reconstructed_mismatch += reconstructed != rec["graph_ids"]
        candidate_rank = {cid: i + 1 for i, cid in enumerate(full_rank)}

        def a1_cut(ordered):
            budget, kept = 0, []
            for cid in ordered:
                if cid not in chunks:
                    continue
                budget += chunk_tokens.get(cid, 0)
                if budget > 4000:
                    break
                kept.append(cid)
            return kept

        if a1_cut(reconstructed) != rec["chunk_ids"]:
            reconstructed_a1_mismatch += 1
            a1_mismatch_questions.append(question)
        ablated_ranks = {}
        for multiplier in ("x2", "x10"):
            divisor = 2 if multiplier == "x2" else 10
            scores = {cid: sum(c["contribution"] / (divisor if c[multiplier] else 1)
                               for c in cs) for cid, cs in contributions.items()}
            ordered = sorted(scores, key=lambda cid: -scores[cid])[:len(rec["graph_ids"])]
            ablated_ranks[multiplier] = ordered
            boost_results[multiplier]["questions_top30_changed"] += ordered != rec["graph_ids"]
            after_a1 = a1_cut(ordered)
            boost_results[multiplier]["questions_a1_changed"] += after_a1 != rec["chunk_ids"]
            wanted = set(gold[question])
            old_top, new_top = set(rec["graph_ids"]), set(ordered)
            old_a1, new_a1 = set(rec["chunk_ids"]), set(after_a1)
            boost_results[multiplier]["gold_up_top30"] += len((new_top - old_top) & wanted)
            boost_results[multiplier]["gold_down_top30"] += len((old_top - new_top) & wanted)
            boost_results[multiplier]["gold_up_a1"] += len((new_a1 - old_a1) & wanted)
            boost_results[multiplier]["gold_down_a1"] += len((old_a1 - new_a1) & wanted)
            boost_results[multiplier]["full_answer_up"] += wanted <= new_a1 and not wanted <= old_a1
            boost_results[multiplier]["full_answer_down"] += wanted <= old_a1 and not wanted <= new_a1
        rank = {cid: i + 1 for i, cid in enumerate(rec.get("graph_ids", []))}
        reachable = set(d["reachable_nodes"])
        within_two = set()
        for seed in active_seeds:
            if seed in graph:
                within_two.update(nx.single_source_shortest_path_length(graph, seed, cutoff=2))
        # Include isolated seeds (which have no path tuple) explicitly.
        for name in active_seeds:
            if active_seeds[name]["path_count"] == 0:
                reachable.update(sources(graph.nodes[name]) if name in graph else ())
        question_tokens = question_hub_1 = question_hub_5 = 0
        for cid in rec["chunk_ids"]:
            all_tokens += chunk_tokens.get(cid, 0)
            question_tokens += chunk_tokens.get(cid, 0)
            cc = contributions.get(cid, [])
            if cc:
                dominant = max(cc, key=lambda x: x["contribution"])
                if dominant["seed"] in hub_1:
                    hub_token_1 += chunk_tokens.get(cid, 0)
                    question_hub_1 += chunk_tokens.get(cid, 0)
                if dominant["seed"] in hub_5:
                    hub_token_5 += chunk_tokens.get(cid, 0)
                    question_hub_5 += chunk_tokens.get(cid, 0)
        hub_shares_1.append(question_hub_1 / question_tokens if question_tokens else 0)
        hub_shares_5.append(question_hub_5 / question_tokens if question_tokens else 0)

        for cid in gold[question]:
            if cid not in reachable:
                layer = "L0_not_reachable"
            elif cid not in contributions:
                layer = "L1_reach_not_cand"
            elif cid not in rec["graph_ids"]:
                layer = "L2_cand_not_top30"
            elif cid not in rec["chunk_ids"]:
                layer = "L3_top30_not_a1"
            else:
                layer = "OK"
            owners = sorted(entity_by_chunk.get(cid, ()))
            selected_owners = [n for n, s in active_seeds.items() if cid in s["selected"]]
            all_counter_owners = [n for n, s in active_seeds.items() if cid in s["all_path_counter"]]
            last_counter_owners = [n for n, s in active_seeds.items() if cid in s["last_path_counter"]]
            counter_ranks = {}
            for name in set(all_counter_owners) | set(last_counter_owners):
                seed = active_seeds[name]
                counter_ranks[name] = {}
                for label, field in (("all", "all_path_counter"), ("last", "last_path_counter")):
                    values = seed[field]
                    if cid in values:
                        counter_ranks[name][label] = sorted(values, key=lambda x: -values[x]).index(cid) + 1
            if layer == "L1_reach_not_cand":
                if last_counter_owners:
                    reason = "top3_per_seed"
                elif all_counter_owners:
                    reason = "last_path_only"
                elif cid in d["levenshtein_removed"]:
                    reason = "levenshtein"
                else:
                    reason = "other_projection"
                d1[reason] += 1
            else:
                reason = None
            if layer == "L0_not_reachable":
                d1["l0_has_entity"] += bool(owners)
                d1["l0_entity_is_matched_seed"] += bool(set(owners) & set(d["seeds"]))
                d1["l0_entity_within_2_hops"] += bool(set(owners) & within_two)
                d1["l0_reachable_on_edge_only"] += cid in d["reachable_edges"]
            nearest = None
            if layer == "L0_not_reachable" and full_ranks:
                options = [(rank, score, kw, owner) for kw in d["keywords"] for owner in owners
                           for rank, score in [full_ranks.get(kw, {}).get(owner, (None, None))]
                           if rank is not None]
                if options:
                    rank, score, kw, owner = min(options)
                    nearest = {"entity": owner, "keyword": kw, "rank": rank, "cosine": score}
            normalized_owners = {re.sub(r"[^A-Z0-9]", "", n.upper()) for n in owners}
            duplicate_seed = [n for n in active_seeds
                              if re.sub(r"[^A-Z0-9]", "", n.upper()) in normalized_owners and n not in owners]
            d3["gold_removed_events"] += d["levenshtein_removed"].get(cid, 0)
            d3["gold_removed_chunks"] += cid in d["levenshtein_removed"]
            items.append({"question": question, "type": typ, "gold_chunk": cid,
                          "layer": layer, "rank": candidate_rank.get(cid), "l1_reason": reason,
                          "entities": owners, "matched_owner_seeds": sorted(set(owners) & set(d["seeds"])),
                          "nearest_entity_match": nearest, "duplicate_seed_names": duplicate_seed,
                          "selected_owners": selected_owners,
                          "all_counter_owners": all_counter_owners,
                          "last_counter_owners": last_counter_owners,
                          "counter_ranks": counter_ranks,
                          "dominant_above": []})
            if layer in ("L2_cand_not_top30", "L3_top30_not_a1"):
                above = full_rank[:candidate_rank[cid]-1]
                dominant_counts = Counter()
                for other in above:
                    cc = contributions.get(other, [])
                    if cc:
                        dominant_counts[max(cc, key=lambda x: x["contribution"])["seed"]] += 1
                items[-1]["above_dominant_seed_counts"] = dict(dominant_counts)
                for other in above[:5]:
                    cc = contributions.get(other, [])
                    if cc:
                        top = max(cc, key=lambda x: x["contribution"])
                        items[-1]["dominant_above"].append({"chunk": other, "seed": top["seed"],
                                                              "contribution": top["contribution"]})
                for multiplier, reranked in ablated_ranks.items():
                    if cid in reranked and layer == "L2_cand_not_top30":
                        boost_results[multiplier]["gold_rescued_to_top30"] += 1
    summary = {
        "run": args.run, "questions": len(recs), "gold_chunks": len(items),
        "layers": counts_by_layer(items),
        "t1": {"maybe_answer_lengths": dict(Counter(answer_lengths)),
               "paths_a_positive": path_a_positive,
               "paths_total": sum(d["path_total"] for d in diags.values()),
               "levenshtein": {**dict(d3), "unique_removed_ids": len(unique_removed_ids)},
               "seeds_per_question": seed_counts,
               "short_removed_per_question": removed_seed_counts,
               "hub_seed_questions": len(hub_questions),
               "hub_seed_question_names": sorted(hub_questions)},
        "l0_l1_detail": dict(d1),
        "hub": {"top1_percent_nodes_each": n_hub_1, "top5_percent_nodes_each": n_hub_5,
                "a1_tokens_total": all_tokens, "a1_tokens_dominant_top1": hub_token_1,
                "a1_tokens_dominant_top5": hub_token_5,
                "a1_share_top1": hub_token_1 / all_tokens if all_tokens else None,
                "a1_share_top5": hub_token_5 / all_tokens if all_tokens else None,
                "per_question_share_top1_median": statistics.median(hub_shares_1),
                "per_question_share_top5_median": statistics.median(hub_shares_5)},
        "boost_ablation": {k: dict(v) for k, v in boost_results.items()},
        "reconstructed_graph_rank_mismatch_questions": reconstructed_mismatch,
        "reconstructed_a1_mismatch_questions": reconstructed_a1_mismatch,
        "a1_mismatch_question_names": a1_mismatch_questions,
        "retention": {"gold_kept": sum(x["layer"] == "OK" for x in items),
                      "full_answer_questions": sum(all(x["layer"] == "OK" for x in items if x["question"] == q)
                                                   for q in recs)},
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with out.with_suffix(".jsonl").open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(json.dumps({"run": args.run, "layers": summary["layers"],
                      "retention": summary["retention"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
