"""Budgeted evidence-set selection (label-free at inference).

Given a candidate pool, a calibrated probability p(c) that chunk c is evidence
(from the trained scorer), and query facets derived from the native pipeline,
choose whole chunks greedily by marginal gain per token:

  F(S) = sum_d [1 - prod_{c in S, doc(c)=d} (1 - p_c)]                 relevance, per conversation
       + beta * sum_f w_f [1 - prod_{c in S, c supports f} (1 - p_c)]  facet coverage

Both terms are probabilistic coverage functions, hence monotone submodular:
  - grouping by conversation discounts overlapping chunks of the same document;
  - a facet is a query keyword (its seed entities' chunk paths) or a query date
    anchor (chunks with that Time header); a second chunk for an already supported
    facet earns less, which pushes a Multi question towards its other half.
Weights w_f = log(1 + |pool| / |support of f in pool|): rare facets count more.

Stop when no remaining chunk fits the 4,000-token budget, or when the best
marginal gain per 1,000 tokens is below tau (adaptive length; tau = 0 fills the
budget). Output order = selection order (position barely matters for Qwen:
83.0 -> 84.1 on full-evidence questions, oracle 11/11).
"""
import math

from reproduce.evidence_set.data import corpus, BUDGET


def facets(r, pool):
    """Label-free facets from the captured native retrieval of one question."""
    inpool = set(pool)
    out = {}
    for kw, seeds in r['groups'].items():
        support = {c for s in seeds for c in s['path'] if c in inpool}
        if support:
            out['kw:' + kw] = support
    for a in r['anchors']:
        support = {c for c in r['date_chunks'].get(a, ()) if c in inpool}
        if support:
            out['date:' + a] = support
    n = max(len(pool), 1)
    return {f: (s, math.log(1 + n / len(s))) for f, s in out.items()}


def select(pool, p, facet_map, *, beta=1.0, tau=0.0, budget=BUDGET, group_docs=True):
    chunks, _, _ = corpus()
    pool = [c for c in dict.fromkeys(pool) if c in chunks]
    by_chunk = {c: [] for c in pool}
    for f, (support, w) in facet_map.items():
        for c in support:
            by_chunk[c].append(f)
    miss_doc = {}      # doc -> prod (1 - p) over selected chunks of that doc
    miss_facet = {f: 1.0 for f in facet_map}
    chosen, used, trace = [], 0, []
    left = set(pool)
    while True:
        best, best_ratio, best_gain = None, -1.0, 0.0
        for c in pool:
            if c not in left or used + chunks[c]['tokens'] > budget:
                continue
            q = 1.0 - min(max(p.get(c, 0.0), 0.0), 1.0)
            key = chunks[c]['doc'] if group_docs else c
            gain = miss_doc.get(key, 1.0) * (1.0 - q)
            if beta:
                gain += beta * sum(facet_map[f][1] * miss_facet[f] * (1.0 - q) for f in by_chunk[c])
            ratio = 1000.0 * gain / chunks[c]['tokens']
            if ratio > best_ratio:
                best, best_ratio, best_gain = c, ratio, gain
        if best is None or best_ratio < tau or (tau > 0 and best_gain <= 0):
            break
        q = 1.0 - min(max(p.get(best, 0.0), 0.0), 1.0)
        key = chunks[best]['doc'] if group_docs else best
        miss_doc[key] = miss_doc.get(key, 1.0) * q
        for f in by_chunk[best]:
            miss_facet[f] *= q
        chosen.append(best)
        used += chunks[best]['tokens']
        left.discard(best)
        trace.append(round(best_ratio, 4))
    return chosen, {'tokens': used, 'gain_per_1k': trace}


def rerank(pool, p, budget=BUDGET):
    """Ablation: plain reranking, i.e. A1 over the pool sorted by p (ties keep pool order)."""
    from reproduce.evidence_set.data import a1
    order = sorted(range(len(pool)), key=lambda i: (-p.get(pool[i], 0.0), i))
    return a1([pool[i] for i in order], budget)
