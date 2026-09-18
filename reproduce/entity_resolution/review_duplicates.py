"""Print evidence for manual review of duplicate entity groups.

This script is deliberately read-only: it opens only the GraphML file in the
selected working directory and writes nothing to the index or vector stores.
"""

import argparse
import collections
import os
import sys

import networkx as nx

from graph_stats import norm_key


EXPECTED_NODES = 1556
EXPECTED_EDGES = 1509
EXPECTED_DUPLICATE_GROUPS = 21
EXPECTED_DUPLICATE_NODES = 42


def compact(value, limit):
    """Collapse whitespace and truncate a GraphML attribute for review output."""
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def duplicate_groups(graph):
    groups = collections.defaultdict(list)
    for node in graph:
        groups[norm_key(node)].append(node)
    return sorted(
        (nodes for key, nodes in groups.items() if key and len(nodes) > 1),
        key=lambda nodes: -sum(graph.degree(node) for node in nodes),
    )


def top_neighbors(graph, node, limit):
    return sorted(
        graph.neighbors(node),
        key=lambda neighbor: (-graph.degree(neighbor), str(neighbor)),
    )[:limit]


def validate_baseline(graph, groups):
    observed = (
        graph.number_of_nodes(),
        graph.number_of_edges(),
        len(groups),
        sum(len(nodes) for nodes in groups),
    )
    expected = (
        EXPECTED_NODES,
        EXPECTED_EDGES,
        EXPECTED_DUPLICATE_GROUPS,
        EXPECTED_DUPLICATE_NODES,
    )
    if observed != expected:
        raise SystemExit(
            "baseline mismatch: "
            f"observed nodes={observed[0]}, edges={observed[1]}, "
            f"duplicate_groups={observed[2]}, duplicate_nodes={observed[3]}; "
            f"expected nodes={expected[0]}, edges={expected[1]}, "
            f"duplicate_groups={expected[2]}, duplicate_nodes={expected[3]}"
        )


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--workingdir", default="./LiHua-World-qwen-modal")
    parser.add_argument("--neighbors", type=int, default=8)
    args = parser.parse_args()
    if args.neighbors < 0:
        parser.error("--neighbors must be non-negative")

    graph_path = os.path.join(
        args.workingdir, "graph_chunk_entity_relation.graphml"
    )
    graph = nx.read_graphml(graph_path)
    groups = duplicate_groups(graph)
    validate_baseline(graph, groups)

    print("MiniRAG duplicate entity review (READ ONLY)")
    print(f"graph: {graph_path}")
    print(f"nodes: {graph.number_of_nodes()}")
    print(f"edges: {graph.number_of_edges()}")
    print(f"duplicate_groups: {len(groups)}")
    print(f"duplicate_nodes: {sum(len(nodes) for nodes in groups)}")

    for group_number, nodes in enumerate(groups, start=1):
        ordered = sorted(nodes, key=lambda node: (-graph.degree(node), str(node)))
        total_degree = sum(graph.degree(node) for node in ordered)
        print("\n" + "=" * 100)
        print(
            f"GROUP {group_number:02d} | norm_key={norm_key(ordered[0])!r} | "
            f"total_degree={total_degree}"
        )
        for node_number, node in enumerate(ordered, start=1):
            data = graph.nodes[node]
            neighbors = top_neighbors(graph, node, args.neighbors)
            print("-" * 100)
            print(f"NODE {node_number}: {node!r}")
            print(f"norm_key: {norm_key(node)!r}")
            print(f"degree: {graph.degree(node)}")
            print(f"entity_type: {data.get('entity_type', '')!r}")
            print(f"source_id: {compact(data.get('source_id', ''), 300)}")
            print(f"description: {compact(data.get('description', ''), 500)}")
            print(f"neighbors_shown: {len(neighbors)}")
            if neighbors:
                for neighbor in neighbors:
                    print(f"  - {neighbor!r} (degree={graph.degree(neighbor)})")
            else:
                print("  - (none)")


if __name__ == "__main__":
    main()
