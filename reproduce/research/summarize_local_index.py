"""Build an aggregate-only local index stage report from durable raw artifacts."""

import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import re
import statistics


def describe(values):
    if not values:
        return {'n':0,'median':None,'min':None,'max':None,'sum':0}
    return {'n':len(values),'median':statistics.median(values),'min':min(values),'max':max(values),'sum':sum(values)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    if args.out.exists():
        p.error('Output exists; use a new report name')
    path=args.run_dir
    manifest_blob=(path/'index_manifest.json').read_bytes()
    manifest=json.loads(manifest_blob)
    request_blob=(path/'requests.jsonl').read_bytes()
    records=[json.loads(line) for line in request_blob.splitlines()]
    progress=[json.loads(line) for line in (path/'index_progress.jsonl').read_bytes().splitlines()]
    groups=defaultdict(list)
    for r in records:
        groups[r['phase']].append(r)
    by_phase={}
    per_chunk=defaultdict(Counter)
    for phase,rows in sorted(groups.items()):
        good=[r for r in rows if r['status']=='ok']
        by_phase[phase]={'requests':len(rows),'ok':len(good),'failed':len(rows)-len(good),
                         'length_truncated':sum(r['response'].get('done_reason')=='length' for r in good),
                         'latency_seconds':describe([r['latency_s'] for r in good]),
                         'prompt_tokens':describe([r['response'].get('prompt_eval_count',0) for r in good]),
                         'output_tokens':describe([r['response'].get('eval_count',0) for r in good])}
        for r in good:
            text=r['response'].get('message',{}).get('content','')
            # Diagnostic markers only; not claimed to reproduce the graph parser.
            per_chunk[r.get('chunk_id')]['requests']+=1
            per_chunk[r.get('chunk_id')]['entity_markers']+=len(re.findall(r'\(\s*["\x27]entity["\x27]',text,re.I))
            per_chunk[r.get('chunk_id')]['relationship_markers']+=len(re.findall(r'\(\s*["\x27]relationship["\x27]',text,re.I))
    done=len(manifest['completed_doc_ids'])
    seconds=sum(r['elapsed_s'] for r in progress)
    report={'purpose':'preliminary_local_pilot_stage_not_QA_benchmark','status':manifest['status'],
            'corpus_id':manifest['identity']['corpus_id'],'config_hash':manifest['config_hash'],
            'model_digest':manifest['identity']['model_digest'],'counts':manifest.get('counts'),
            'verification':manifest.get('verification'),'docs_done':done,'docs_expected':manifest['expected']['docs'],
            'requests_total':len(records),'requests_by_phase':by_phase,
            'all_responses_local_qwen':all(r.get('response',{}).get('model')=='qwen2.5:3b' for r in records if r['status']=='ok'),
            'requests_missing_chunk_id':sum(not r.get('chunk_id') for r in records),
            'diagnostic_chunks_without_relationship_markers':sum(c['relationship_markers']==0 for c in per_chunk.values()),
            'diagnostic_note':'regex marker counts are diagnostics, not exact extracted graph records',
            'measured_document_seconds':describe([r['elapsed_s'] for r in progress]),
            'preliminary_estimates':{'seconds_per_doc':seconds/done if done else None,
                  'pilot200_total_seconds':seconds/done*200 if done else None,
                  'full_pool11657_total_hours':seconds/done*11657/3600 if done else None,
                  'limitations':'small non-time-stratified sample; disk/graph growth, thermal throttling and restarts can change throughput'},
            'next_action':manifest.get('next_action'),
            'test_questions_or_answers_included':False,
            'provenance':{'index_manifest_sha256':hashlib.sha256(manifest_blob).hexdigest(),
                          'requests_sha256':hashlib.sha256(request_blob).hexdigest(),
                          'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_bytes((json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8'))
    print(json.dumps({'docs_done':done,'verification':report['verification'],'requests_by_phase':by_phase,
                      'preliminary_estimates':report['preliminary_estimates']},ensure_ascii=False))


if __name__=='__main__':
    main()
