"""Summarize D1-D4 from frozen, local phase-1 logs; no retrieval or API calls."""
import json
import math
import statistics
from collections import Counter
from pathlib import Path

import networkx as nx

ROOT = Path(__file__).resolve().parents[2]
PHASE = ROOT / "logs" / "graph_repair" / "phase1"


def rows(path):
    result = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if len(result) != 180:
        raise ValueError(f"Expected 180 rows in {path}: {len(result)}")
    return result


def main():
    from sys import path
    path.insert(0, str(ROOT / "reproduce" / "screening"))
    from screen_variant import gold_map
    gold = gold_map()
    baseline = rows(PHASE / "t0_on" / "diag.jsonl")
    fix0 = rows(PHASE / "d2_fix0" / "diag.jsonl")
    rec1 = {r["question"]: r for r in rows(PHASE / "t0_on" / "C0_records.jsonl")}
    rec0 = {r["question"]: r for r in rows(PHASE / "d2_fix0" / "C0_records.jsonl")}
    if {x["query"] for x in baseline} != {x["query"] for x in fix0}:
        raise ValueError("FIX=0 and FIX=1 question sets differ")
    graph = nx.read_graphml(ROOT / "LiHua-World-qwen-modal" / "graph_chunk_entity_relation.graphml")
    degree = dict(graph.degree())
    df = {name: len(set(data.get("source_id", "").split("<SEP>")) - {""})
          for name, data in graph.nodes(data=True)}
    cutoff = math.ceil(len(graph) * .01)
    degree_hubs = set(sorted(graph, key=lambda n: (-degree[n], n))[:cutoff])
    df_hubs = set(sorted(graph, key=lambda n: (-df[n], n))[:cutoff])
    active = lambda d: {n for n, x in d["seeds"].items() if not x["short_path_removed"]}
    removed_gold = [(d["query"], cid) for d in baseline for cid in gold[d["query"]]
                    if cid in d["levenshtein_removed"]]
    candidate = sum(len(d["seeds"]) for d in baseline)
    removed = sum(sum(x["short_path_removed"] for x in d["seeds"].values()) for d in baseline)
    answer = {}
    for name, data in (("fix0", fix0), ("fix1", baseline)):
        values = [d["maybe_answer_count"] for d in data]
        answer[name] = {
            "histogram": dict(sorted(Counter(values).items())),
            "median": statistics.median(values), "min": min(values), "max": max(values),
            "positive_paths": sum(d["path_a_positive"] for d in data),
            "all_paths": sum(d["path_total"] for d in data),
        }
    output = {
        "d1": json.loads((PHASE / "d1_comparison.json").read_text(encoding="utf-8")),
        "d2": {"answer_types": answer,
               "changed_chunk_ids_questions": sum(rec0[q]["chunk_ids"] != rec1[q]["chunk_ids"] for q in rec1)},
        "d3": {"questions_called": sum(bool(d["levenshtein_calls"]) for d in baseline),
               "calls": sum(d["levenshtein_calls"] for d in baseline),
               "removed_events": sum(sum(d["levenshtein_removed"].values()) for d in baseline),
               "removed_question_chunk_pairs": sum(len(d["levenshtein_removed"]) for d in baseline),
               "removed_unique_chunks": len({cid for d in baseline for cid in d["levenshtein_removed"]}),
               "gold_removed_pairs": len(removed_gold),
               "gold_removed_questions": len({q for q, _ in removed_gold}),
               "gold_removed_events": sum(d["levenshtein_removed"].get(cid, 0)
                                          for d in baseline for cid in gold[d["query"]])},
        "d4": {"candidate_seeds": candidate, "short_path_removed_seeds": removed,
               "short_path_removed_fraction": removed / candidate,
               "active_seed_median": statistics.median(len(active(d)) for d in baseline),
               "top1_percent_nodes": cutoff,
               "questions_with_degree_hub_seed": sum(bool(active(d) & degree_hubs) for d in baseline),
               "questions_with_df_hub_seed": sum(bool(active(d) & df_hubs) for d in baseline),
               "questions_with_either_hub_seed": sum(bool(active(d) & (degree_hubs | df_hubs)) for d in baseline)},
    }
    target = PHASE / "t1_summary.json"
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"d2": {k: {"median": v["median"], "positive_paths": v["positive_paths"]}
                                 for k, v in answer.items()}, "d3": output["d3"], "d4": output["d4"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
