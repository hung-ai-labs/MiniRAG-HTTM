"""Current C0/C1/C2/C3 only: offline verification on frozen study inputs."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import numpy as np

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(HERE))
from c_profiles import PROFILES,VERSION,REFERENCE_KEYS,DESCRIPTIONS,apply_profile
from path_common import read,append,dev_rows,gold_map,evidence,mcnemar_p,embedding,forbidden_llm,CACHE
from minirag import MiniRAG,QueryParam,operate as op


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def sha(text):return hashlib.sha256(text.encode()).hexdigest()


def restore(data,profile):
    if profile not in ('C1','C2','C3'):
        raise ValueError('C0 uses its immutable historical baseline contexts')
    if profile=='C3' and data.get('path_method')!='p0_relation_lift':
        raise ValueError('New C3 cannot reuse the retired P2 scores')
    entries={}
    for seed,r in data['entries'].items():
        score=float(r['Score']) if r['score_dtype']=='python_float' else np.dtype(r['score_dtype']).type(r['Score'])
        entries[seed]={'Score':score,'Path':list(r['Path'])}
        if profile!='C1':entries[seed]['PathChunkScores']=dict(r['PathChunkScores'] if profile=='C3' else r['P0'])
    return {name:[entries[s] for s in seeds] for name,seeds in data['groups'].items()}


async def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profiles',nargs='+',choices=PROFILES,default=list(PROFILES))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--limit',type=int,default=200)
    parser.add_argument('--live-limit',type=int,default=0,
        help='Also verify first N questions through the actual offline retrieval pipeline')
    args=parser.parse_args()
    if not 1<=args.limit<=200 or not 0<=args.live_limit<=args.limit:parser.error('Invalid dev/live limits')
    if len(set(args.profiles))!=len(args.profiles):parser.error('Duplicate profiles')
    fresh=ROOT/'logs/p0_paths/20261109_dev200'
    if 'C3' in args.profiles and not (fresh/'independent_replay_validation.json').exists():
        parser.error('C3 is the new P0 method. Complete eval_p0_paths.py and its replay validation first; old P2 results are not used.')
    if args.output.exists():parser.error('Choose a new output directory; prior reports are immutable')
    args.output.mkdir(parents=True)
    frozen=ROOT/'logs/path_calibration/20261109_dev200'
    proof=json.loads((frozen/'independent_replay_validation.json').read_text())
    old=json.loads((frozen/'manifest.json').read_text())
    assert proof['complete']
    assert all(digest(frozen/n)==h for n,h in proof['input_sha256'].items())
    assert all(digest(frozen/'source'/n)==h for n,h in old['sources_sha256'].items())
    index=ROOT/'LiHua-World-qwen-modal'
    assert all(digest(index/n)==h for n,h in old['index_sha256'].items())
    for p in (CACHE,ROOT/'logs/devset.csv',ROOT/'logs/diag_path2chunk.jsonl',ROOT/'baseline.yaml'):
        assert digest(p)==old['sources_sha256'][str(p.relative_to(ROOT))]
    rows=dev_rows()[:args.limit]
    inputs={r['question']:r for r in read(frozen/'inputs.jsonl')}
    reference={r['question']:r for r in read(frozen/'replay.jsonl')}
    contexts={(r['question'],r['variant']):r for r in read(frozen/'contexts.jsonl')}
    new_inputs=new_reference=new_contexts={}
    if 'C3' in args.profiles:
        new_proof=json.loads((fresh/'independent_replay_validation.json').read_text())
        new_plan=json.loads((fresh/'manifest.json').read_text())
        assert new_proof['complete'] and new_plan['profile_version']==VERSION
        assert all(digest(fresh/n)==h for n,h in new_proof['input_sha256'].items())
        assert new_plan['index_sha256']==old['index_sha256']
        new_inputs={r['question']:r for r in read(fresh/'inputs.jsonl')}
        new_reference={r['question']:r for r in read(fresh/'replay.jsonl')}
        new_contexts={(r['question'],r['variant']):r for r in read(fresh/'contexts.jsonl')}
    sources=[Path(__file__),HERE/'c_profiles.py',HERE/'path_common.py',ROOT/'minirag/operate.py',
        ROOT/'minirag/path_affinity.py',ROOT/'minirag/path_calibration.py',ROOT/'minirag/path_projection.py',
        ROOT/'minirag/p0_path_scoring.py',
        ROOT/'minirag/path_rerank.py',ROOT/'minirag/utils.py',ROOT/'baseline.yaml',CACHE,
        ROOT/'logs/devset.csv',ROOT/'logs/diag_path2chunk.jsonl']
    hashes={str(p.relative_to(ROOT)):digest(p) for p in sources}
    plan={'profile_version':VERSION,'profiles':args.profiles,'descriptions':{p:DESCRIPTIONS[p] for p in args.profiles},
        'reference_keys':{p:REFERENCE_KEYS[p] for p in args.profiles},'source_study':str(frozen),
        'source_study_sha256':digest(frozen/'manifest.json'),'sources_sha256':hashes,
        'index_sha256':old['index_sha256'],'questions':[r['Question'] for r in rows],
        'top_k':60,'local_k':3,'budget':4000,'fusion':'graph-only; no RRF','api_calls':0,
        'scope':'Current-name verification of existing offline results; not a new independent experiment'}
    if 'C3' in args.profiles:
        plan['C3_source_study']=str(fresh)
        plan['C3_source_manifest_sha256']=digest(fresh/'manifest.json')
        plan['C3_source_validation_sha256']=digest(fresh/'independent_replay_validation.json')
    (args.output/'manifest.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2))
    for p in sources:
        dest=args.output/'source'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    records={};saved_contexts={};rank_checks=0
    for row in rows:
        q=row['Question'];records[q]={}
        data=inputs[q]
        for profile in args.profiles:
            apply_profile(profile)
            key=REFERENCE_KEYS[profile]
            expected=(new_reference if profile=='C3' else reference)[q]['selections'][key]
            current_data=new_inputs[q] if profile=='C3' else data
            if profile=='C0':rank=expected['graph_top30']
            else:
                groups=restore(current_data,profile)
                assert [[e['Path'] for e in group] for group in groups.values()]==[
                    [current_data['entries'][s]['Path'] for s in seeds] for seeds in current_data['groups'].values()]
                rank=op.kwd2chunk(groups,current_data['vector_ids'],30)
                assert rank==expected['graph_top30'];rank_checks+=1
            ctx=(new_contexts if profile=='C3' else contexts)[(q,key)];saved_contexts[(q,profile)]=ctx
            records[q][profile]={'graph_ids':rank,'chunk_ids':list(ctx['chunk_ids'])}
            append(args.output/'contexts.jsonl',{'question':q,'variant':profile,'reference_key':key,
                'context':ctx['context'],'context_sha256':ctx['context_sha256'],'chunk_ids':ctx['chunk_ids']})
    live=[]
    if args.live_limit:
        with tempfile.TemporaryDirectory(prefix='current-c-profiles-') as directory:
            work=Path(directory)
            for n in old['index_sha256']:shutil.copy2(index/n,work/n)
            rag=MiniRAG(working_dir=directory,llm_model_func=forbidden_llm,llm_model_name='offline-frozen-parser',
                enable_llm_cache=False,embedding_func=embedding(),log_level='ERROR')
            for row in rows[:args.live_limit]:
                for profile in args.profiles:
                    apply_profile(profile)
                    log=work/'trace.jsonl';log.unlink(missing_ok=True)
                    os.environ.update(MINIRAG_KW_CACHE=str(CACHE),MINIRAG_KW_CACHE_ONLY='1',MINIRAG_CONTEXT_LOG=str(log))
                    q=row['Question'];ctx=await rag.aquery(q,QueryParam(mode='mini',top_k=60,only_need_context=True))
                    assert ctx==saved_contexts[(q,profile)]['context']
                    trace=read(log)[-1];assert trace['chunk_ids']==records[q][profile]['chunk_ids']
                    live.append({'question':q,'profile':profile,'context_match':True})
                    print(f'Current profile {profile}: {len(live)}/{args.live_limit*len(args.profiles)} live contexts exact',flush=True)
    gold=gold_map()
    metrics={p:{stage:evidence(rows,{q:{'chunk_ids':r[p][stage]} for q,r in records.items()},gold)
        for stage in ('graph_ids','chunk_ids')} for p in args.profiles}
    paired={}
    for a in args.profiles:
        paired[a]={}
        for b in args.profiles:
            if a==b:continue
            up=down=0
            for q,rec in records.items():
                if q not in gold:continue
                before=all(c in rec[b]['chunk_ids'] for c in gold[q]);after=all(c in rec[a]['chunk_ids'] for c in gold[q])
                up+=not before and after;down+=before and not after
            paired[a][b]={'up':up,'down':down,'p_exact':mcnemar_p(up,down)}
    assert all(digest(ROOT/n)==h for n,h in hashes.items())
    assert all(digest(index/n)==h for n,h in old['index_sha256'].items())
    result={'profile_version':VERSION,'questions':len(rows),'metrics':metrics,'paired':paired,
        'rank_checks':rank_checks,'live_context_checks':live,'hashes_unchanged':True,'api_calls':0,
        'accuracy_measured':False,'fusion':'graph-only; no RRF','scope':plan['scope']}
    (args.output/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    lines=['Current profiles only; offline evidence, not QA accuracy.','profile | evidence /207 | full evidence /180']
    for p in args.profiles:
        m=metrics[p]['chunk_ids'];n=m['questions'];g=m['gold_chunks']
        lines.append(f"{p} | {round(m['retention']*g/100)}/{g} | {round(m['full']*n/100)}/{n}")
    print('\n'.join(lines),flush=True);(args.output/'report.txt').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':asyncio.run(main())
