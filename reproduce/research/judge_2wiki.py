"""ID-based 2Wiki judging with aliases; plan only unless --execute is supplied.

Accepts phased QA answers.jsonl (not the legacy CSV without query IDs).
Uses the existing Gemini key pool/quotas and saves raw per-attempt trace.
"""
import argparse
import ast
import asyncio
import csv
import json
import os
from pathlib import Path
import random
import re
import sys

import qa_run
import metrics
from two_wiki_acceleration.common import JUDGE_MODEL

RUBRIC_VERSION = '2wiki-upstream-aliases-v2'


def upstream_prompt():
    """Read the registered prompt verbatim without importing the legacy runner."""
    path = qa_run.ROOT / 'reproduce/Step_2_evaluate.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'JUDGE_PROMPT' for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError('Registered JUDGE_PROMPT missing from Step_2_evaluate.py')


# Preserve the project's definitions verbatim. The appendix only supplies
# 2Wiki alternate names; it adds no criterion about incidental background facts.
RUBRIC = upstream_prompt() + '''
accepted_aliases for the gold answer (JSON): {accepted_aliases}
These are alternative names for the gold answer; semantically equivalent wording counts as usual.
'''


def parse_label(raw):
    label = re.sub(r'^[\s\W_]+|[\s\W_]+$', '', raw.lower())
    return label if label in metrics.LABELS else None


def records(path):
    result = {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        r = json.loads(line)
        qid = r['query_id']
        if not qid or qid in result:
            raise ValueError('Missing or duplicate query_id')
        result[qid] = r
    return result


def inputs(questions, gold_path, answers_path):
    rows = metrics.read_csv(questions)
    ids = [r['query_id'] for r in rows]
    gold, answers = records(gold_path), records(answers_path)
    if not ids or len(set(ids)) != len(ids) or set(ids) != set(gold) or set(ids) != set(answers):
        raise ValueError('Questions, gold and answers must cover exactly the same unique IDs')
    for r in rows:
        g, a = gold[r['query_id']], answers[r['query_id']]
        if r['Gold Answer'] != g['answer'] or not isinstance(a.get('answer'), str):
            raise ValueError('Gold mismatch or invalid generated answer')
        if not isinstance(g.get('aliases'), list) or any(not isinstance(x, str) for x in g['aliases']):
            raise ValueError('Gold aliases must be strings')
    return rows, gold, answers


async def verdict(call, prompt):
    attempts = []
    api_failures = parse_failures = 0
    while api_failures < 6 and parse_failures < 3:
        try:
            raw = await call(prompt)
        except Exception as exc:
            api_failures += 1
            attempts.append({'ok': False, 'error_type': type(exc).__name__})
            if api_failures < 6:
                await asyncio.sleep(min(2 ** api_failures, 30))
            continue
        label = parse_label(raw)
        attempts.append({'ok': True, 'raw': raw, 'label': label})
        if label:
            return {'status': 'ok', 'label': label, 'attempts': attempts}
        parse_failures += 1
    return {'status': 'parse_failed' if parse_failures == 3 else 'judge_failed',
            'label': None, 'attempts': attempts}


async def run(a, rows, gold, answers, call):
    log = a.out / 'judge.jsonl'
    latest = {}
    if log.exists():
        blob = log.read_bytes()
        if blob and not blob.endswith(b'\n'):
            raise ValueError('Torn judge checkpoint; preserve it and recover into a new run')
        for line in blob.splitlines():
            r = json.loads(line)
            if r['query_id'] not in gold or r['pass'] not in (1, 2, 3):
                raise ValueError('Unexpected checkpoint ID/pass')
            latest[r['query_id'], r['pass']] = r
    sem = asyncio.Semaphore(a.concurrency)
    with log.open('a', encoding='utf-8') as f:
        async def one(row, turn):
            qid = row['query_id']
            if latest.get((qid, turn), {}).get('status') == 'ok':
                return
            async with sem:
                import llm_trace
                with llm_trace.request_context(query_id=qid, phase=f'judge_pass{turn}'):
                    prompt = RUBRIC.format(question=row['Question'], gold=gold[qid]['answer'],
                                           pred=answers[qid]['answer'],
                                           accepted_aliases=json.dumps(gold[qid]['aliases'], ensure_ascii=False))
                    result = await verdict(call, prompt)
            record = {'query_id': qid, 'pass': turn, 'type': row.get('Type', '?'), **result}
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
            latest[qid, turn] = record
        for turn in (1, 2, 3):
            shuffled = list(rows)
            random.Random(13 + turn).shuffle(shuffled)
            await asyncio.gather(*(one(r, turn) for r in shuffled))
    per_question = []
    for r in rows:
        labels = [latest[r['query_id'], t]['label'] or latest[r['query_id'], t]['status'] for t in (1, 2, 3)]
        per_question.append({'query_id': r['query_id'], 'Type': r.get('Type', '?'),
                             **dict(zip(['pass1', 'pass2', 'pass3'], labels)), 'majority': metrics.vote(labels)})
    with (a.out / 'per_question.csv').open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(per_question[0]), lineterminator='\n')
        w.writeheader()
        w.writerows(per_question)
    complete = all(r['majority'] != 'incomplete' for r in per_question)
    if complete:
        qa_run.atomic_json(a.out / 'summary.json', metrics.groups_summary(per_question, ['pass1', 'pass2', 'pass3']))
    print(json.dumps({'complete': complete, 'n_questions': len(rows), 'out': str(a.out)}))
    return 0 if complete else 1


def job_identity(a):
    return {'schema': 2, 'judge_model': a.model, 'passes': 3, 'shuffle_seed_base': 13,
            'rubric_version': RUBRIC_VERSION,
            'rubric_sha256': qa_run.digest(RUBRIC), 'source_sha256': qa_run.file_hash(Path(__file__)),
            'inputs': {k: qa_run.file_hash(getattr(a, k)) for k in ('questions', 'gold', 'answers')}}


def provider():
    """Set up one persistent free-tier pool; no requests until call() is awaited."""
    sys.path.insert(0, str(qa_run.ROOT))
    from dotenv import load_dotenv
    load_dotenv(qa_run.ROOT / '.env')
    if os.environ.get('GEMINI_API_BASE') or os.environ.get('MINIRAG_SLM_SEED'):
        raise ValueError('Use a fresh judge shell without GEMINI_API_BASE or MINIRAG_SLM_SEED')
    if int(os.environ.get('GEMINI_TPM', '3000')) > 3000:
        raise ValueError('Judge must retain the Gemini free-tier limiter, TPM <= 3000')
    from minirag.llm import gemini
    gemini._resolve_api_keys(None)
    import llm_trace
    llm_trace.install()
    async def call(model, prompt):
        return await gemini.gemini_complete_if_cache.__wrapped__(
            model, prompt, base_url=gemini.GEMINI_BASE_URL, max_tokens=512)
    return call


async def execute_job(a, call):
    """One job in a persistent consumer; each job has its own trace and lock."""
    rows, gold, answers = inputs(a.questions, a.gold, a.answers)
    identity = job_identity(a)
    a.out.mkdir(parents=True, exist_ok=True)
    with qa_run.run_lock(a.out):
        manifest = a.out / 'manifest.json'
        if manifest.exists():
            if json.loads(manifest.read_text(encoding='utf-8')) != identity:
                raise ValueError('Resume identity changed')
        elif any(p.name != '.qa.lock' for p in a.out.iterdir()):
            raise ValueError('Existing judge output has no valid manifest')
        else:
            qa_run.atomic_json(manifest, identity)
        import llm_trace
        with (a.out / 'requests.jsonl').open('a', encoding='utf-8') as trace:
            def sink(r):
                trace.write(json.dumps(r | {'at': qa_run.utc_now()}, ensure_ascii=False) + '\n')
                trace.flush()
                os.fsync(trace.fileno())
            async def request(prompt):
                return await call(a.model, prompt)
            with llm_trace.trace(sink):
                return await run(a, rows, gold, answers, request)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--questions', type=Path, required=True)
    p.add_argument('--gold', type=Path, required=True)
    p.add_argument('--answers', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--model', default=JUDGE_MODEL, choices=(JUDGE_MODEL,),
                   help='Frozen 2Wiki judge ID selected by the user; latest aliases are not accepted')
    p.add_argument('--concurrency', type=qa_run.positive, default=4)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    if not a.model.startswith('gemini-'):
        p.error('Judge must use an explicit Gemini model ID')
    rows, gold, answers = inputs(a.questions, a.gold, a.answers)
    identity = job_identity(a)
    if not a.execute:
        print(json.dumps({'execute': False, 'n_questions': len(rows), 'nominal_judgments': 3 * len(rows), **identity}))
        return 0
    if a.out.exists() and not a.resume:
        p.error('Output exists; use --resume or a new directory')
    if a.resume and not (a.out / 'manifest.json').is_file():
        p.error('Resume requires a valid manifest')
    return asyncio.run(execute_job(a, provider()))


if __name__ == '__main__':
    sys.exit(main())
