import networkx as nx

from minirag.paper_edge_score import edge_vote_path_paper, omega


def chain():
    # A - B - C - D - E, plus hub H joined to A and E
    g = nx.Graph()
    g.add_edges_from([("A", "B"), ("B", "C"), ("C", "D"), ("D", "E"), ("H", "A"), ("H", "E")])
    return g


def test_omega_counts_important_nodes_within_k_of_either_endpoint():
    g = chain()
    e_ab, e_cd = frozenset("AB"), frozenset("CD")
    w, n = omega(g, ["A", "D", "missing"], [e_ab, e_cd], k=1)
    assert n == 2  # nodes absent from the graph are ignored
    # k=1 around A-B: {H, A, B, C} -> A only. Around C-D: {B, C, D, E} -> D only.
    assert w == {e_ab: 1, e_cd: 1}
    w2, _ = omega(g, ["A", "D"], [e_ab, e_cd], k=2)
    # k=2 around A-B reaches D (B->C->D); around C-D reaches A (C->B->A)
    assert w2 == {e_ab: 2, e_cd: 2}


def test_vote_sums_selected_edges_either_orientation_and_keeps_shape():
    g = chain()
    paths = {"A": {"Score": 0.9, "Path": {("A", "B", "C"): [1], ("A", "H"): [0]}},
             "C": {"Score": 0.5, "Path": {("C", "B"): [0]}}}
    out, pairs = edge_vote_path_paper(paths, g, ["B"], n_select=1, k=1)
    # k=1, source B: A-B -> 1, B-C -> 1, A-H -> 1 (A is next to B). Ties broken by name: A-B first.
    assert out["A"]["Path"][("A", "B", "C")] == [1, 1]
    assert out["A"]["Path"][("A", "H")] == [0, 0]
    assert out["C"]["Path"][("C", "B")] == [0, 0]
    assert pairs == {("A", "B", "C"): [("A", "B")]}
    assert out["A"]["Score"] == 0.9 and paths["A"]["Path"][("A", "B", "C")] == [1]  # input untouched
