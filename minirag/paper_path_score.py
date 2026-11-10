"""Opt-in paper Eq. (3) path ranking, registered in EQ3_REGISTRATION.md."""

import json
import os
import time


def select_paper_paths(path_dict, pairs_append, k=50, query=None):
    """Keep top-k paths per surviving seed/query-entity pair, without mutating inputs.

    The existing pipeline collapses duplicate seeds across query entities. Its
    surviving Score is the cosine for the last matching query entity.
    """
    start = time.perf_counter()
    out, selected_edges = {}, {}
    before = after = 0
    for seed, entry in path_dict.items():
        factor = float(entry["Score"])
        ranked = []
        for path, terms in entry["Path"].items():
            # terms = [answer-node count, selected-edge weight]. The edge
            # component is either code's unit votes or Eq. (2)'s omega_e.
            score = factor * (1 + terms[0] + terms[1])
            ranked.append((path, score))
        before += len(ranked)
        ranked.sort(key=lambda item: (-item[1], item[0]))
        chosen = ranked[:k]
        after += len(chosen)
        paths = {path: list(entry["Path"][path]) for path, _ in chosen}
        out[seed] = {**entry, "Path": paths,
                     "PathPaperScores": {path: score for path, score in chosen}}
        for path in paths:
            if path in pairs_append:
                selected_edges[path] = pairs_append[path]
    folder = os.environ.get("MINIRAG_PATH_SELECT_LOG", "")
    if folder:
        os.makedirs(folder, exist_ok=True)
        row = {"query": query, "paths_before": before, "paths_after": after,
               "pairs": len(path_dict), "k": k,
               "elapsed_ms": round((time.perf_counter() - start) * 1000, 3)}
        with open(os.path.join(folder, f"path_stats_{os.getpid()}.jsonl"), "a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    return out, selected_edges
