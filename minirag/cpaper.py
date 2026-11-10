"""Opt-in paper-style retrieval. Decisions are frozen in CPAPER_REGISTRATION.md.

The heterogeneous graph and E_beta descriptions are derived in memory from the
loaded GraphML. No storage callback or index mutation is made here.
"""
import hashlib
import json
import os
import time

import numpy as np

from .paper_edge_score import omega
from .paper_path_score import select_paper_paths
from .prompt import GRAPH_FIELD_SEP
from .utils import encode_string_by_tiktoken, list_of_list_to_csv, truncate_list_by_token_size
from .temporal import active as temporal_active, candidate_ids


PATH_CAP = 5000
PAPER_K = 10
PAPER_N = 4
SOURCE_LIMIT = 5
SOURCE_TOKENS = 6000


def enabled(name):
    return os.environ.get('MINIRAG_CPAPER_' + name, '1') == '1'


def _parts(value):
    return [v.strip() for v in str(value or '').split(GRAPH_FIELD_SEP) if v.strip()]


def build_heterogeneous_graph(entity_graph):
    graph = entity_graph.copy()
    owners, descriptions = {}, {}
    for entity, data in sorted(entity_graph.nodes(data=True)):
        ids = _parts(data.get('source_id'))
        descs = _parts(data.get('description'))
        aligned = len(ids) == len(descs)
        for i, cid in enumerate(ids):
            chunk = 'chunk:' + cid
            graph.add_node(chunk, paper_chunk=True)
            graph.add_edge(entity, chunk, paper_beta=True)
            owners.setdefault(cid, set()).add(entity)
            descriptions[(entity, cid)] = descs[i] if aligned else str(data.get('description', ''))
    return graph, owners, descriptions


def loaded_graph(storage):
    cached = getattr(storage, '_cpaper_loaded_graph', None)
    if cached is None or cached[0] is not storage._graph:
        graph, owners, descriptions = build_heterogeneous_graph(storage._graph)
        cached = (storage._graph, graph, owners, descriptions)
        storage._cpaper_loaded_graph = cached
    return cached[1:]


def enumerate_paths(graph, seed, *, include_chunks=True, n=PAPER_N, cap=PATH_CAP):
    """Deterministic DFS. The cap is an explicit fidelity limit, not exact top-k."""
    if seed not in graph:
        return [], False
    paths, stack = [], [(seed, (seed,), frozenset((seed,)))]
    while stack and len(paths) < cap:
        node, path, seen = stack.pop()
        if len(path) == n + 1:
            paths.append(path)
        else:
            neighbors = sorted((v for v in graph.neighbors(node)
                                if v not in seen and
                                (include_chunks or not graph.nodes[v].get('paper_chunk'))), reverse=True)
            for neighbor in neighbors:
                stack.append((neighbor, path + (neighbor,), seen | {neighbor}))
    return paths, len(paths) >= cap


def answer_nodes(entity_graph, starting, type_keywords):
    wanted = {str(t).strip().strip('"').strip("'").casefold() for t in type_keywords}
    return {s for s in starting if s in entity_graph and
            str(entity_graph.nodes[s].get('entity_type', '')).strip().strip('"').strip("'").casefold() in wanted}


def associated_text(cid, content, owners, descriptions, *, with_descriptions=True):
    if not with_descriptions:
        return content
    desc = list(dict.fromkeys(descriptions.get((entity, cid), '')
                              for entity in sorted(owners.get(cid, ()))
                              if descriptions.get((entity, cid), '')))
    return content + ('\n' + '\n'.join(desc) if desc else '')


async def rank_chunks(query, candidates, contents, owners, descriptions, embedder, *, with_descriptions=True):
    if not candidates:
        return []
    ids = sorted(cid for cid in candidates if cid in contents)
    texts = [query] + [associated_text(cid, contents[cid], owners, descriptions,
                                      with_descriptions=with_descriptions) for cid in ids]
    vectors = np.asarray(await embedder(texts), dtype=float)
    norms = np.linalg.norm(vectors, axis=1)
    scores = [(cid, float(np.dot(vectors[0], vectors[i + 1]) /
                          (norms[0] * norms[i + 1])) if norms[0] and norms[i + 1] else 0.0)
              for i, cid in enumerate(ids)]
    return sorted(scores, key=lambda row: (-row[1], row[0]))


def pack_chunks(ranked_ids, contents, token_count=None, limit=SOURCE_LIMIT, budget=SOURCE_TOKENS):
    token_count = token_count or (lambda text: len(encode_string_by_tiktoken(text)))
    kept, used = [], 0
    for cid in ranked_ids:
        if cid not in contents:
            continue
        size = token_count(contents[cid])
        if used + size <= budget:
            kept.append(cid)
            used += size
            if len(kept) >= limit:
                break
    return kept, used


async def build_context(ent_from_query, type_keywords, query, storage, entity_name_vdb,
                        relationships_vdb, chunks_vdb, text_chunks_db, embedder, query_param):
    started = time.perf_counter()
    entity_graph = storage._graph
    graph, owners, descriptions = loaded_graph(storage)
    anchors, by_time = temporal_active(query, text_chunks_db)
    metadata_only = bool(anchors) and os.environ.get('MINIRAG_TEMPORAL_H', '0') == '1'
    temporal_chunks = {cid for anchor in anchors for cid in by_time.get(anchor, ())}
    if anchors and not metadata_only:
        graph = graph.copy()
        for anchor in anchors:
            graph.add_node(anchor, temporal_anchor=True)
            for cid in by_time.get(anchor, ()):
                graph.add_edge(anchor, 'chunk:' + cid, temporal_gamma=True)
    pairs = {}
    seed_names = set()
    # Preserve each query-entity/seed pair, including a seed found by both vector routes.
    for keyword in ent_from_query:
        by_seed = {}
        names = await entity_name_vdb.query(keyword, top_k=query_param.top_k)
        for result in names:
            name = result['entity_name']
            if name in entity_graph:
                by_seed[name] = max(by_seed.get(name, float('-inf')), float(result['distance']))
        chunks = await chunks_vdb.query(keyword, top_k=query_param.top_k // 2)
        for result in chunks:
            for name in owners.get(result['id'], ()):
                by_seed[name] = max(by_seed.get(name, float('-inf')), float(result['distance']))
        for name, score in sorted(by_seed.items(), key=lambda row: (-row[1], row[0]))[:query_param.top_k]:
            pairs[(keyword, name)] = score
            seed_names.add(name)

    if anchors and not metadata_only:
        for anchor in anchors:
            pairs[(anchor, anchor)] = 1.0

    answers = answer_nodes(entity_graph, seed_names, type_keywords)
    all_paths, path_capped = {}, 0
    for pair in sorted(pairs):
        paths, capped = enumerate_paths(graph, pair[1], include_chunks=enabled('CHUNK_NODES'))
        all_paths[pair] = paths
        path_capped += int(capped)

    # Keep the code's E_alpha cardinality when its vector route is used as the comparator.
    vector_edges = await relationships_vdb.query(query, top_k=len(ent_from_query) * query_param.top_k)
    good = [r for r in vector_edges if r['src_id'] in seed_names | answers or r['tgt_id'] in seed_names | answers]
    candidate_edges = {frozenset((a, b)) for paths in all_paths.values() for path in paths
                       for a, b in zip(path, path[1:]) if a in entity_graph and b in entity_graph}
    if enabled('EQ2'):
        weights, _ = omega(graph, seed_names | answers | (set(anchors) if not metadata_only else set()),
                           candidate_edges, k=PAPER_K)
        selected = sorted(candidate_edges, key=lambda e: (-weights[e], tuple(sorted(e))))[:len(good)]
    else:
        selected = [frozenset((r['src_id'], r['tgt_id'])) for r in good]
        selected = list(dict.fromkeys(e for e in selected if e in candidate_edges))
        weights = {e: 1 for e in selected}
    selected_set = set(selected)

    path_dict = {}
    for pair, paths in all_paths.items():
        terms = {}
        for path in paths:
            path_edges = {frozenset((a, b)) for a, b in zip(path, path[1:])}
            terms[path] = [sum(node in answers for node in path),
                           sum(weights[e] for e in path_edges & selected_set) +
                           (sum(graph.edges[a, b].get('temporal_gamma', False)
                                for a, b in zip(path, path[1:])) if anchors and not metadata_only else 0)]
        path_dict[pair] = {'Score': pairs[pair], 'Path': terms}
    if enabled('EQ3'):
        kept_paths, _ = select_paper_paths(path_dict, {}, k=PAPER_K, query=query)
    else:
        kept_paths = path_dict

    graph_chunks = {cid for entry in kept_paths.values() for path in entry['Path']
                    for node in path if node in entity_graph
                    for cid in _parts(entity_graph.nodes[node].get('source_id'))}
    if anchors:
        graph_chunks.update(node[6:] for entry in kept_paths.values() for path in entry['Path']
                            for node in path if node.startswith('chunk:'))
        if metadata_only:
            graph_chunks.update(temporal_chunks)
    vector_chunks = await chunks_vdb.query(query, top_k=query_param.top_k // 2)
    vector_ids = [row['id'] for row in vector_chunks]
    candidates = (candidate_ids(graph_chunks, vector_ids, temporal_chunks,
                                expand=os.environ.get('MINIRAG_TEMPORAL_EXPAND', '1') == '1')
                  if anchors and enabled('INTERSECTION') else
                  graph_chunks & set(vector_ids) if enabled('INTERSECTION') else graph_chunks)
    records = await text_chunks_db.get_by_ids(sorted(candidates))
    contents = {cid: row['content'] for cid, row in zip(sorted(candidates), records) if row is not None}
    ranking = await rank_chunks(query, candidates, contents, owners, descriptions, embedder,
                                with_descriptions=enabled('EDGE_DESC'))
    ranked_ids = [cid for cid, _ in ranking]
    kept_ids, sources_tokens = pack_chunks(ranked_ids, contents)

    entity_rows = [[name, pairs.get(next((p for p in sorted(pairs) if p[1] == name), None), 0),
                    entity_graph.nodes[name].get('description', 'UNKNOWN')] for name in sorted(answers)]
    entity_rows = truncate_list_by_token_size(entity_rows, key=lambda row: row[2],
                                               max_token_size=query_param.max_token_for_node_context)
    entity_csv = list_of_list_to_csv([['entity', 'score', 'description']] + entity_rows)
    relation_rows = []
    for edge in selected:
        a, b = sorted(edge)
        data = entity_graph.get_edge_data(a, b) or {}
        relation_rows.append([len(relation_rows), a, b, data.get('description', ''),
                              data.get('keywords', ''), data.get('weight', ''), weights.get(edge, 1)])
    relation_rows = truncate_list_by_token_size(relation_rows, key=lambda row: row[3],
                                                 max_token_size=query_param.max_token_for_global_context)
    relation_csv = list_of_list_to_csv([['id', 'source', 'target', 'description', 'keywords', 'weight', 'rank']]
                                       + relation_rows)
    source_csv = list_of_list_to_csv([['id', 'content']] +
                                     [[i, contents[cid]] for i, cid in enumerate(kept_ids)])
    context = f'''\n-----Entities-----\n```csv\n{entity_csv}\n```\n-----Relationships-----\n```csv\n{relation_csv}\n```\n-----Sources-----\n```csv\n{source_csv}\n```\n'''
    log = os.environ.get('MINIRAG_CONTEXT_LOG', '').strip()
    if log:
        row = {'query': query, 'chunk_ids': kept_ids, 'ranked_ids': ranked_ids,
               'graph_ids': sorted(graph_chunks), 'vector_ids': vector_ids,
               'context_sha256': hashlib.sha256(context.encode('utf-8')).hexdigest(),
               'graph_seeds': len(seed_names), 'graph_paths': sum(len(p) for p in all_paths.values()),
               'path_pairs_capped': path_capped, 'n_pairs': len(pairs),
               'n_answers': len(answers), 'sources_tok': sources_tokens,
               'entities_tok': len(encode_string_by_tiktoken(entity_csv)),
               'retrieval_ms': round(1000 * (time.perf_counter() - started), 2),
               'fusion': 'cpaper'}
        with open(log, 'a', encoding='utf-8') as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    return context
