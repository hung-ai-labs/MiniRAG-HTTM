"""QA check of the evidence-set selector on dev200 (all 200 questions, Null included).

Arms (only the Sources block differs; Entities, prompt, 4,000-token budget unchanged):
  BASELINE      frozen C0 + source-time + A1@4000 context, byte for byte
  CE0F_SET      CE0+F scorer + budgeted set selection over native@45 (main method)
  CE0F_RERANK   CE0+F scorer, plain sort by p + A1@4000 (ablation: no set selection)
Selections come from offline_selections_dev200.json (cross-fitted scores, nested beta/tau).

Generation/judging reuse reproduce/oracle_headroom/run.py unchanged (Qwen2.5-3B, seed
13+id, 1024 tokens; Gemini flash-lite judge, Step_2 prompt, blind, 1 pass). The oracle
run's Qwen cache and judgments are copied in, so identical bodies reuse their answers.

    .venv/bin/python -m reproduce.evidence_set.qa build|generate|judge|report
"""
import argparse
import asyncio
import csv
import json
import shutil
from math import comb
from pathlib import Path

from reproduce.graph_ablation.study import ROOT, sha, write, lines, read
from reproduce.evidence_set.data import corpus, gold, full
from reproduce.evidence_set.pool import OUT as SET_OUT
from reproduce.oracle_headroom import run as runner
from minirag.utils import list_of_list_to_csv

OUT = SET_OUT / 'qa_dev200'
ORACLE = ROOT / 'review/oracle_headroom_20261111'
SRC = ROOT / 'review/learned_selector_lihua_20261111/contexts200.jsonl'
ARMS = ('BASELINE', 'CE0F_SET', 'CE0F_RERANK')
FROM = {'CE0F_SET': 'CE0+F_SET', 'CE0F_RERANK': 'CE0+F_RERANK'}
HEAD = '-----Sources-----\n```csv\n'


def with_sources(context, texts):
    start = context.index(HEAD) + len(HEAD)
    end = context.index('\n```', start)
    return context[:start] + list_of_list_to_csv([['id', 'content']] + [[i, t] for i, t in enumerate(texts)]) + context[end:]


def build():
    chunks, _, _ = corpus()
    sel = json.loads((SET_OUT / 'offline_selections_dev200.json').read_text())
    pools = {r['id']: r for r in lines(SET_OUT / 'pools_dev200.jsonl')}
    qa = {}
    with (ROOT / 'dataset/LiHua-World/qa/query_set.csv').open() as f:
        for r in csv.DictReader(f):
            qa.setdefault(r['Question'], r)
    base = sorted((r for r in lines(SRC) if r['arm'] == 'BASELINE'), key=lambda r: r['id'])
    assert len(base) == 200
    out = []
    for r in base:
        assert sha(r['context']) == r['context_sha256']
        assert pools[r['id']]['baseline_kept'] == r['chunk_ids'] == sel['BASELINE'][str(r['id'])]
        typ, sets, status = gold(r['question'])
        for arm in ARMS:
            ids = r['chunk_ids'] if arm == 'BASELINE' else sel[FROM[arm]][str(r['id'])]
            ctx = r['context'] if arm == 'BASELINE' else with_sources(r['context'], [chunks[c]['content'] for c in ids])
            assert sum(chunks[c]['tokens'] for c in ids) <= 4000
            out.append({'id': r['id'], 'arm': arm, 'question': r['question'],
                        'gold': qa[r['question']]['Gold Answer'], 'type': qa[r['question']]['Type'],
                        'status': status, 'context': ctx, 'context_sha256': sha(ctx), 'chunk_ids': ids,
                        'full_evidence': full(ids, sets) if sets else None})
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / 'contexts.jsonl'
    path.write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in out))
    # share the oracle run's cached Qwen bodies and judge verdicts (keyed by body / prediction hash)
    if (ORACLE / 'qwen_cache').exists() and not (OUT / 'qwen_cache').exists():
        shutil.copytree(ORACLE / 'qwen_cache', OUT / 'qwen_cache')
    if not (OUT / 'judgments.jsonl').exists():
        shutil.copy(ORACLE / 'judgments.jsonl', OUT / 'judgments.jsonl')
    by = lambda a: [x for x in out if x['arm'] == a]
    summary = {'questions': 200, 'arms': list(ARMS),
               'full_evidence': {a: sum(bool(x['full_evidence']) for x in by(a)) for a in ARMS},
               'identical_to_baseline': {a: sum(x['context_sha256'] == b['context_sha256']
                                                for x, b in zip(by(a), by('BASELINE'))) for a in ARMS},
               'selections_sha256': sha((SET_OUT / 'offline_selections_dev200.json').read_bytes()),
               'contexts_sha256': sha(path.read_bytes()), 'builder_sha256': sha(Path(__file__).read_bytes()),
               'api_calls': 0}
    write(OUT / 'build.json', summary)
    print(json.dumps(summary, indent=1))


def exact_p(b, c):
    n = b + c
    return min(1., 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n) if n else 1.


def report():
    rows = lines(OUT / 'contexts.jsonl')
    meta = {(r['id'], r['arm']): r for r in rows}
    ans = {(r['id'], r['arm']): r for r in lines(OUT / 'answers.jsonl')}
    v = {(j['id'], j['prediction_sha256']): j['verdict'] for j in lines(OUT / 'judgments.jsonl') if j['judge_pass'] == 1}
    ids = sorted({r['id'] for r in rows if all((r['id'], a) in ans and (r['id'], ans[r['id'], a]['prediction_sha256']) in v
                                             for a in ARMS)})
    lab = lambda i, a: v[i, ans[i, a]['prediction_sha256']]
    groups = {'all': ids}
    for t in ('Single', 'Multi', 'Null'):
        groups[t] = [i for i in ids if meta[i, 'BASELINE']['type'] == t]
    res = {'n': len(ids), 'rates': {}, 'mcnemar_vs_baseline': {}}
    for g, s in groups.items():
        res['rates'][g] = {a: {l: round(100 * sum(lab(i, a) == l for i in s) / len(s), 2) for l in runner.LABELS}
                           for a in ARMS} if s else None
        res['mcnemar_vs_baseline'][g] = {}
        for a in ARMS[1:]:
            m = {}
            for l in ('accurate', 'error'):
                up = sum(lab(i, 'BASELINE') != l and lab(i, a) == l for i in s)
                dn = sum(lab(i, 'BASELINE') == l and lab(i, a) != l for i in s)
                m[l] = {'became': up, 'ceased': dn, 'net': up - dn, 'p_exact': exact_p(up, dn)}
            res['mcnemar_vs_baseline'][g][a] = m
    write(OUT / 'results.json', res)
    for g in groups:
        if res['rates'][g]:
            print(g, len(groups[g]), {a: res['rates'][g][a]['accurate'] for a in ARMS},
                  {a: (x['accurate']['became'], x['accurate']['ceased'], round(x['accurate']['p_exact'], 5))
                   for a, x in res['mcnemar_vs_baseline'][g].items()})


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('step', choices=('build', 'generate', 'judge', 'report'))
    ap.add_argument('--workers', type=int, default=16)
    ap.add_argument('--concurrency', type=int, default=8)
    a = ap.parse_args()
    runner.OUT, runner.ARMS = OUT, ARMS
    if a.step == 'build':
        build()
    elif a.step == 'generate':
        runner.generate(a.workers)
    elif a.step == 'judge':
        asyncio.run(runner.judge_all(a.concurrency))
    else:
        report()
