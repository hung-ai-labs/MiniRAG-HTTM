"""New P0-based path scoring vs C0/C1, with all original MiniRAG flows."""
import argparse
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(HERE))
from c_profiles import apply_profile,VERSION
from path_common import read,append,dev_rows,gold_map,evidence,mcnemar_p,embedding,forbidden_llm,CACHE
from minirag import MiniRAG,QueryParam,operate as op,path_rerank
from minirag import p0_path_scoring as method
from minirag.path_affinity import condition_evidence

ARMS=('C1','C3','no_relation','no_background','affinity_only','no_score_flow')


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def sha(v):return hashlib.sha256(v.encode()).hexdigest()


def aggregate_config(arm):
    apply_profile('C3')
    if arm in ('C1','no_score_flow'):os.environ['MINIRAG_PATH_SCORE_FLOW']='0'


def report(args,rows,records):
    gold=gold_map()
    names=('C0','C1','C2','C3','no_relation','no_background','affinity_only','no_score_flow')
    metrics={a:{stage:evidence(rows,{r['question']:{'chunk_ids':r['selections'][a][stage]} for r in records},gold)
        for stage in ('selected_pool','graph_top30','graph_a1','rrf_a1')
        if all(stage in r['selections'][a] for r in records)} for a in names}
    paired={}
    for control in names:
        if control=='C3':continue
        paired[control]={}
        for stage in ('graph_top30','graph_a1','rrf_a1'):
            b=c=0
            for r in records:
                g=gold.get(r['question'])
                if not g:continue
                before=all(cid in r['selections'][control][stage] for cid in g)
                after=all(cid in r['selections']['C3'][stage] for cid in g)
                b+=not before and after;c+=before and not after
            paired[control][stage]={'up':b,'down':c,'net':b-c,'p_exact':mcnemar_p(b,c)}
    prev=0
    for i,c in enumerate(sorted(('C0','C1'),key=lambda c:paired[c]['graph_a1']['p_exact'])):
        p=paired[c]['graph_a1'];p['p_holm']=prev=min(1,max(prev,p['p_exact']*(2-i)))
    by_type={a:{t:evidence([row for row in rows if row['Type']==t],
        {r['question']:{'chunk_ids':r['selections'][a]['graph_a1']} for r in records},gold)
        for t in ('Single','Multi')} for a in names}
    changes={a:{c:{'all':sum(r['context_hashes'][a]!=r['context_hashes'][c] for r in records),
        'Null':sum(r['type']=='Null' and r['context_hashes'][a]!=r['context_hashes'][c] for r in records)}
        for c in ('C0','C1')} for a in ARMS if a!='C1'}
    import statistics
    result={'scope':'exploratory offline P0 redesign; not QA accuracy','profile_version':VERSION,
        'questions':len(rows),'metrics':metrics,'C3_vs':paired,'by_type':by_type,'context_changes':changes,
        'candidate_lists_fixed_to_C1':True,'C1_frozen_context_checks':len(records),'native_C3_context_checks':len(records),
        'old_P2_calls':0,'hashes_unchanged':True,'api_calls':0,'accuracy_measured':False,
        'fallback_seeds':sum(r['metadata']['fallback_seeds'] for r in records),
        'zero_relation_paths':sum(r['metadata']['zero_relation_paths'] for r in records),
        'original_paths':sum(r['metadata']['original_paths'] for r in records),
        'retrieval_ms_median':statistics.median(r['retrieval_ms'] for r in records),
        'scoring_ms_median':statistics.median(r['metadata']['total_scoring_ms'] for r in records),
        'independent_context_checks':sum(r['independent_checks'] for r in records)}
    (args.output/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    lines=['P0 relation-conditioned scoring; fixed C1 candidates; evidence only, not accuracy.',
           'arm | top30 retention | A1 retention | full evidence | RRF simulated']
    for a in names:
        m=metrics[a];lines.append(f"{a} | {m['graph_top30']['retention']:.2f} | {m['graph_a1']['retention']:.2f} | {m['graph_a1']['full']:.2f} | {m['rrf_a1']['retention']:.2f}")
    (args.output/'report.txt').write_text('\n'.join(lines)+'\n');print('\n'.join(lines),flush=True)


async def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--limit',type=int,default=200)
    args=parser.parse_args()
    if not 1<=args.limit<=200:parser.error('Use frozen dev 1..200')
    if args.output.exists():parser.error('Use new output; never overwrite existing experiments')
    args.output.mkdir(parents=True)
    old=ROOT/'logs/path_calibration/20261109_dev200';prior=json.loads((old/'manifest.json').read_text())
    proof=json.loads((old/'independent_replay_validation.json').read_text());assert proof['complete']
    assert all(digest(old/n)==h for n,h in proof['input_sha256'].items())
    assert all(digest(old/'source'/n)==h for n,h in prior['sources_sha256'].items())
    index=ROOT/'LiHua-World-qwen-modal'
    assert all(digest(index/n)==h for n,h in prior['index_sha256'].items())
    for p in (CACHE,ROOT/'logs/devset.csv',ROOT/'logs/diag_path2chunk.jsonl',ROOT/'baseline.yaml'):
        assert digest(p)==prior['sources_sha256'][str(p.relative_to(ROOT))]
    rows=dev_rows()[:args.limit]
    frozen_contexts={(r['question'],r['variant']):r for r in read(old/'contexts.jsonl')}
    frozen_records={r['question']:r for r in read(old/'replay.jsonl')}
    frozen_inputs={r['question']:r for r in read(old/'inputs.jsonl')}
    sources=[Path(__file__),HERE/'P0_RELATION_LIFT_PROTOCOL.md',HERE/'c_profiles.py',HERE/'path_common.py',
        ROOT/'minirag/p0_path_scoring.py',ROOT/'minirag/path_projection.py',ROOT/'minirag/path_affinity.py',
        ROOT/'minirag/operate.py',ROOT/'minirag/utils.py',ROOT/'minirag/kg/nano_vector_db_impl.py',
        ROOT/'minirag/kg/networkx_impl.py',ROOT/'minirag/minirag.py',ROOT/'minirag/base.py',
        ROOT/'tests/test_p0_path_scoring.py',ROOT/'tests/test_c_profiles.py',
        ROOT/'baseline.yaml',CACHE,ROOT/'logs/devset.csv',ROOT/'logs/diag_path2chunk.jsonl',
        old/'manifest.json',old/'inputs.jsonl',old/'contexts.jsonl',old/'replay.jsonl']
    hashes={str(p.relative_to(ROOT)):digest(p) for p in sources}
    plan={'profile_version':VERSION,'method':'p0_relation_lift','source_study':str(old),
        'questions':[r['Question'] for r in rows],'sources_sha256':hashes,'index_sha256':prior['index_sha256'],
        'arms':('C0','C2',*ARMS),'primary':'C3 vs C0,C1; Holm-adjusted','top_k':60,'local_k':3,'budget':4000,
        'fusion':'graph-only; no RRF','api_calls':0,'fixed_candidates':'C1 ordered per-seed lists',
        'embedding':'all-MiniLM-L6-v2','embedding_revision':'1110a243fdf4706b3f48f1d95db1a4f5529b4d41'}
    (args.output/'manifest.json').write_text(json.dumps(plan,indent=2))
    for p in sources:
        dest=args.output/'source'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    chunks=json.loads((index/'kv_store_text_chunks.json').read_text())
    def cap(ids):
        units=[(c,chunks[c]['content']) for c in ids if c in chunks]
        return [c for c,_ in op.truncate_list_by_token_size(units,key=lambda x:x[1],max_token_size=4000)]
    def context_for(prefix,ids):
        csv=op.list_of_list_to_csv([['id','content']]+[[i,chunks[c]['content']] for i,c in enumerate(ids)])
        return prefix+'-----Sources-----\n```csv\n'+csv+'\n```\n'
    original_prepare=method.prepare_scoring;original_project=op.path2chunk;original_kwd=op.kwd2chunk
    records=[]
    os.environ.update(MINIRAG_KW_CACHE=str(CACHE),MINIRAG_KW_CACHE_ONLY='1')
    with tempfile.TemporaryDirectory(prefix='p0-path-redesign-') as directory:
        work=Path(directory)
        for n in prior['index_sha256']:shutil.copy2(index/n,work/n)
        rag=MiniRAG(working_dir=directory,llm_model_func=forbidden_llm,llm_model_name='offline-frozen-parser',
                    enable_llm_cache=False,embedding_func=embedding(),log_level='ERROR')
        with patch.object(path_rerank,'score_reasoning_paths_weighted',side_effect=AssertionError('Old P2 forbidden')):
            for i,row in enumerate(rows):
                q=row['Question'];saved={}
                async def prepare(*a,**kw):
                    bundle=await original_prepare(*a,**kw);saved['bundle']=bundle;return bundle
                async def project(*a,**kw):
                    out=await original_project(*a,**kw);saved['names']={id(v):s for s,v in out.items()};return out
                def kwd(groups,vectors,chunk_nums):
                    saved['groups']={k:[saved['names'][id(e)] for e in es] for k,es in groups.items()}
                    saved['vectors']=list(vectors);return original_kwd(groups,vectors,chunk_nums)
                apply_profile('C3');trace=work/'trace.jsonl';trace.unlink(missing_ok=True)
                os.environ['MINIRAG_CONTEXT_LOG']=str(trace)
                with patch.object(method,'prepare_scoring',prepare),patch.object(op,'path2chunk',project),patch.object(op,'kwd2chunk',kwd):
                    actual=await rag.aquery(q,QueryParam(mode='mini',top_k=60,only_need_context=True))
                t=read(trace)[-1];bundle=saved['bundle']
                assert t['path_projection']['base_scorer']=='P0' and t['path_score_mode']==''
                assert saved['vectors']==frozen_inputs[q]['vector_ids']
                reference=condition_evidence(bundle['prior'],bundle['affinities'],3)
                variants={'C1':copy.deepcopy(reference),'C3':method.rank_scoring(bundle,3)}
                variants.update({m:method.rank_scoring(bundle,3,m) for m in ('no_relation','no_background','affinity_only')})
                variants['no_score_flow']=copy.deepcopy(variants['C3'])
                paths={s:e['Path'] for s,e in reference.items()}
                for e in variants.values():assert {s:r['Path'] for s,r in e.items()}==paths
                prefix=actual.split('-----Sources-----')[0]
                selections={};contexts={}
                for name,key in (('C0','C0'),('C2','P0_fixed_mean')):
                    selections[name]=copy.deepcopy(frozen_records[q]['selections'][key])
                    contexts[name]=frozen_contexts[(q,key)]['context'];assert contexts[name].split('-----Sources-----')[0]==prefix
                for arm in ARMS:
                    aggregate_config(arm);entries=copy.deepcopy(variants[arm])
                    if arm in ('C1','no_score_flow'):
                        for e in entries.values():e.pop('PathChunkScores')
                    groups={k:[entries[s] for s in names] for k,names in saved['groups'].items()}
                    rank=original_kwd(groups,saved['vectors'],30)
                    selections[arm]={'selected_pool':sorted({cid for e in entries.values() for cid in e['Path']}),
                        'graph_top30':rank,'graph_a1':cap(rank),'rrf_a1':cap(op._rrf_fuse(rank,saved['vectors']))}
                    contexts[arm]=context_for(prefix,selections[arm]['graph_a1'])
                    if arm=='C1':
                        assert contexts[arm]==frozen_contexts[(q,'C1_affinity')]['context']
                        assert rank==frozen_records[q]['selections']['C1_affinity']['graph_top30']
                    if arm=='C3':assert contexts[arm]==actual and rank==t['graph_ids']
                assert contexts['no_score_flow']==contexts['C1']
                serialized={s:{'Score':float(e['Score']),'score_dtype':str(getattr(e['Score'],'dtype','python_float')),
                    'Path':e['Path'],'PathChunkScores':e['PathChunkScores']} for s,e in variants['C3'].items()}
                append(args.output/'inputs.jsonl',{'question':q,'path_method':'p0_relation_lift',
                    'entries':serialized,'groups':saved['groups'],'vector_ids':saved['vectors']})
                for arm,ctx in contexts.items():append(args.output/'contexts.jsonl',{'question':q,'variant':arm,
                    'context':ctx,'context_sha256':sha(ctx),'chunk_ids':selections[arm]['graph_a1']})
                independent=0
                if i<2:
                    for name in ('C0','C1','C2'):
                        apply_profile(name);os.environ['MINIRAG_CONTEXT_LOG']=str(work/'independent.jsonl')
                        assert await rag.aquery(q,QueryParam(mode='mini',top_k=60,only_need_context=True))==contexts[name]
                        independent+=1
                record={'question':q,'type':row['Type'],'selections':selections,
                    'context_hashes':{a:sha(c) for a,c in contexts.items()},'metadata':bundle['metadata'],
                    'retrieval_ms':t['retrieval_ms'],'independent_checks':independent}
                records.append(record);append(args.output/'replay.jsonl',record)
                if (i+1)%10==0 or i+1==len(rows):print(f'P0 path redesign {i+1}/{len(rows)}; C1 exact, all original flows, P2 forbidden',flush=True)
    assert all(digest(ROOT/n)==h for n,h in hashes.items())
    assert all(digest(index/n)==h for n,h in prior['index_sha256'].items())
    report(args,rows,records)


if __name__=='__main__':asyncio.run(main())
