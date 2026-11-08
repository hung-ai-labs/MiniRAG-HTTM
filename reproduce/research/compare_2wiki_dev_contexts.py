"""Compare fixed dev401 C0/C1 contexts offline, without inference or tuning."""
import argparse
import csv
import hashlib
import io
import json
import math
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(text):
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())


def read_rows(path):
    rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    result = {r['query_id']: r for r in rows}
    assert len(result) == len(rows), f'Duplicate IDs: {path}'
    return result


def distribution(values):
    values = sorted(values)
    return {'n': len(values), 'median': statistics.median(values) if values else None,
            'p95_nearest_rank': values[math.ceil(.95 * len(values)) - 1] if values else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--c1', type=Path, default=ROOT / 'runs/2wiki/analysis/c1-context-dev401-s101/C1_s101')
    args = parser.parse_args()
    c0 = ROOT / 'runs/2wiki/modal/baseline-dev-s101-c4/C0_s101'
    split = ROOT / 'dataset/2WikiMultiHopQA/processed/splits/n2000_s13_dev20_test80'
    paths = [split / 'internal_dev.csv', split / 'internal_dev_gold.jsonl']
    manifest_paths = [directory.parent / 'run_manifest.json' for directory in (c0, args.c1)]
    manifests = [json.loads(p.read_text(encoding='utf-8')) for p in manifest_paths]
    assert manifests[0] == manifests[1], 'C0/C1 run conditions differ; investigate before comparing.'
    assert manifests[0]['dataset_id'] == '2wiki' and manifests[0]['seed'] == 101
    keyword_paths = [directory.parent / 'kw_s101.jsonl' for directory in (c0, args.c1)]
    assert digest(keyword_paths[0]) == digest(keyword_paths[1]), 'Keyword caches differ.'
    paths += manifest_paths + keyword_paths
    questions = {r['query_id']: r for r in csv.DictReader(paths[0].open(encoding='utf-8-sig'))}
    gold = read_rows(paths[1])
    assert len(questions) == 401 and questions.keys() == gold.keys()
    chunk_path = ROOT / 'indexes/2wiki-modal-n2000-s13-dev20test80/kv_store_text_chunks.json'
    chunks = json.loads(chunk_path.read_text(encoding='utf-8'))
    corpus = ROOT / 'dataset/2WikiMultiHopQA/processed/pools/n2000_seed13/docs.jsonl'
    needed = {e['doc_id'] for r in gold.values() for e in r['evidence']}
    title_ids = {}
    for line in corpus.open(encoding='utf-8'):
        d = json.loads(line)
        if d['doc_id'] in needed:
            title_ids[d['doc_id']] = d['minirag_doc_id']
    assert set(title_ids) == needed
    paths += [chunk_path, corpus]
    methods = {}
    status_counts = {}
    for name, directory in [('C0', c0), ('C1', args.c1)]:
        cp, lp = directory / 'contexts.jsonl', directory / 'context.jsonl'
        paths += [cp, lp]
        contexts = read_rows(cp)
        assert contexts.keys() == questions.keys(), f'Incomplete {name}: {len(contexts)}/401'
        traces = defaultdict(list)
        for line in lp.read_text(encoding='utf-8').splitlines():
            t = json.loads(line)
            traces[t['context_sha256']].append(t)
        status_counts[name] = dict(Counter(r['status'] for r in contexts.values()))
        methods[name] = {}
        for qid, r in contexts.items():
            context = r['context'] or ''
            sha = hashlib.sha256(context.encode('utf-8')).hexdigest()
            traces_for_query = [t for t in traces[sha] if t['query'] == questions[qid]['Question']]
            if r['status'] == 'ok':
                assert traces_for_query, f'No matching trace: {name}/{qid}'
                t = traces_for_query[-1]
                assert t['fusion'] == ('' if name == 'C0' else 'vector_bm25'), f'Unexpected fusion for {name}'
                assert len(t['chunk_ids']) == t['n_chunks']
                docs = {chunks[c]['full_doc_id'] for c in t['chunk_ids']}
                match = re.search(r'-----Sources-----\s*```csv\s*(.*?)```', context, re.S)
                assert match
                sources = list(csv.DictReader(io.StringIO(match.group(1))))
                assert len(sources) == t['n_chunks']
                source_text = '\n'.join(s['content'] for s in sources)
            else:
                t, docs, source_text = {}, set(), ''
            expected = {e['doc_id'] for e in gold[qid]['evidence']}
            present = {title for title in expected if title_ids[title] in docs}
            facts = [e['fact'] for e in gold[qid]['evidence'] if e.get('mapping_status') == 'ok' and e.get('fact')]
            methods[name][qid] = {'status': r['status'], 'context_sha256': sha,
                'sources_sha256': hashlib.sha256(source_text.encode('utf-8')).hexdigest(),
                'entities_sha256': hashlib.sha256(context.split('-----Sources-----')[0].encode('utf-8')).hexdigest(),
                'graph_candidate_ids_sha256': hashlib.sha256(json.dumps(t.get('graph_ids', []), separators=(',', ':')).encode()).hexdigest(),
                'vector_candidate_ids_sha256': hashlib.sha256(json.dumps(t.get('vector_ids', []), separators=(',', ':')).encode()).hexdigest(),
                'supporting_titles_present': sorted(present), 'supporting_titles_expected': len(expected),
                'supporting_titles_hit': len(present), 'all_supporting_titles_present': expected == present,
                'mapped_fact_hits_proxy': sum(norm(f) in norm(source_text) for f in facts),
                'mapped_facts_expected': len(facts), 'sources_tokens': t.get('sources_tok'),
                'entity_tokens': t.get('entities_tok'), 'source_chunks': t.get('n_chunks'),
                'retrieval_s': r.get('retrieval_s')}
    per_query = []
    for qid, q in questions.items():
        a, b = methods['C0'][qid], methods['C1'][qid]
        per_query.append({'query_id': qid, 'type': q['Type'], 'C0': a, 'C1': b,
            'supporting_title_hit_delta': b['supporting_titles_hit'] - a['supporting_titles_hit'],
            'gained_titles': sorted(set(b['supporting_titles_present']) - set(a['supporting_titles_present'])),
            'lost_titles': sorted(set(a['supporting_titles_present']) - set(b['supporting_titles_present']))})
    def summary(rows):
        result = {'n': len(rows)}
        for name in methods:
            data = [r[name] for r in rows]
            expected = sum(x['supporting_titles_expected'] for x in data)
            hit = sum(x['supporting_titles_hit'] for x in data)
            result[name] = {'supporting_titles_hit': hit, 'supporting_titles_expected': expected,
                'supporting_title_recall_micro_proxy': hit / expected,
                'queries_all_supporting_titles_present': sum(x['all_supporting_titles_present'] for x in data),
                'mapped_fact_hits_proxy': sum(x['mapped_fact_hits_proxy'] for x in data),
                'mapped_facts_expected': sum(x['mapped_facts_expected'] for x in data),
                **{field: distribution([x[field] for x in data if x[field] is not None]) for field in
                   ['sources_tokens', 'entity_tokens', 'source_chunks', 'retrieval_s']}}
        result['title_hit_delta_queries'] = dict(Counter('up' if r['supporting_title_hit_delta'] > 0 else 'down' if r['supporting_title_hit_delta'] < 0 else 'same' for r in rows))
        result['all_titles_transitions'] = dict(Counter(f"{r['C0']['all_supporting_titles_present']}->{r['C1']['all_supporting_titles_present']}" for r in rows))
        result['identical_contexts'] = sum(r['C0']['context_sha256'] == r['C1']['context_sha256'] for r in rows)
        result['identical_sources'] = sum(r['C0']['sources_sha256'] == r['C1']['sources_sha256'] for r in rows)
        result['identical_entity_sections'] = sum(r['C0']['entities_sha256'] == r['C1']['entities_sha256'] for r in rows)
        result['identical_graph_candidate_lists'] = sum(r['C0']['graph_candidate_ids_sha256'] == r['C1']['graph_candidate_ids_sha256'] for r in rows)
        result['identical_vector_candidate_lists'] = sum(r['C0']['vector_candidate_ids_sha256'] == r['C1']['vector_candidate_ids_sha256'] for r in rows)
        return result
    report = {'all': summary(per_query), 'by_type': {typ: summary([r for r in per_query if r['type'] == typ]) for typ in sorted({r['type'] for r in per_query})},
        'statuses': status_counts, 'source_hashes': {str(p.relative_to(ROOT)): digest(p) for p in paths + [Path(__file__)]},
        'limits': ['Gold used only after retrieval.', 'Title presence and substring fact hits are proxies, not semantic evidence sufficiency or QA accuracy.',
                   'Separate CPU measurement times: latency is descriptive, not a speedup estimate.', 'Only dev401/seed101, no held-out data, no generation or judge calls.']}
    out = args.c1.parent / 'comparison'
    out.mkdir(exist_ok=True)
    (out / 'per_query.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in per_query), encoding='utf-8')
    (out / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'all': report['all'], 'statuses': status_counts}, ensure_ascii=False))


if __name__ == '__main__':
    main()
