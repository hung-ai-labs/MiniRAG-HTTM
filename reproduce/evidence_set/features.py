"""Candidate pools, label-free features, and the training export for the scorer.

Every feature is computable at query time from the native retrieval capture
(pool.py) and the corpus; none reads Gold Answer or Evidence. `label` is added
by export() for training and evaluation only.

    .venv/bin/python -m reproduce.evidence_set.features export [--pool all+date]
"""
import argparse
import json
import math
from functools import lru_cache

from reproduce.graph_ablation.study import ROOT, lines, write, sha
from reproduce.evidence_set.data import corpus, gold, folds
from reproduce.evidence_set.pool import OUT

FEATURES = ('native_rank', 'native_rank_log', 'in_native30', 'graph_rank', 'graph_score', 'graph_score_rel',
            'in_graph', 'in_dense30', 'dense_rank', 'date_match', 'time_boosted', 'n_seed_paths',
            'n_keyword_groups', 'is_path_head', 'is_continuation', 'chunk_order', 'doc_chunks',
            'tokens')
# BM25 is NOT a feature (user decision 11/11: no BM25 / RRF in the method). bm25_scores() below
# exists only for the BM25_RERANK comparison arm in evaluate.py.


@lru_cache(maxsize=1)
def bm25():
    from minirag.bm25 import BM25Index
    chunks, _, _ = corpus()
    return BM25Index({c: v['content'] for c, v in chunks.items()})


def bm25_scores(question):
    idx = bm25()
    from minirag.bm25 import tokenize, STOP
    terms = [w for w in tokenize(question) if w not in STOP]
    out = {}
    for cid, tf, length in zip(idx.ids, idx.tf, idx.lens):
        out[cid] = sum(idx.idf[w] * tf[w] * (idx.k1 + 1) /
                       (tf[w] + idx.k1 * (1 - idx.b + idx.b * length / idx.avg)) for w in terms if tf.get(w))
    return out


def pool_of(r, name):
    """Candidate pool by name (see coverage.py). Native order first, expansions appended."""
    from reproduce.evidence_set.coverage import variants
    return variants(r)[name]


def featurize(r, pool):
    chunks, _, by_doc = corpus()
    native = {c: i for i, c in enumerate(r['final_full'])}
    graph = {c: i for i, c in enumerate(r['graph_full'])}
    dense = {c: i for i, c in enumerate(r['dense_ids'])}
    top = max(r['graph_scores'].values(), default=1.0) or 1.0
    dates = {c for a in r['anchors'] for c in r['date_chunks'].get(a, ())}
    boosted = {c for v in r['boosted'].values() for c in v}
    paths, groups, heads = {}, {}, set()
    for kw, seeds in r['groups'].items():
        for s in seeds:
            for c in s['path']:
                paths[c] = paths.get(c, 0) + 1
                groups.setdefault(c, set()).add(kw)
            if s['path']:
                heads.add(s['path'][0])
    far = len(pool)
    out = []
    for c in pool:
        g = r['graph_scores'].get(c, 0.0)
        out.append({'chunk_id': c, 'features': {
            'native_rank': native.get(c, far), 'native_rank_log': math.log1p(native.get(c, far)),
            'in_native30': int(native.get(c, far) < 30), 'graph_rank': graph.get(c, far),
            'graph_score': g, 'graph_score_rel': g / top, 'in_graph': int(c in graph),
            'in_dense30': int(c in dense), 'dense_rank': dense.get(c, 30), 'date_match': int(c in dates),
            'time_boosted': int(c in boosted), 'n_seed_paths': paths.get(c, 0),
            'n_keyword_groups': len(groups.get(c, ())), 'is_path_head': int(c in heads),
            'is_continuation': int(chunks[c]['time'] is None), 'chunk_order': chunks[c]['order'],
            'doc_chunks': len(by_doc[chunks[c]['doc']]), 'tokens': chunks[c]['tokens']}})
        assert tuple(out[-1]['features']) == FEATURES
    return out


def export(pool_name, preview=False):
    chunks, _, _ = corpus()
    rows = lines(OUT / 'pools_dev200.jsonl')
    if not preview:
        assert len(rows) == 200, f'only {len(rows)} pools captured; use --preview for a partial schema file'
    fold = folds([r['question'] for r in rows])
    dest = OUT / ('codex_preview' if preview else 'codex')
    dest.mkdir(parents=True, exist_ok=True)
    with (dest / 'chunks.jsonl').open('w') as f:
        for c, v in sorted(chunks.items()):
            f.write(json.dumps({'chunk_id': c, **v}, ensure_ascii=False) + '\n')
    stats = {'questions': 0, 'labelled': 0, 'candidates': 0, 'positives': 0}
    with (dest / 'train_dev200.jsonl').open('w') as f:
        for r in rows:
            typ, sets, status = gold(r['question'])
            pool = pool_of(r, pool_name)
            cands = featurize(r, pool)
            for x in cands:
                hits = [i for i, g in enumerate(sets or []) if x['chunk_id'] in g]
                x['label'] = int(bool(hits))
                x['evidence_index'] = hits
            f.write(json.dumps({'id': r['id'], 'question': r['question'], 'type': typ, 'status': status,
                                'fold': fold[r['question']], 'n_evidence': len(sets or []),
                                'gold_in_pool': bool(sets) and all(set(pool) & g for g in sets),
                                'baseline_kept': r['baseline_kept'], 'candidates': cands},
                               ensure_ascii=False) + '\n')
            stats['questions'] += 1
            stats['labelled'] += status == 'labelled'
            stats['candidates'] += len(cands)
            stats['positives'] += sum(x['label'] for x in cands)
    write(dest / 'export_manifest.json', {
        **stats, 'pool': pool_name, 'features': list(FEATURES), 'folds': 'grouped by gold document, 5 folds',
        'fold_sizes': {f: sum(v == f for v in fold.values()) for f in range(5)},
        'pools_sha256': sha((OUT / 'pools_dev200.jsonl').read_bytes()),
        'train_sha256': sha((dest / 'train_dev200.jsonl').read_bytes()),
        'chunks_sha256': sha((dest / 'chunks.jsonl').read_bytes()),
        'label_rule': 'label=1 iff the chunk holds the Time header of an Evidence stamp of the question'})
    print(json.dumps(stats))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('step', choices=('export',))
    ap.add_argument('--pool', default=None, help='pool name; default = chosen_pool from coverage_dev200.json')
    ap.add_argument('--preview', action='store_true',
                    help='partial export to codex_preview/ (schema only; folds and pool are NOT final)')
    a = ap.parse_args()
    name = a.pool or json.loads((OUT / 'coverage_dev200.json').read_text())['chosen_pool']
    export(name, a.preview)
