"""Operational queue for unchanged Phase 3 judge: unseen work before retries.

Uses the frozen judge_run prompt/parser/options and its full original rows.
No valid verdict is repeated. Exhausted cohorts remain explicitly incomplete;
the final analysis gate still requires every registered verdict.
"""
import argparse
import asyncio
import collections
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from reproduce.research.mhr_phase3.common import load_repo,now,read_json,run_lock,sha,source_hashes
from reproduce.research.mhr_phase3.judge_worker import load_judge
from reproduce.research.recover_mhr_phase3_windows import write_status


def journal_state(path, query_ids, passes):
    expected={(q,p) for q in query_ids for p in range(1,passes+1)}
    latest={};cycles=collections.Counter()
    if Path(path).exists():
        lines=Path(path).read_text(encoding='utf-8').splitlines()
        for i,line in enumerate(lines):
            if not line.strip():continue
            try:r=json.loads(line)
            except json.JSONDecodeError:
                if i==len(lines)-1:break
                raise ValueError('Corrupt middle of judge journal') from None
            key=(r['query_id'],r['pass'])
            if key not in expected:raise ValueError('Unexpected verdict ID/pass')
            cycles[key]+=1;latest[key]=r
    valid=sum(r.get('status')=='ok' for r in latest.values())
    pending=[{'query_id':q,'pass':p,'status':latest.get((q,p),{}).get('status','unattempted'),
              'recorded_cycles':cycles[q,p]} for q,p in sorted(expected) if latest.get((q,p),{}).get('status')!='ok']
    return {'valid':valid,'target':len(expected),'unseen':len(expected-set(latest)),
            'cycles_used':max(cycles.values(),default=0),'pending':pending}


def choose(cohorts, limit):
    runnable=[c for c in cohorts if c['state']['pending'] and c['state']['cycles_used']<limit]
    # This uses only technical coverage, never accurate/error/neither outcomes.
    return min(runnable,key=lambda c:(not bool(c['state']['unseen']),c['state']['cycles_used'],
                                      c['seed'],c['config'])) if runnable else None


async def consume(args):
    load_repo(args.repo)
    from dotenv import load_dotenv
    load_dotenv(args.repo/'.env')
    from minirag.llm.gemini import gemini_complete_if_cache
    from minirag.prompt import PROMPTS
    from Step_2_evaluate import JUDGE_PROMPT
    import llm_trace
    llm_trace.install()
    judge=load_judge(args.repo);judge.require_gemini_endpoint()
    manifest=read_json(args.run_root/'RUN_MANIFEST.json')
    questions=args.run_root/'test_internal.csv'
    if sha(questions)!=read_json(args.run_root/'TEST_INPUT.json')['sha256']:
        raise ValueError('Frozen test input changed')
    cache={};events=args.run_root/'fair_judge_scheduler';events.mkdir(exist_ok=True)
    write_status(events/'SCHEDULER_IDENTITY.json',{'at':now(),'script_sha256':sha(__file__),
        'original_manifest_sha256':sha(args.run_root/'RUN_MANIFEST.json'),
        'policy':'Unseen ready cohorts precede format retries. Original full rows, shuffle and labels unchanged.',
        'retry_budget':'Original outer_resume_limit; conservatively count maximum records per ID/pass across prior processes.'})
    async def complete(prompt):
        return await gemini_complete_if_cache(manifest['judge_model'],prompt)
    while True:
        if source_hashes(args.repo)!=manifest['source_hashes']:
            raise ValueError('Frozen repository source changed')
        cohorts=[]
        for seed in manifest['seeds']:
            ready_path=args.run_root/f'READY_s{seed}.json'
            if not ready_path.exists():continue
            ready=read_json(ready_path)
            if ready['questions_sha256']!=sha(questions):raise ValueError('Ready question hash mismatch')
            for config in manifest['configs']:
                folder=args.run_root/'qa'/f's{seed}'/f'{config}_s{seed}'
                answers=folder/'answers.csv'
                if ready['answers'][config]!=sha(answers):raise ValueError('Ready answer hash mismatch')
                key=(seed,config)
                if key not in cache:
                    argv=['--questions',str(questions),'--answers',str(answers),'--run-dir',str(folder/'judge'),
                          '--judgemodel',manifest['judge_model'],'--passes',str(manifest['judge_passes']),
                          '--concurrency',str(manifest['judge_concurrency']),'--invalid-tries',str(manifest['invalid_tries'])]
                    parsed=judge.parser().parse_args(argv);parsed.prompt=JUDGE_PROMPT
                    rows=judge.load_rows(questions,answers,parsed.column,PROMPTS['fail_response'])
                    if len(rows)!=manifest['test_queries']:raise ValueError('Wrong cohort size')
                    cache[key]={'seed':seed,'config':config,'args':parsed,'rows':rows,'folder':folder}
                c=cache[key]
                c['state']=journal_state(folder/'judge/judge.jsonl',[r['query_id'] for r in c['rows']],manifest['judge_passes'])
                cohorts.append(c)
        total=sum(c['state']['valid'] for c in cohorts)
        pending=[{'seed':c['seed'],'config':c['config'],**p} for c in cohorts for p in c['state']['pending']]
        pending_file=args.run_root/'PENDING_JUDGE_SLOTS.json'
        write_status(pending_file,{'at':now(),'valid_votes':total,'target_votes':manifest['valid_judge_votes'],
                     'ready_cohorts':len(cohorts),'pending_ready_slots':pending,'labels_forced':False})
        all_ready=len(cohorts)==len(manifest['seeds'])*len(manifest['configs'])
        if all_ready and total==manifest['valid_judge_votes']:
            write_status(args.run_root/'JUDGE_STATUS.json',{'status':'completed','at':now(),
                         'valid_votes':total,'analysis_pending':True})
            return 0
        c=choose(cohorts,manifest['outer_resume_limit'])
        if c is None:
            if all_ready:
                write_status(args.run_root/'JUDGE_STATUS.json',{'status':'needs_adjudication','at':now(),
                    'valid_votes':total,'target_votes':manifest['valid_judge_votes'],'pending_file':str(pending_file),
                    'note':'Original technical retry budgets exhausted. No label or denominator changed; final audit remains blocked.'})
                return 2
            write_status(args.run_root/'JUDGE_STATUS.json',{'status':'waiting_for_ready','at':now(),
                         'valid_votes':total,'pending_file':str(pending_file)})
            if (args.run_root/'QA_FAILED.json').exists():raise RuntimeError('QA producer failed before all seeds ready')
            await asyncio.sleep(5)
            continue
        parsed=c['args'];parsed.resume=(parsed.run_dir/'manifest.json').exists()
        write_status(args.run_root/'JUDGE_STATUS.json',{'status':'running','at':now(),
            'seed':c['seed'],'config':c['config'],'resume_cycle':c['state']['cycles_used'],
            'prior_valid_votes':total,'queue_policy':'unseen_before_retries','pending_file':str(pending_file)})
        event={'at':now(),'seed':c['seed'],'config':c['config'],'cycles_used_before':c['state']['cycles_used'],
               'valid_before':c['state']['valid'],'unseen_before':c['state']['unseen']}
        # Exactly the original runner, including three passes, seed13 shuffle,
        # invalid/API attempts, trace capture, fsync journal and summary contract.
        code=await judge.run(parsed,c['rows'],complete)
        event.update(finished_at=now(),return_code=code)
        with (events/'events.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps(event,ensure_ascii=False)+'\n');f.flush()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,required=True);p.add_argument('--run-root',type=Path,required=True)
    args=p.parse_args()
    with run_lock(args.run_root/'judge_consumer'):
        return asyncio.run(consume(args))


if __name__=='__main__':raise SystemExit(main())
