"""Materialize a measured 2Wiki question pool and an unexecuted pilot document set.

No model calls or train/test split. Full IDs and labeled files stay in ignored
processed storage; the public report contains counts/checksums only.
"""

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import random


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def jb(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)+'\n').encode('utf-8')


def jl(rows):
    return ''.join(json.dumps(r, ensure_ascii=False, sort_keys=True)+'\n' for r in rows).encode('utf-8')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--public-report', type=Path, required=True)
    p.add_argument('--size', type=int, default=2000)
    p.add_argument('--seed', type=int, default=13)
    p.add_argument('--pilot-docs', type=int, default=200)
    p.add_argument('--check', action='store_true')
    args = p.parse_args()
    root = args.repo.resolve()
    processed = root/'dataset/2WikiMultiHopQA/processed'
    if args.out.resolve() == processed or processed not in args.out.resolve().parents:
        p.error('Output must be a new subdirectory of the ignored processed directory')
    source_manifest_blob = (processed/'manifest.json').read_bytes()
    source_manifest = json.loads(source_manifest_blob)
    measure_blob = (root/'docs/research/env/2wiki_pool_measurements_seed13.json').read_bytes()
    measurements = json.loads(measure_blob)
    if sha(source_manifest_blob) != measurements['provenance']['processed_manifest_sha256']:
        raise ValueError('Normalized source manifest changed since measurements')
    if args.seed != measurements['sampling']['seed']:
        raise ValueError('Seed differs from measured pools')
    measured = next((r for r in measurements['results'] if r['n_queries'] == args.size), None)
    if measured is None:
        raise ValueError('Pool size has not been measured')
    source_blobs = {}
    for name, expected in source_manifest['outputs'].items():
        blob = (processed/name).read_bytes()
        if sha(blob) != expected['sha256']:
            raise ValueError('Normalized checksum mismatch: '+name)
        source_blobs[name] = blob
    raw_blob = (root/'dataset/2WikiMultiHopQA/raw/extracted/dev.json').read_bytes()
    if sha(raw_blob) != source_manifest['inputs']['dev.json']:
        raise ValueError('Raw dev checksum mismatch')
    raw = sorted(json.loads(raw_blob), key=lambda q:q['_id'])
    random.Random(args.seed).shuffle(raw)
    pool = raw[:args.size]
    ids = {q['_id'] for q in pool}
    identity = sha(json.dumps(sorted(ids), ensure_ascii=False, separators=(',', ':')).encode())
    if identity != measured['query_ids_sha256']:
        raise ValueError('Pool query identity differs from measurements')
    titles = {t for q in pool for t, _ in q['context']}
    selected = {}
    for name, key, keep in [('docs.jsonl', 'doc_id', titles), ('queries.jsonl','query_id',ids),('gold.jsonl','query_id',ids)]:
        selected[name] = sorted([r for r in map(json.loads, source_blobs[name].splitlines()) if r[key] in keep], key=lambda r:r[key])
    if len(selected['docs.jsonl']) != measured['unique_docs'] or len(selected['queries.jsonl']) != args.size or len(selected['gold.jsonl']) != args.size:
        raise ValueError('Selected document/query/gold counts mismatch')
    if not 0 < args.pilot_docs <= len(titles):
        p.error('Invalid pilot document count')
    pilot_titles = set(random.Random(args.seed).sample(sorted(titles), args.pilot_docs))
    pilot = [d for d in selected['docs.jsonl'] if d['doc_id'] in pilot_titles]
    buf = io.StringIO(newline='')
    writer = csv.writer(buf, lineterminator='\n')
    writer.writerow(['Question','Gold Answer','Type','query_id'])
    for q, g in zip(selected['queries.jsonl'],selected['gold.jsonl']):
        assert q['query_id'] == g['query_id']
        writer.writerow([q['question'],g['answer'],q['type'],q['query_id']])
    output = {name:jl(rows) for name,rows in selected.items()}
    output['questions.csv'] = buf.getvalue().encode('utf-8')
    output['pilot_docs.jsonl'] = jl(pilot)
    corpus_id = '2wiki-n'+str(args.size)+'-s'+str(args.seed)+'-'+sha(output['docs.jsonl'])[:12]
    counts = {'queries':args.size,'docs':len(titles),'chunks_measured':measured['unique_chunks'],
              'nominal_index_calls':measured['nominal_index_calls_extract_plus_one_glean'],
              'pilot_docs':len(pilot),'queries_by_type':dict(sorted(Counter(q['type'] for q in selected['queries.jsonl']).items()))}
    corpus = {'status':'corpus_materialized_split_not_frozen_index_not_started','corpus_id':corpus_id,
              'dataset':'2WikiMultiHopQA','source_split':'official_dev','n_questions':args.size,'seed':args.seed,
              'selection':'sort _id then shuffle seed; corpus union of every context paragraph, gold and distractors',
              'query_ids':sorted(ids),'doc_ids':sorted(titles),'counts':counts,
              'split_manifest':None,'backup_verified':False,
              'source_manifest_sha256':sha(source_manifest_blob),'measurements_sha256':sha(measure_blob),
              'script_sha256':sha(Path(__file__).read_bytes()),
              'outputs':{name:{'sha256':sha(blob),'bytes':len(blob)} for name,blob in sorted(output.items())}}
    output['corpus_manifest.json'] = jb(corpus)
    output['pilot_manifest.json'] = jb({'status':'selected_not_indexed','corpus_id':corpus_id,
                                      'seed':args.seed,'selection':'sample sorted corpus doc IDs without using gold relevance',
                                      'doc_ids':sorted(pilot_titles),'n_docs':len(pilot),
                                      'docs_sha256':sha(output['pilot_docs.jsonl']),
                                      'corpus_manifest_sha256':sha(output['corpus_manifest.json'])})
    public = jb({'status':corpus['status'],'corpus_id':corpus_id,'counts':counts,'seed':args.seed,
                 'selection_authority':'user shared team message choosing 2000 questions; 80/20 split remains a proposal',
                 'full_ids_location':'ignored processed pool directory only','split_frozen':False,
                 'local_model_condition':'Qwen2.5-3B-Instruct GGUF Q4_K_M','benchmark_started':False,
                 'corpus_manifest_sha256':sha(output['corpus_manifest.json']),
                 'pilot_manifest_sha256':sha(output['pilot_manifest.json']),
                 'file_sha256':{name:sha(blob) for name,blob in sorted(output.items())}})
    paths = {args.out/name:blob for name,blob in output.items()}
    paths[args.public_report] = public
    if args.check:
        for path,blob in paths.items():
            if not path.exists() or path.read_bytes()!=blob:
                raise ValueError('Output missing or differs: '+str(path))
        print('CHECK OK: corpus, pilot and public report exactly recomputed')
        return
    if any(path.exists() for path in paths):
        p.error('Some output already exists; use --check or a new directory/report')
    for path,blob in paths.items():
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(blob)
    print(json.dumps({'corpus_id':corpus_id,'counts':counts,'split_frozen':False,'index_started':False}))


if __name__=='__main__':
    main()
