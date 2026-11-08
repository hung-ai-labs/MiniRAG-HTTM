"""Offline diagnostics for the fixed dev401 baseline; no model calls."""
import csv
import hashlib
import io
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPLIT = ROOT / 'dataset/2WikiMultiHopQA/processed/splits/n2000_s13_dev20_test80'
QA = ROOT / 'runs/2wiki/modal/baseline-dev-s101-c4/C0_s101'
JUDGE = ROOT / 'runs/2wiki/judge/baseline-dev-s101-fl35-v2'
OUT = ROOT / 'runs/2wiki/analysis/baseline-dev-s101-v2'


def norm(s):
    return ' '.join(unicodedata.normalize('NFKC', s).casefold().split())


def jsonl(path):
    rows = [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()]
    indexed = {r['query_id']: r for r in rows}
    assert len(rows) == len(indexed), path
    return indexed


def main():
    questions = {r['query_id']: r for r in csv.DictReader((SPLIT / 'internal_dev.csv').open(encoding='utf-8-sig'))}
    gold = jsonl(SPLIT / 'internal_dev_gold.jsonl')
    answers = jsonl(QA / 'answers.jsonl')
    contexts = jsonl(QA / 'contexts.jsonl')
    labels = {r['query_id']: r for r in csv.DictReader((JUDGE / 'per_question.csv').open(encoding='utf-8-sig'))}
    assert len(questions) == 401
    assert questions.keys() == gold.keys() == answers.keys() == contexts.keys() == labels.keys()
    trace_path = QA / 'context.jsonl'
    traces = defaultdict(list)
    for line in trace_path.read_text(encoding='utf-8').splitlines():
        t = json.loads(line)
        traces[t['context_sha256']].append(t)
    index = ROOT / 'indexes/2wiki-modal-n2000-s13-dev20test80'
    chunk_path = index / 'kv_store_text_chunks.json'
    chunks = json.loads(chunk_path.read_text(encoding='utf-8'))
    corpus_path = ROOT / 'dataset/2WikiMultiHopQA/processed/pools/n2000_seed13/docs.jsonl'
    needed_titles = {e['doc_id'] for g in gold.values() for e in g['evidence']}
    title_docs = {}
    for line in corpus_path.open(encoding='utf-8'):
        d = json.loads(line)
        if d['doc_id'] in needed_titles:
            title_docs[d['doc_id']] = d['minirag_doc_id']
    assert set(title_docs) == needed_titles
    def doc_ids(ids):
        assert all(c in chunks for c in ids)
        return {chunks[c]['full_doc_id'] for c in ids}
    records = []
    for qid, q in questions.items():
        context = contexts[qid]['context']
        context_hash = hashlib.sha256(context.encode('utf-8')).hexdigest()
        matches = [t for t in traces[context_hash] if t['query'] == q['Question']]
        assert matches, qid
        t = matches[-1]
        stages = {name: doc_ids(t[name]) for name in ('ranked_ids', 'chunk_ids', 'graph_ids', 'vector_ids')}
        match = re.search(r'-----Sources-----\s*```csv\s*(.*?)```', context, re.S)
        assert match, qid
        sources = list(csv.DictReader(io.StringIO(match.group(1))))
        content = '\n'.join(' '.join(row.values()) for row in sources)
        source_titles = {norm(row['content'].split('\n', 1)[0]) for row in sources}
        # Exact normalized substring is only a diagnostic proxy, not semantic sufficiency.
        evidence = gold[qid]['evidence']
        facts = [e['fact'] for e in evidence if e.get('mapping_status') == 'ok']
        hits = sum(bool(norm(f)) and norm(f) in norm(content) for f in facts)
        coverage = ('unmapped' if not facts else 'all' if hits == len(facts) == len(evidence) else 'some' if hits else 'none')
        records.append({'query_id': qid, 'type': q['Type'], 'question': q['Question'],
                        'gold': gold[qid]['answer'], 'answer': answers[qid]['answer'],
                        'majority': labels[qid]['majority'], 'source_rows': len(sources),
                        'mapped_facts': len(facts), 'total_evidence': len(evidence),
                        'fact_hits': hits, 'source_fact_coverage_proxy': coverage,
                        'missing_supporting_source_titles': sorted({e['doc_id'] for e in evidence if norm(e['doc_id']) not in source_titles}),
                        'supporting_title_trace': [{'title': title, **{name: title_docs[title] in ids for name, ids in stages.items()}}
                                                   for title in sorted({e['doc_id'] for e in evidence})],
                        'evidence': evidence, 'context': context,
                        'manual_stage': 'unreviewed', 'manual_reason': ''})
    OUT.mkdir(parents=True, exist_ok=True)
    # Deterministic stratification: up to five errors and five neither per type.
    sample = []
    for typ in sorted({r['type'] for r in records}):
        for label in ('error', 'neither'):
            group = [r for r in records if r['type'] == typ and r['majority'] == label]
            group.sort(key=lambda r: hashlib.sha256(('dev-review-v1:' + r['query_id']).encode()).hexdigest())
            sample.extend(group[:5])
    for filename, rows in [('diagnostics.jsonl', records), ('manual_review_sample.jsonl', sample)]:
        (OUT / filename).write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
    table = defaultdict(Counter)
    for r in records:
        table[r['type']][r['majority']] += 1
    cross = defaultdict(Counter)
    for r in records:
        cross[r['majority']][r['source_fact_coverage_proxy']] += 1
    summary = {'n': len(records), 'by_type_majority': dict(table), 'fact_proxy_by_label': dict(cross),
               'manual_sample_n': len(sample), 'manual_review_complete': False,
               'limitations': 'Exact normalized fact substring in Sources only; absence may be truncation or formatting, presence is not proof of sufficient reasoning evidence. No automatic causal taxonomy.'}
    (OUT / 'diagnostics_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    annotation_path = ROOT / 'docs/research/dev401_review_annotations.json'
    if annotation_path.exists():
        annotations = json.loads(annotation_path.read_text(encoding='utf-8'))
        assert set(annotations['cases']) == {r['query_id'] for r in sample}
        reviewed = []
        for r in sample:
            category, reason = annotations['cases'][r['query_id']]
            reviewed.append(r | {'review_category': category, 'review_reason': reason,
                                 'reviewer': annotations['reviewer'],
                                 'manual_stage': 'causal_stage_unresolved'})
        (OUT / 'reviewed_sample.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in reviewed), encoding='utf-8')
        failures = [r for r in records if r['majority'] in ('error', 'neither')]
        by_type = {}
        for typ in sorted(table):
            group = [r for r in failures if r['type'] == typ]
            by_type[typ] = {'failed_n': len(group), 'at_least_one_supporting_title_absent_from_sources': sum(bool(r['missing_supporting_source_titles']) for r in group)}
        review_summary = {'reviewed_n': len(reviewed), 'reviewer': annotations['reviewer'],
                          'sample_category_counts': dict(Counter(r['review_category'] for r in reviewed)),
                          'all_failed_dev_title_diagnostics': by_type,
                          'source_hashes': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                                            [Path(__file__), annotation_path, SPLIT / 'internal_dev.csv', SPLIT / 'internal_dev_gold.jsonl', QA / 'answers.jsonl', QA / 'contexts.jsonl', trace_path, chunk_path, corpus_path, JUDGE / 'per_question.csv']},
                          'scope': 'Observable sample categories; no independent human validation, no six-stage causal distribution, no score edits, no test data.'}
        (OUT / 'review_summary.json').write_text(json.dumps(review_summary, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(review_summary, ensure_ascii=False))
    missing_stage_counts = Counter()
    affected = defaultdict(set)
    for r in records:
        if r['majority'] == 'accurate':
            continue
        for t in r['supporting_title_trace']:
            if t['chunk_ids']:
                continue
            stage = 'ranked_but_not_in_final_sources' if t['ranked_ids'] else 'absent_from_ranked_candidates'
            missing_stage_counts[stage] += 1
            affected[stage].add(r['query_id'])
            if not t['ranked_ids'] and t['vector_ids']:
                missing_stage_counts['absent_ranked_but_available_in_vector_candidates'] += 1
                affected['absent_ranked_but_available_in_vector_candidates'].add(r['query_id'])
    trace_summary = {'missing_supporting_title_occurrences': dict(missing_stage_counts),
                     'affected_failed_queries_nonexclusive': {k: len(v) for k, v in affected.items()},
                     'limitations': 'Document-level presence only; a kept chunk may omit the necessary sentence. Candidate absence does not identify extraction, entity mapping, path discovery or ranking root cause.'}
    (OUT / 'trace_summary.json').write_text(json.dumps(trace_summary, indent=2), encoding='utf-8')
    print(json.dumps(trace_summary))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
