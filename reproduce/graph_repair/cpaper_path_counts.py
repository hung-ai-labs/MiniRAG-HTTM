"""Count simple paths of 1..4 edges in the frozen entity/chunk graph. No index writes."""
import hashlib
import json
from pathlib import Path
import statistics
import time

import networkx as nx

INDEX = Path('E:/Project/MiniRAG/LiHua-World-qwen-modal/graph_chunk_entity_relation.graphml')
OUT = Path('logs/graph_repair/cpaper/path_counts.json')


def adjacency(graph):
    adj = {node: set(graph.neighbors(node)) for node in graph}
    for node, data in graph.nodes(data=True):
        for cid in str(data.get('source_id', '')).split('<SEP>'):
            cid = cid.strip()
            if cid:
                chunk = 'chunk:' + cid
                adj.setdefault(chunk, set()).add(node)
                adj[node].add(chunk)
    return adj


def count_from(adj, start):
    """Exact count; last step counted by degree, so no materialized length-4 paths."""
    counts = [0, 0, 0, 0]
    for b in adj[start]:
        counts[0] += 1
        for c in adj[b]:
            if c == start:
                continue
            counts[1] += 1
            for d in adj[c]:
                if d == start or d == b:
                    continue
                counts[2] += 1
                counts[3] += (len(adj[d]) - int(start in adj[d])
                              - int(b in adj[d]) - int(c in adj[d]))
    return counts


def main():
    graph = nx.read_graphml(INDEX)
    adj = adjacency(graph)
    started = time.perf_counter()
    rows = {node: count_from(adj, node) for node in graph}
    elapsed = time.perf_counter() - started
    totals = sorted(sum(v) for v in rows.values())
    hubs = sorted(graph.degree, key=lambda row: (-row[1], row[0]))[:16]
    report = {
        'graphml_sha256': hashlib.sha256(INDEX.read_bytes()).hexdigest(),
        'entity_nodes': graph.number_of_nodes(), 'entity_edges': graph.number_of_edges(),
        'chunk_nodes': len(adj) - graph.number_of_nodes(),
        'entity_chunk_edges': sum(len(adj[n]) for n in adj if n.startswith('chunk:')),
        'path_definition': 'simple paths of 1..4 edges in heterogeneous undirected graph, starting at each entity',
        'median': statistics.median(totals), 'p90': totals[int(.9 * (len(totals)-1))],
        'max': totals[-1], 'count_seconds_all_entities': round(elapsed, 3),
        'top_degree_hubs': [{'entity': n, 'degree_entity': degree,
                             'paths_by_length': rows[n], 'total': sum(rows[n])}
                            for n, degree in hubs],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('median', 'p90', 'max', 'count_seconds_all_entities')}, indent=2))


if __name__ == '__main__':
    main()
