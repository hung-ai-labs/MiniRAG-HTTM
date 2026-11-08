"""Freeze 20% analysis / 80% held-out 2Wiki split offline; no model calls.

Reuse the existing gold-title connected-component allocation. Full IDs, labels
and held-out questions stay under ignored processed storage. Never overwrite.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

from analyze_2wiki_splits import candidate_split, summarize

ROOT = Path(__file__).resolve().parents[2]


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def jb(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def jl(rows):
    return ''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n' for r in rows).encode('utf-8')


def csv_bytes(rows):
    buf = io.StringIO(newline='')
    writer = csv.DictWriter(buf, fieldnames=['query_id', 'Question', 'Gold Answer', 'Type'], lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode('utf-8')


def partition(rows, seed=13):
    # Existing allocator selects the requested small fraction as its second
    # result. Here that fraction is analysis/dev, reversing the OLD proposal.
    heldout, analysis, groups = candidate_split(rows, .2, seed)
    report = summarize(rows, analysis, heldout, groups)
    return analysis, heldout, report


def build(pool, raw_path, seed=13):
    manifest_blob = (pool / 'corpus_manifest.json').read_bytes()
    manifest = json.loads(manifest_blob)
    blobs = {}
    for name, info in manifest['outputs'].items():
        blob = (pool / name).read_bytes()
        if sha(blob) != info['sha256']:
            raise ValueError('Pool checksum mismatch: ' + name)
        blobs[name] = blob
    ids = set(manifest['query_ids'])
    raw_blob = raw_path.read_bytes()
    normalized = pool.parents[1] / 'manifest.json'
    if sha(normalized.read_bytes()) != manifest['source_manifest_sha256']:
        raise ValueError('Normalized manifest changed')
    if sha(raw_blob) != json.loads(normalized.read_bytes())['inputs']['dev.json']:
        raise ValueError('Official dev checksum changed')
    # Canonical pool order reproduces the earlier measured split allocation.
    import random
    all_rows = sorted(json.loads(raw_blob), key=lambda q: q['_id'])
    random.Random(manifest['seed']).shuffle(all_rows)
    rows = [q for q in all_rows if q['_id'] in ids]
    if len(rows) != 2000 or len(ids) != len(rows):
        raise ValueError('Expected the existing 2000-question pool')
    gold = {r['query_id']: r for r in map(json.loads, blobs['gold.jsonl'].splitlines())}
    queries = {r['query_id']: r for r in map(json.loads, blobs['queries.jsonl'].splitlines())}
    if set(gold) != ids or set(queries) != ids:
        raise ValueError('Query/gold ID coverage mismatch')
    dev, test, report = partition(rows, seed)
    outputs, split_ids = {}, {}
    for name, indices in [('internal_dev', dev), ('internal_test', test)]:
        chosen = sorted((rows[i] for i in indices), key=lambda q: q['_id'])
        split_ids[name] = [r['_id'] for r in chosen]
        csv_rows = [{'query_id': r['_id'], 'Question': queries[r['_id']]['question'],
                     'Gold Answer': gold[r['_id']]['answer'], 'Type': r['type']} for r in chosen]
        outputs[name + '.csv'] = csv_bytes(csv_rows)
        outputs[name + '_queries.jsonl'] = jl([queries[r['_id']] for r in chosen])
        outputs[name + '_gold.jsonl'] = jl([gold[r['_id']] for r in chosen])
        if name == 'internal_dev':
            outputs['smoke_dev20.csv'] = csv_bytes(csv_rows[:20])
    public = {'status': 'split_frozen_benchmark_not_started',
              'authority': 'User accepted 20% failure analysis / 80% held-out evaluation, 2026-10-30',
              'source_split': 'official_dev', 'corpus_id': manifest['corpus_id'], 'seed': seed,
              'requested_analysis_fraction': .2, 'allocation': 'existing gold-title component allocator; small partition assigned to analysis',
              'counts': report, 'corpus_manifest_sha256': sha(manifest_blob),
              'script_sha256': sha(Path(__file__).read_bytes()),
              'outputs': {k: sha(v) for k, v in sorted(outputs.items())},
              'limitations': ['Shared distractor titles may cross splits; see counts.',
                             'Not an official 2Wiki test split; do not inspect held-out labels for tuning.',
                             'Text near-duplicate audit from old split does not certify this split.',
                             'Filesystem separation is organizational, not access control.']}
    outputs['split_manifest.json'] = jb(public | {'query_ids': split_ids})
    return outputs, public


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pool', type=Path, default=ROOT / 'dataset/2WikiMultiHopQA/processed/pools/n2000_seed13')
    p.add_argument('--out', type=Path, default=ROOT / 'dataset/2WikiMultiHopQA/processed/splits/n2000_s13_dev20_test80')
    p.add_argument('--report', type=Path, default=ROOT / 'docs/research/env/2wiki_split_dev20_test80_seed13.json')
    p.add_argument('--check', action='store_true')
    a = p.parse_args()
    processed = (ROOT / 'dataset/2WikiMultiHopQA/processed').resolve()
    if processed not in a.out.resolve().parents:
        p.error('Full split outputs must remain under ignored processed storage')
    outputs, report = build(a.pool, ROOT / 'dataset/2WikiMultiHopQA/raw/extracted/dev.json')
    paths = {a.out / k: v for k, v in outputs.items()}
    paths[a.report] = jb(report)
    if a.check:
        if any(not path.exists() or path.read_bytes() != blob for path, blob in paths.items()):
            raise ValueError('Frozen split differs or is missing')
    else:
        if a.out.exists() or a.report.exists():
            p.error('Refusing overwrite; use --check')
        for path, blob in paths.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as f:
                f.write(blob)
    print(json.dumps({'checked': a.check, 'dev': report['counts']['internal_dev_count'],
                      'test': report['counts']['internal_test_count'],
                      'shared_gold_titles': report['counts']['gold_title_overlap']['shared_unique_titles']}))


if __name__ == '__main__':
    main()
