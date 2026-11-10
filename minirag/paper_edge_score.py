"""Faithful implementation of the paper's Eq. (2) (MiniRAG, ACL 2025, p. 37125), opt-in.

    omega_e(e) = sum_{v in V_s ∪ V_a} count(v, G_{e,k})

G_{e,k} is the k-hop subgraph centred at edge e: every node reachable within k steps from either endpoint.
count(v, G) is 1 if v is in G. The key-relationship set E_alpha is the top-ranked edges by omega_e.

Upstream code does not compute this (see reproduce/graph_repair/PAPER_CODE_AUDIT.md, row 3): it takes the edges whose
description is closest to the question (`relationships_vdb.query`), keeps those touching a seed/answer node, and gives
each one weight 1 (`utils.edge_vote_path`). This module replaces only that step, with
`MINIRAG_EDGE_SCORE=paper`; pre-registered in reproduce/graph_repair/EQ2_REGISTRATION.md.

Choices the paper leaves open, fixed in the registration:
- k = 2, the hop limit the code already uses for paths (operate.py `get_neighbors_within_k_hops(key, 2)`).
- Candidate edges = edges on the candidate reasoning paths (the only edges that can change a path score).
- |E_alpha| = number of edges the code's own E_alpha holds for that query (`goodedge`), so only *which* edges
  change, not how many.
- Ties broken by edge name, deterministic. Edges matched on the path in either orientation (the graph is undirected).
"""
import json
import os
import time


def _balls(graph, sources, k):
    """For each graph node, a bitmask of the source nodes within k hops of it (BFS from each source)."""
    cover = {}
    for bit, src in enumerate(sources):
        mask = 1 << bit
        frontier, seen = {src}, {src}
        for _ in range(k):
            nxt = set()
            for u in frontier:
                nxt.update(graph.adj[u])
            frontier = nxt - seen
            seen |= frontier
        for node in seen:
            cover[node] = cover.get(node, 0) | mask
    return cover


def path_edges(path):
    return [frozenset(pair) for pair in zip(path, path[1:]) if pair[0] != pair[1]]


def omega(graph, important_nodes, edges, k=2):
    sources = sorted({n for n in important_nodes if n in graph})
    cover = _balls(graph, sources, k)
    return {e: bin(cover.get(min(e), 0) | cover.get(max(e), 0)).count("1") for e in edges}, len(sources)


def edge_vote_path_paper(path_dict, graph, important_nodes, n_select, code_edges=(), query=None, k=2):
    """Drop-in replacement for utils.edge_vote_path: same return shape (path_dict copy, pairs_append)."""
    t0 = time.perf_counter()
    candidates = sorted({e for v in path_dict.values() for p in v["Path"] for e in path_edges(p)},
                        key=lambda e: tuple(sorted(e)))
    w, n_sources = omega(graph, important_nodes, candidates, k)
    ranked = sorted(candidates, key=lambda e: (-w[e], tuple(sorted(e))))
    selected = ranked[:n_select]
    rank = {e: i for i, e in enumerate(selected)}

    out, pairs_append = {}, {}
    for seed, v in path_dict.items():
        scored = {}
        for p, scores in v["Path"].items():
            on_path = sorted({e for e in path_edges(p) if e in rank}, key=rank.get)
            scored[p] = list(scores) + [sum(w[e] for e in on_path)]
            if on_path:
                pairs_append[p] = [_oriented(e, p) for e in on_path]
        out[seed] = {**v, "Path": scored}
    elapsed_ms = 1000 * (time.perf_counter() - t0)
    _log(query, graph, important_nodes, candidates, w, selected, ranked, code_edges, n_sources, elapsed_ms)
    return out, pairs_append


def _oriented(edge, path):
    a, b = sorted(edge)
    for x, y in zip(path, path[1:]):
        if {x, y} == {a, b}:
            return (x, y)
    return (a, b)


def _log(query, graph, important_nodes, candidates, w, selected, ranked, code_edges, n_sources, elapsed_ms):
    folder = os.environ.get("MINIRAG_EDGE_SCORE_LOG")
    if not folder:
        return
    cand = set(candidates)
    code_on_path = sorted({frozenset(e) for e in code_edges} & cand, key=lambda e: tuple(sorted(e)))
    vals = sorted(w.values())
    cut = w[selected[-1]] if selected else None
    w1, _ = omega(graph, important_nodes, candidates, 1)
    row = {
        "query": query, "n_sources": n_sources, "n_candidates": len(candidates), "n_select": len(selected),
        "omega_max": vals[-1] if vals else 0, "omega_median": vals[len(vals) // 2] if vals else 0,
        "omega_distinct": len(set(vals)),
        "frac_at_max": (sum(v == vals[-1] for v in vals) / len(vals)) if vals else 0,
        "tie_at_cut": sum(w[e] == cut for e in candidates) if cut is not None else 0,
        "tie_at_cut_selected": sum(w[e] == cut for e in selected) if cut is not None else 0,
        "omega1_distinct": len(set(w1.values())),
        "omega1_frac_at_max": (sum(v == max(w1.values()) for v in w1.values()) / len(w1)) if w1 else 0,
        "elapsed_ms": round(elapsed_ms, 2),
        "paper_edges": [sorted(e) for e in selected],
        "code_edges_on_path": [sorted(e) for e in code_on_path],
    }
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, f"edge_stats_{os.getpid()}.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
