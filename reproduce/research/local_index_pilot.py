"""Bounded local 2Wiki indexing stages with raw requests and immutable checkpoints.

Each invocation indexes at most --max-new-docs (default 10) of the fixed 200-doc
pilot, then verifies stores and estimates remaining work. No QA/judge. Resume
requires identical sources/config and exact committed store hashes. Torn writes
are rejected; previous immutable checkpoints remain available for a recovery fork.
"""

import argparse
import asyncio
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from local_qwen import LocalQwen, OPTIONS, MODEL, PINNED_MODEL_DIGEST, append, now, write_json

ROOT = Path(__file__).resolve().parents[2]


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def identity_hash(value):
    return sha(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


def stores_hash(index):
    return {p.name: sha(p.read_bytes()) for p in sorted(index.iterdir())
            if p.is_file() and p.suffix in ('.json', '.graphml')}


def require_matching_identity(stored, expected):
    if stored['identity'] != expected:
        raise ValueError('Resume identity differs: config, docs, model or source changed')


def require_clean_checkpoint(index, stored):
    actual = stores_hash(index)
    if actual != stored.get('committed_store_sha256', {}):
        raise ValueError('Stores differ from last committed checkpoint; refusing in-place repair. Preserve this index and recover into a NEW directory from an immutable checkpoint.')


def check_paths(index, run, root, resume):
    for p in (index, run):
        if p.is_symlink():
            raise ValueError('Symlink output not accepted')
    if index.resolve().parent != (root/'indexes').resolve() or not index.name.startswith('2wiki-local-q4km-pilot'):
        raise ValueError('Index must be a direct child indexes/2wiki-local-q4km-pilot*')
    if (root/'runs/2wiki/local').resolve() not in run.resolve().parents:
        raise ValueError('Run must be inside runs/2wiki/local')
    if resume:
        if not index.is_dir() or not (run/'index_manifest.json').is_file():
            raise ValueError('Nothing to resume')
    elif index.exists() or run.exists():
        raise ValueError('Fresh run refuses existing index/run directories')


def verify(index, docs, chunk_map):
    import networkx as nx
    def load(name):
        return json.loads((index/name).read_bytes())
    status, chunks = load('kv_store_doc_status.json'), load('kv_store_text_chunks.json')
    full = load('kv_store_full_docs.json')
    vectors = {r['__id__'] for r in load('vdb_chunks.json')['data']}
    extracted = set(load('extracted_chunks.json'))
    graph = nx.read_graphml(index/'graph_chunk_entity_relation.graphml')
    sources = set()
    for attrs in [a for _, a in graph.nodes(data=True)] + [a for _, _, a in graph.edges(data=True)]:
        sources.update(s for s in str(attrs.get('source_id', '')).split('<SEP>') if s)
    expected_docs = {d['minirag_doc_id'] for d in docs}
    expected_chunks = {cid for cid, c in chunk_map.items() if c['full_doc_id'] in expected_docs}
    checks = {'all_docs_processed': set(status) == expected_docs and all(s['status']=='processed' for s in status.values()),
              'full_docs_match': set(full)==expected_docs,
              'expected_chunks_match': set(chunks)==expected_chunks,
              'chunk_doc_links': all(c['full_doc_id']==chunk_map[cid]['full_doc_id'] for cid,c in chunks.items() if cid in chunk_map),
              'chunk_vectors_match': vectors==set(chunks),
              'all_chunks_extracted': extracted==expected_chunks,
              'graph_sources_exist': sources<=set(chunks)}
    return checks, {'docs':len(full),'chunks':len(chunks),'nodes':graph.number_of_nodes(),'edges':graph.number_of_edges(),
                    'chunks_without_graph_sources':len(set(chunks)-sources)}


async def process(args, docs, chunks, manifest, client):
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TRANSFORMERS_OFFLINE']='1'
    sys.path.insert(0,str(ROOT))
    from transformers import AutoModel, AutoTokenizer
    from minirag import MiniRAG
    from minirag.llm.hf import hf_embed
    from minirag.utils import EmbeddingFunc
    name='sentence-transformers/all-MiniLM-L6-v2'
    tokenizer=AutoTokenizer.from_pretrained(name,local_files_only=True)
    embed_model=AutoModel.from_pretrained(name,local_files_only=True).to('cpu')
    embed_model.eval()
    async def embed(texts):
        return await hf_embed(texts,tokenizer=tokenizer,embed_model=embed_model)
    async def complete(prompt,system_prompt=None,history_messages=None,**kwargs):
        texts=[prompt]+[m.get('content','') for m in history_messages or [] if m.get('role')=='user']
        found=[(len(c['content']),cid) for cid,c in chunks.items() if any(c['content'] in t for t in texts)]
        if not found:
            raise ValueError('Cannot attribute index request to a source chunk')
        client.chunk_id=max(found)[1]
        client.doc_id=chunks[client.chunk_id]['doc_id']
        return await client.complete(prompt,system_prompt=system_prompt,history_messages=history_messages,**kwargs)
    client.phase='index'
    rag=MiniRAG(working_dir=str(args.index),llm_model_func=complete,llm_model_name=MODEL,
                llm_model_max_async=1,llm_model_max_token_size=200,
                embedding_func=EmbeddingFunc(embedding_dim=384,max_token_size=1000,func=embed),
                embedding_func_max_async=1,enable_llm_cache=False,chunk_token_size=1200,
                chunk_overlap_token_size=100,entity_extract_max_gleaning=1)
    already=set(manifest['completed_doc_ids'])
    todo=[d for d in docs if d['minirag_doc_id'] not in already][:args.max_new_docs]
    for d in todo:
        started=time.perf_counter()
        append(args.run_dir/'events.jsonl',{'at':now(),'event':'doc_start','doc_id':d['doc_id']})
        await rag.ainsert(d['text'])
        already.add(d['minirag_doc_id'])
        manifest['completed_doc_ids']=sorted(already)
        manifest['committed_store_sha256']=stores_hash(args.index)
        manifest['last_committed_at']=now()
        # MiniRAG.ainsert has persisted every store before a doc is committed.
        atomic_manifest(args.run_dir/'index_manifest.json',manifest)
        elapsed=time.perf_counter()-started
        append(args.run_dir/'index_progress.jsonl',{'at':now(),'doc_id':d['doc_id'],
               'minirag_doc_id':d['minirag_doc_id'],'elapsed_s':elapsed,'docs_done':len(already)})
        print(f'{len(already)}/{len(docs)} docs; last_doc_s={elapsed:.2f}',flush=True)
    return [d for d in docs if d['minirag_doc_id'] in already]


def atomic_manifest(path,value):
    temp=path.with_suffix('.json.tmp')
    write_json(temp,value)
    os.replace(temp,path)


def stats(requests,done,total):
    good=[r for r in requests if r['status']=='ok']
    seconds=sum(r['latency_s'] for r in good)
    output=sum(r['response'].get('eval_count',0) for r in good)
    truncated=sum(r['response'].get('done_reason')=='length' for r in good)
    return {'docs_done':done,'docs_expected':total,'requests':len(requests),'requests_ok':len(good),
            'requests_failed':len(requests)-len(good),'phases':dict(Counter(r['phase'] for r in requests)),
            'output_tokens':output,'request_wall_s':seconds,'length_truncated':truncated,
            'truncation_fraction':truncated/len(good) if good else None,
            'output_tokens_per_request_second':output/seconds if seconds else None,
            'remaining_pilot_model_seconds_extrapolated':seconds/done*(total-done) if done else None,
            'full_pool_model_seconds_extrapolated':seconds/done*11657 if done else None,
            'estimate_note':'preliminary extrapolation from measured documents; excludes future cold starts/embedding/storage and may be biased by document lengths'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--docs',type=Path,required=True)
    p.add_argument('--index',type=Path,required=True)
    p.add_argument('--run-dir',type=Path,required=True)
    p.add_argument('--max-new-docs',type=int,default=10)
    p.add_argument('--resume',action='store_true')
    p.add_argument('--verify',action='store_true')
    args=p.parse_args()
    if sys.version_info[:3]!=(3,13,5):
        p.error('Python 3.13.5 is required by the group')
    if not 1<=args.max_new_docs<=200:
        p.error('max-new-docs must be 1..200')
    args.index,args.run_dir=args.index.resolve(),args.run_dir.resolve()
    check_paths(args.index,args.run_dir,ROOT,args.resume or args.verify)
    source_blob=args.docs.read_bytes()
    docs=[json.loads(line) for line in source_blob.splitlines()]
    if len(docs)!=200 or len({d['doc_id'] for d in docs})!=200:
        p.error('Only the selected 200-document pilot is accepted')
    pilot_path=args.docs.with_name('pilot_manifest.json')
    pilot=json.loads(pilot_path.read_bytes())
    if pilot['docs_sha256']!=sha(source_blob) or pilot['corpus_id']!='2wiki-n2000-s13-4267adcf3ef6':
        raise ValueError('Pilot source identity mismatch')
    from measure_2wiki_pools import load_chunker
    chunker,_,chunker_hash=load_chunker(ROOT,'gpt-4o-mini')
    chunks={}
    for d in docs:
        if d['minirag_doc_id']!='doc-'+hashlib.md5(d['text'].encode()).hexdigest():
            raise ValueError('MiniRAG document ID mismatch')
        for c in chunker(d['text'],100,1200,'gpt-4o-mini'):
            cid='chunk-'+hashlib.md5(c['content'].encode()).hexdigest()
            if cid in chunks and chunks[cid]['full_doc_id']!=d['minirag_doc_id']:
                raise ValueError('Shared chunk ownership requires explicit handling')
            chunks[cid]={'full_doc_id':d['minirag_doc_id'],'doc_id':d['doc_id'],'content':c['content']}
    sources=list((ROOT/'minirag').rglob('*.py'))+[Path(__file__),Path(__file__).with_name('local_qwen.py')]
    identity={'docs_sha256':sha(source_blob),'corpus_id':pilot['corpus_id'],'model':MODEL,
              'model_digest':PINNED_MODEL_DIGEST,'options':OPTIONS,'index_max_tokens':4096,
              'embedding':'existing hf_embed all-MiniLM-L6-v2 CPU 384d','chunking':[1200,100,'gpt-4o-mini'],
              'chunker_hash':chunker_hash,'client_concurrency':1,
              'source_hashes':{str(s.relative_to(ROOT)):sha(s.read_bytes()) for s in sorted(sources)}}
    if args.resume or args.verify:
        manifest=json.loads((args.run_dir/'index_manifest.json').read_bytes())
        require_matching_identity(manifest,identity)
        require_clean_checkpoint(args.index,manifest)
    else:
        args.index.mkdir(parents=True)
        args.run_dir.mkdir(parents=True)
        manifest={'status':'planned','identity':identity,'config_hash':identity_hash(identity),
                  'created_at':now(),'completed_doc_ids':[],'committed_store_sha256':{},
                  'expected':{'docs':len(docs),'chunks':len(chunks),'nominal_requests':2*len(chunks)},
                  'purpose':'local_2wiki_pilot_not_full_corpus_or_QA_benchmark',
                  'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()}
        atomic_manifest(args.run_dir/'index_manifest.json',manifest)
    if args.verify:
        done=[d for d in docs if d['minirag_doc_id'] in manifest['completed_doc_ids']]
        checks,counts=verify(args.index,done,chunks)
        if not all(checks.values()):
            raise ValueError('Index verification failed')
        print(json.dumps({'verification':checks,'counts':counts}))
        return
    client=LocalQwen(args.run_dir,timeout=240)
    try:
        write_json(args.run_dir/'runtime.json',client.inspect())
        manifest['status']='running'
        atomic_manifest(args.run_dir/'index_manifest.json',manifest)
        done=asyncio.run(process(args,docs,chunks,manifest,client))
        checks,counts=verify(args.index,done,chunks)
        manifest.update({'status':'pilot_indexed' if len(done)==len(docs) else 'stage_complete',
                         'verification':checks,'counts':counts})
        if not all(checks.values()):
            raise ValueError('Index link verification failed')
        snapshot=args.run_dir/'checkpoints'/f'docs-{len(done):04d}'
        if snapshot.exists():
            raise ValueError('Checkpoint directory already exists; refusing overwrite')
        snapshot.mkdir(parents=True)
        for name in manifest['committed_store_sha256']:
            shutil.copy2(args.index/name,snapshot/name)
        if stores_hash(snapshot)!=manifest['committed_store_sha256']:
            raise ValueError('Checkpoint snapshot checksum mismatch')
        write_json(snapshot/'checkpoint_manifest.json',manifest)
        records=[json.loads(line) for line in (args.run_dir/'requests.jsonl').read_text(encoding='utf-8').splitlines()]
        manifest['metrics']=stats(records,len(done),len(docs))
        if manifest['metrics']['truncation_fraction'] and manifest['metrics']['truncation_fraction']>.10:
            manifest['next_action']='review_truncation_before_more_indexing'
        else:
            manifest['next_action']='review_stage_estimates_before_resume'
        atomic_manifest(args.run_dir/'index_manifest.json',manifest)
        append(args.run_dir/'events.jsonl',{'at':now(),'event':'stage_verified','docs_done':len(done),'checkpoint':str(snapshot)})
        print(json.dumps({'status':manifest['status'],'counts':counts,'metrics':manifest['metrics'],'verification':checks},ensure_ascii=False))
    except BaseException as exc:
        manifest['status']='partial'
        manifest['last_error_type']=type(exc).__name__
        atomic_manifest(args.run_dir/'index_manifest.json',manifest)
        append(args.run_dir/'events.jsonl',{'at':now(),'event':'failed','error_type':type(exc).__name__})
        raise
    finally:
        try:
            client.unload()
        except Exception:
            pass


if __name__=='__main__':
    main()
