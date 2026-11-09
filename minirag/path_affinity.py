"""Query evidence relevance inside path projection; no extra corpus retrieval."""
import math
import time


def condition_evidence(entries, affinities, max_chunks=3, *, affinity_only=False):
    """Apply relevance before the original cap, retaining absolute evidence mass.

    Input contains complete bounded node/edge provenance scores. affinity_only
    is a diagnostic ablation, never the proposed graph method.
    """
    result = {}
    for seed, entry in entries.items():
        scores = {}
        for cid, mass in entry['PathChunkScores'].items():
            cosine = float(affinities[cid])
            if not math.isfinite(cosine) or not -1.000001 <= cosine <= 1.000001:
                raise ValueError('Invalid cosine for graph-supported evidence')
            if not math.isfinite(mass) or mass < 0:
                raise ValueError('Invalid path projection mass')
            value = (1.0 if affinity_only else mass) * max(0.0, min(1.0, cosine))
            if value > 0:
                scores[cid] = value
        ranked = sorted(scores, key=lambda c: (-round(scores[c], 12), c))[:max_chunks]
        result[seed] = {'Score': entry['Score'], 'Path': ranked,
                        'PathChunkScores': {cid: scores[cid] for cid in ranked}}
    return result


async def project_with_affinity(entries, graph, pairs, query, max_chunks, *, valid,
                                chunk_vectors, diagnostics=None, reference_answers=None):
    """Keep original path scores and both provenance channels, then select locally."""
    from .path_projection import project_paths
    if valid is None or chunk_vectors is None:
        raise ValueError('Path affinity requires valid chunk IDs and existing chunk vectors')
    reference = None
    if reference_answers is not None:
        from .utils import count_elements_in_tuple
        # Selection stays on C1/P0; only the score channel may use P2.
        reference = {seed: {'Score': entry['Score'], 'Path': {
            path: [count_elements_in_tuple(path, reference_answers), score[1]]
            for path, score in entry['Path'].items()}} for seed, entry in entries.items()}
    trace = {}
    complete = await project_paths(entries, graph, pairs, query, len(valid), 'local',
                                   valid=valid, trace=trace)
    started = time.perf_counter()
    pool = set(trace['candidate_chunk_ids'])
    rows = await chunk_vectors.score_ids(query, pool)
    affinities = {row['id']: row['distance'] for row in rows}
    if set(affinities) != pool:
        raise ValueError('Missing query affinity for graph-supported evidence')
    affinity_ms = 1000 * (time.perf_counter() - started)
    if reference is None:
        result = condition_evidence(complete, affinities, max_chunks)
    else:
        reference_trace = {}
        reference = await project_paths(reference, graph, pairs, query, len(valid), 'local',
                                        valid=valid, trace=reference_trace)
        if set(reference_trace['candidate_chunk_ids']) != pool:
            raise ValueError('P0/P2 supported source pools differ before fixed selection')
        selected = condition_evidence(reference, affinities, max_chunks)
        scored = condition_evidence(complete, affinities, len(valid))
        result = {seed: {'Score': entry['Score'], 'Path': list(entry['Path']),
            'PathChunkScores': {cid: scored[seed]['PathChunkScores'][cid] for cid in entry['Path']}}
            for seed, entry in selected.items()}
        trace.update(selection='c1_affinity',
            reference_candidates={seed: list(entry['Path']) for seed, entry in selected.items()},
            reference_path_chunk_scores={seed: dict(entry['PathChunkScores']) for seed, entry in selected.items()},
            reference_projection_ms=reference_trace['projection_ms'])
    trace.update(mode='affinity', affinity_ms=affinity_ms,
                 local_cap=max_chunks)
    if diagnostics is not None:
        diagnostics.update(trace)
    return result
