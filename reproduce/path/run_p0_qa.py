"""C0/C1/new C3 QA on verified existing contexts; never rerun retrieval."""
import argparse
import asyncio
from collections import Counter
import hashlib
import json
import logging
import os
from pathlib import Path
import random
import statistics
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(HERE));sys.path.insert(0,str(ROOT/'reproduce'))
logging.getLogger('dotenv.main').setLevel(logging.ERROR)
from path_common import read,append,dev_rows,mcnemar_p,CACHE
from c_profiles import VERSION,profile_env
from minirag import QueryParam
from minirag.prompt import PROMPTS
from Step_2_evaluate import JUDGE_PROMPT
from qa_common import FreeAPI,DailyQuotaExhausted,MODEL

ARMS=('C0','C1','C3')
LABELS=('accurate','error','neither')


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest() if text is not None else 'NONE'


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def prepare(output):
    study=ROOT/'logs/p0_paths/20261109_dev200'
    proof=json.loads((study/'independent_replay_validation.json').read_text())
    plan=json.loads((study/'manifest.json').read_text())
    assert proof['complete'] and plan['profile_version']==VERSION
    assert all(digest(study/n)==h for n,h in proof['input_sha256'].items())
    index=ROOT/'LiHua-World-qwen-modal'
    assert all(digest(index/n)==h for n,h in plan['index_sha256'].items())
    for p in (CACHE,ROOT/'logs/devset.csv',ROOT/'logs/diag_path2chunk.jsonl',ROOT/'baseline.yaml'):
        assert digest(p)==plan['sources_sha256'][str(p.relative_to(ROOT))]
    rows=dev_rows();assert len(rows)==200
    contexts={}
    for r in read(study/'contexts.jsonl'):
        if r['variant'] not in ARMS:continue
        key=(r['question'],r['variant']);assert key not in contexts
        assert sha(r['context'])==r['context_sha256']
        contexts[key]=r
    assert set(contexts)=={(r['Question'],a) for r in rows for a in ARMS}
    sources=[Path(__file__),HERE/'qa_common.py',HERE/'P0_QA_PROTOCOL.md',HERE/'c_profiles.py',
        HERE/'path_common.py',ROOT/'minirag/prompt.py',ROOT/'minirag/base.py',
        ROOT/'minirag/llm/gemini.py',ROOT/'reproduce/Step_2_evaluate.py']
    inputs={str(p.relative_to(ROOT)):digest(p) for p in sources}
    manifest={'profile_version':VERSION,'arms':ARMS,'profiles':{a:profile_env(a) for a in ARMS},
        'scope':'Exploratory dev QA; frozen Qwen graph/parser and Gemini generation; not final SLM benchmark',
        'questions':[r['Question'] for r in rows],'generator':MODEL,'judge':MODEL,
        'generation_rounds':1,'judge_repeats':3,'max_tokens_generation':1024,'max_tokens_judge':16,
        'response_type':QueryParam().response_type,'sampling':'provider default',
        'system_template_sha256':sha(PROMPTS['rag_response']),'judge_prompt_sha256':sha(JUDGE_PROMPT),
        'sources_sha256':inputs,'index_sha256':plan['index_sha256'],
        'source_study_sha256':digest(study/'manifest.json'),
        'source_proof_sha256':digest(study/'independent_replay_validation.json'),
        'source_contexts_sha256':digest(study/'contexts.jsonl'),'new_retrieval_runs':0,
        'primary_comparisons':['C3 vs C0','C3 vs C1'],'prior_answers_reused':False,
        'endpoint':'public Gemini free tier only; original limiter',
        'reuse':'only identical question/context/round or question/prediction/judge pass'}
    manifest=json.loads(json.dumps(manifest))
    target=output/'manifest.json'
    if target.exists():
        if json.loads(target.read_text())!=manifest:raise ValueError('Manifest changed; use a new output')
    else:target.write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    for p in sources:
        dest=output/'source'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists():assert digest(dest)==digest(p)
        else:dest.write_bytes(p.read_bytes())
    saved=output/'contexts.jsonl'
    records=[contexts[(r['Question'],a)] for r in rows for a in ARMS]
    if saved.exists():assert read(saved)==records
    else:
        for r in records:append(saved,r)
    return rows,contexts,manifest


def summarize(output,rows):
    answers=read(output/'answers.jsonl');judges=read(output/'judgments.jsonl')
    keys=[(r['question'],r['variant'],r['judge_pass']) for r in judges]
    if len(set(keys))!=len(keys):raise ValueError('Duplicate judge checkpoint keys')
    labels=dict(zip(keys,(r['verdict'] for r in judges)))
    result={'status':'partial','planned_questions':len(rows),'answers':len(answers),
        'judgments':len(judges),'generation_rounds':1,'judge_repeats':3,'passes':{},
        'configuration_gain_confirmed':False,'new_retrieval_runs':0}
    def rates(qs,verdict):
        return {a:{l:100*sum(verdict(q,a)==l for q in qs)/len(qs) for l in LABELS} for a in ARMS}
    def paired(qs,verdict):
        out={}
        for control in ('C0','C1'):
            b=sum(verdict(q,control)!='accurate' and verdict(q,'C3')=='accurate' for q in qs)
            c=sum(verdict(q,control)=='accurate' and verdict(q,'C3')!='accurate' for q in qs)
            out[control]={'n':len(qs),'up':b,'down':c,'net':b-c,'p_exact':mcnemar_p(b,c)}
        previous=0
        for i,control in enumerate(sorted(out,key=lambda c:out[c]['p_exact'])):
            previous=min(1,max(previous,out[control]['p_exact']*(2-i)))
            out[control]['p_holm']=previous
        return out
    for j in (1,2,3):
        qs=[r['Question'] for r in rows if all((r['Question'],a,j) in labels for a in ARMS)]
        if qs:
            verdict=lambda q,a:labels[(q,a,j)]
            result['passes'][str(j)]={'paired_questions':len(qs),'rates':rates(qs,verdict),'paired':paired(qs,verdict)}
    expected=len(rows)*len(ARMS)*3
    if len(labels)==expected:
        result['status']='complete'
        majority={}
        for row in rows:
            q=row['Question']
            for a in ARMS:
                votes=Counter(labels[(q,a,j)] for j in (1,2,3));label,count=votes.most_common(1)[0]
                majority[(q,a)]=label if count>=2 else 'neither'
        result['rates_mean_judge_sd']={a:{l:{
            'mean':statistics.mean(result['passes'][str(j)]['rates'][a][l] for j in (1,2,3)),
            'sd_judge':statistics.stdev(result['passes'][str(j)]['rates'][a][l] for j in (1,2,3))}
            for l in LABELS} for a in ARMS}
        result['majority_paired']={};result['majority_rates']={}
        for group in ('All','Single','Multi','Null'):
            qs=[r['Question'] for r in rows if group=='All' or r['Type']==group]
            if not qs:continue
            verdict=lambda q,a:majority[(q,a)]
            result['majority_paired'][group]=paired(qs,verdict)
            result['majority_rates'][group]=rates(qs,verdict)
    name='accuracy_report.json' if result['status']=='complete' else 'partial_accuracy_report.json'
    (output/name).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result


async def run(output,rows,contexts):
    api=FreeAPI(output)
    answers={(r['question'],r['variant']):r for r in read(output/'answers.jsonl')}
    judges={(r['question'],r['variant'],r['judge_pass']):r for r in read(output/'judgments.jsonl')}
    reuse={(r['question'],r['context_sha256']):r['prediction'] for r in answers.values()}
    judge_reuse={(r['question'],r['prediction_sha256'],r['judge_pass']):r['verdict'] for r in judges.values()}
    for (q,a),record in answers.items():
        assert record['context_sha256']==contexts[(q,a)]['context_sha256']
    async def judge(row,a,j):
        q=row['Question'];key=(q,a,j)
        if key in judges:return
        h=sha(answers[(q,a)]['prediction']);cached=(q,h,j) in judge_reuse
        if cached:label=judge_reuse[(q,h,j)]
        else:label=(await api.call(JUDGE_PROMPT.format(question=q,gold=row['Gold Answer'],pred=answers[(q,a)]['prediction']),role='judge')).strip().lower()
        if label not in LABELS:raise RuntimeError('Invalid judge label; progress retained without invented verdict')
        rec={'question':q,'variant':a,'type':row['Type'],'generation_round':1,'judge_pass':j,
             'verdict':label,'prediction_sha256':h,'reused_identical_prediction':cached}
        append(output/'judgments.jsonl',rec);judges[key]=rec;judge_reuse[(q,h,j)]=label
    order=list(rows);random.Random(1308).shuffle(order)
    for i,row in enumerate(order):
        q=row['Question'];rotation=i%3;arms=ARMS[rotation:]+ARMS[:rotation]
        for a in arms:
            if (q,a) in answers:continue
            ctx=contexts[(q,a)];key=(q,ctx['context_sha256']);cached=key in reuse
            if cached:prediction=reuse[key]
            elif ctx['context'] is None:prediction=PROMPTS['fail_response']
            else:
                system=PROMPTS['rag_response'].format(context_data=ctx['context'],response_type=QueryParam().response_type)
                prediction=await api.call(q,system=system)
            prediction=prediction.replace('\n','').replace('\r','')
            if not prediction or prediction.strip()=='Error':raise RuntimeError('Invalid generation; not scored')
            rec={'question':q,'gold':row['Gold Answer'],'type':row['Type'],'variant':a,
                 'generation_round':1,'prediction':prediction,'context_sha256':ctx['context_sha256'],
                 'reused_identical_context':cached}
            append(output/'answers.jsonl',rec);answers[(q,a)]=rec;reuse[key]=prediction
        shuffled=list(arms);random.Random(2308+i).shuffle(shuffled)
        for a in shuffled:await judge(row,a,1)
        summarize(output,rows)
        print(f'QA {i+1}/{len(rows)} paired questions; answers={len(answers)} judges={len(judges)}',flush=True)
    for j in (2,3):
        shuffled=list(rows);random.Random(2408+j).shuffle(shuffled)
        for i,row in enumerate(shuffled):
            arms=list(ARMS);random.Random(1700+j*100+i).shuffle(arms)
            for a in arms:await judge(row,a,j)
            if (i+1)%5==0:
                summarize(output,rows);print(f'judge pass {j}: {i+1}/{len(rows)} paired questions',flush=True)


async def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--stage',choices=('prepare','run','report'),default='run')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    rows,contexts,manifest=prepare(args.output)
    if args.stage=='prepare':print('Prepared 600 verified existing contexts; retrieval not run');return
    try:
        if args.stage=='run':await run(args.output,rows,contexts)
        result=summarize(args.output,rows)
        (args.output/'status.json').write_text(json.dumps({'state':result['status']},indent=2))
        print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
    except Exception as exc:
        result=summarize(args.output,rows)
        state='daily_quota_exhausted' if isinstance(exc,DailyQuotaExhausted) else 'incomplete_error'
        status={'state':state,'error_type':type(exc).__name__,'answers':result['answers'],'judgments':result['judgments']}
        (args.output/'status.json').write_text(json.dumps(status,indent=2));print(json.dumps(status),flush=True)
        raise SystemExit(3 if isinstance(exc,DailyQuotaExhausted) else 1) from None
    finally:
        assert all(digest(ROOT/n)==h for n,h in manifest['sources_sha256'].items())
        assert all(digest(ROOT/'LiHua-World-qwen-modal'/n)==h for n,h in manifest['index_sha256'].items())


if __name__=='__main__':asyncio.run(main())
