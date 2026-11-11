"""A-Z pipeline for the paper's Table 1 (ladder: each row adds one component).

  C0        MiniRAG original: graph top 30 -> A1@4000                   (profile c0)
  BASELINE  + source-time                                               (profile baseline)
  F         + learned scorer on graph/time/conversation-structure features, sort by p -> A1@4000
  CE0F      + semantic signal (zero-shot cross-encoder logit) in the same scorer
  CE0F_SET  + budgeted set selection (per-conversation diminishing returns + facet coverage)
Rows F..CE0F_SET score the first 45 candidates of the BASELINE ranking; widening 30 -> 45
alone changes no context (A1 stops at ~6 chunks), see offline_eval A1_WIDE.

Only the Sources block differs between BASELINE and the learned rows; C0 is the native C0
context (its own Entities too). Same reader (the SLM, on Modal), rag_response prompt,
4,000-token Sources budget; DeepSeek judge, Step_2 prompt, blind, 3 passes.

SLM (MINIRAG_EVSET_SLM=qwen|phi): each SLM runs the whole ladder on ITS OWN index (built by
that SLM, as in the paper), with its own parser, scorer training and reader.

Splits:
  dev200  scores are cross-fitted (5 folds grouped by conversation), beta/tau nested
  nondev  435 held-out questions; all-fold models + dev-chosen beta/tau, nothing tuned here

Steps (each is resumable, cached, and skips work already done):
  capture   native retrieval for baseline and c0 (pool.py; parser from cache)      0 LLM calls on dev
  score     features export + scorer (quick_scorer) + offline gate (evaluate)      0 API calls
  build     contexts for the five rows                                              0 API calls
  generate  Qwen answers, --rounds R (round r uses seed 13 + id + 100000*(r-1))     Modal
  judge     DeepSeek verdicts, 3 passes, for every new (question, answer)           DeepSeek
  report    Table 1: ACC / ERR / neither (mean over rounds x passes), per type,
            McNemar on the per-round majority verdict vs BASELINE and vs the row above

    MINIRAG_EVSET_SLM=phi .venv/bin/python -m reproduce.evidence_set.pipeline all --split nondev --rounds 3
"""
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import json
import pickle
import runpy
import statistics
import subprocess
import sys
import threading
from math import comb
from pathlib import Path

import numpy as np

from reproduce.graph_ablation.study import ROOT, sha, write, lines, append

from reproduce.evidence_set.pool import OUT as SET
from reproduce.evidence_set.slm import SLM, GEN_MODEL, URL_FILE, SPEC

ARMS = ('C0', 'BASELINE', 'F', 'CE0F', 'CE0F_SET')
LABEL = {'C0': 'C0 (MiniRAG original)', 'BASELINE': '+ source-time (baseline)',
         'F': '+ learned scorer: graph/time/structure features', 'CE0F': '+ semantic signal (cross-encoder)',
         'CE0F_SET': '+ budgeted set selection (full method)'}
SPLIT = {'dev200': {'n': 200, 'dir': SET / 'qa_dev200', 'shards': 2},
         'nondev': {'n': 435, 'dir': SET / 'qa_nondev435', 'shards': 4}}
LABELS = ('accurate', 'error', 'neither')
POOL = 'native@45'
PY = sys.executable


def ladder(split):
    return SPLIT[split]['dir'] / 'ladder'


def shards(split, profile):
    tag = 'dev200' if split == 'dev200' else 'nondev'
    if profile == 'baseline':
        if split == 'dev200':
            return [(SET / 'pools_dev200.jsonl', SET / 'contexts_dev200.jsonl')]  # phi: merged from 4 shards
        return [(SET / f'pools_nondev_{k}of4.jsonl', SET / f'contexts_nondev_{k}of4.jsonl') for k in range(4)]
    n = SPLIT[split]['shards']
    return [(SET / f'pools_{tag}_c0_{k}of{n}.jsonl', SET / f'contexts_{tag}_c0_{k}of{n}.jsonl') for k in range(n)]


def load(split, profile):
    rows, ctx = {}, {}
    for p, c in shards(split, profile):
        rows.update({r['id']: r for r in lines(p)})
        ctx.update({r['id']: r for r in lines(c)})
    return rows, ctx


# ---------------------------------------------------------------- capture
def capture(split):
    n = SPLIT[split]['n']
    for profile in ('baseline', 'c0'):
        rows, _ = load(split, profile)
        if len(rows) == n:
            print(f'capture {split}/{profile}: complete ({n})')
            continue
        if profile == 'baseline' and split == 'nondev':
            k_n = 4
        elif profile == 'baseline':
            k_n = 1 if SLM == 'qwen' else 4
        else:
            k_n = SPLIT[split]['shards']
        procs = [subprocess.Popen([PY, '-m', 'reproduce.evidence_set.pool', '--split', split, '--profile', profile,
                                   '--shard', f'{k}/{k_n}'], cwd=ROOT) for k in range(k_n)]
        assert all(p.wait() == 0 for p in procs), f'capture {split}/{profile} failed'
        if profile == 'baseline' and split == 'dev200' and k_n > 1:
            for kind in ('pools', 'contexts'):
                got = sorted((r for k in range(k_n) for r in lines(SET / f'{kind}_dev200_{k}of{k_n}.jsonl')),
                             key=lambda r: r['id'])
                (SET / f'{kind}_dev200.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in got))
        assert len(load(split, profile)[0]) == n


# ---------------------------------------------------------------- score
def score():
    if not (SET / 'codex/export_manifest.json').exists():
        subprocess.run([PY, '-m', 'reproduce.evidence_set.features', 'export', '--pool', POOL], cwd=ROOT, check=True)
    if not all((SET / f'models/{m}_allfolds.pkl').exists() for m in ('F', 'CE0+F')):
        subprocess.run([PY, '-m', 'reproduce.evidence_set.quick_scorer', '--fit-all'], cwd=ROOT, check=True)
    if not (SET / 'offline_selections_dev200.json').exists():
        S = SET / 'scores'
        subprocess.run([PY, '-m', 'reproduce.evidence_set.evaluate', '--pool', POOL, '--scores',
                        f'CE0={S}/CE0.jsonl', f'F={S}/F.jsonl', f'CE0+F={S}/CE0+F.jsonl'], cwd=ROOT, check=True)


# ---------------------------------------------------------------- build
def selections(split, base_rows):
    """chunk ids per arm (except C0) for every question id."""
    from reproduce.evidence_set.select import facets, select, rerank
    if split == 'dev200':
        sel = json.loads((SET / 'offline_selections_dev200.json').read_text())
        src = {'BASELINE': 'BASELINE', 'F': 'F_RERANK', 'CE0F': 'CE0+F_RERANK', 'CE0F_SET': 'CE0+F_SET'}
        return {a: {i: sel[s][str(i)] for i in base_rows} for a, s in src.items()}, \
            {'scores': 'cross-fitted (5 folds); beta/tau nested per fold'}
    from reproduce.evidence_set.data import corpus
    from reproduce.evidence_set.features import featurize, pool_of, FEATURES
    from reproduce.evidence_set.quick_scorer import ce_logits
    from reproduce.evidence_set.nondev import dev_beta_tau
    chunks, _, _ = corpus()
    models = {m: pickle.load((SET / f'models/{m}_allfolds.pkl').open('rb')) for m in ('F', 'CE0+F')}
    beta, tau = dev_beta_tau(models['CE0+F'])[0]
    ids = sorted(base_rows)
    cand = [{'id': i, 'question': base_rows[i]['question'],
             'candidates': featurize(base_rows[i], pool_of(base_rows[i], POOL))} for i in ids]
    ce = ce_logits(cand, chunks, SET / 'ce0_logits_nondev435.json')
    out = {a: {} for a in ('BASELINE', 'F', 'CE0F', 'CE0F_SET')}
    for c in cand:
        i, r = c['id'], base_rows[c['id']]
        pool = [x['chunk_id'] for x in c['candidates']]
        Xf = np.array([[x['features'][k] for k in FEATURES] for x in c['candidates']], float)
        z = np.array([[ce[f"{i}|{x['chunk_id']}"]] for x in c['candidates']], float)
        pf = dict(zip(pool, models['F'].predict_proba(Xf)[:, 1]))
        p = dict(zip(pool, models['CE0+F'].predict_proba(np.hstack([z, Xf]))[:, 1]))
        out['BASELINE'][i] = r['baseline_kept']
        out['F'][i] = rerank(pool, pf)
        out['CE0F'][i] = rerank(pool, p)
        out['CE0F_SET'][i] = select(pool, p, facets(r, pool), beta=beta, tau=tau)[0]
    return out, {'scores': 'all-fold models fit on dev200 only', 'beta_tau_from_dev': [beta, tau],
                 'models_sha256': {m: sha((SET / f'models/{m}_allfolds.pkl').read_bytes()) for m in models}}


def build(split):
    from reproduce.evidence_set.data import corpus, gold, full
    from reproduce.evidence_set.qa import with_sources
    chunks, _, _ = corpus()
    n = SPLIT[split]['n']
    base, bctx = load(split, 'baseline')
    c0, c0ctx = load(split, 'c0')
    assert len(base) == len(c0) == n, 'run the capture step first'
    for i in base:
        assert base[i]['question'] == c0[i]['question']
        assert sha(bctx[i]['context']) == base[i]['context_sha256'] and sha(c0ctx[i]['context']) == c0[i]['context_sha256']
    sel, how = selections(split, base)
    qa = {}
    with (ROOT / 'dataset/LiHua-World/qa/query_set.csv').open() as f:
        for q in csv.DictReader(f):
            qa.setdefault(q['Question'], q)
    out = []
    for i in sorted(base):
        q = base[i]['question']
        typ, sets, status = gold(q)
        for arm in ARMS:
            if arm == 'C0':
                ids, ctx = c0[i]['baseline_kept'], c0ctx[i]['context']
            elif arm == 'BASELINE':
                ids, ctx = base[i]['baseline_kept'], bctx[i]['context']
                assert sel['BASELINE'][i] == ids
            else:
                ids = sel[arm][i]
                ctx = with_sources(bctx[i]['context'], [chunks[c]['content'] for c in ids])
            assert sum(chunks[c]['tokens'] for c in ids if c in chunks) <= 4000
            out.append({'id': i, 'arm': arm, 'question': q, 'gold': qa[q]['Gold Answer'], 'type': qa[q]['Type'],
                        'status': status, 'context': ctx, 'context_sha256': sha(ctx), 'chunk_ids': ids,
                        'full_evidence': full(ids, sets) if sets else None})
    d = ladder(split)
    d.mkdir(parents=True, exist_ok=True)
    (d / 'contexts.jsonl').write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in out))
    by = lambda a: [x for x in out if x['arm'] == a]
    summary = {'split': split, 'questions': n, 'arms': list(ARMS), 'pool': POOL, **how,
               'labelled': sum(x['full_evidence'] is not None for x in by('BASELINE')),
               'full_evidence': {a: sum(bool(x['full_evidence']) for x in by(a)) for a in ARMS},
               'identical_to_baseline': {a: sum(x['context_sha256'] == b['context_sha256']
                                                for x, b in zip(by(a), by('BASELINE'))) for a in ARMS},
               'contexts_sha256': sha((d / 'contexts.jsonl').read_bytes()),
               'pipeline_sha256': sha(Path(__file__).read_bytes()), 'api_calls': 0}
    write(d / 'build.json', summary)
    print(json.dumps(summary, indent=1))


def contexts(split):
    d = ladder(split)
    assert sha((d / 'contexts.jsonl').read_bytes()) == json.loads((d / 'build.json').read_text())['contexts_sha256']
    return lines(d / 'contexts.jsonl')


# ---------------------------------------------------------------- generate
def generate(split, rounds, workers):
    from reproduce.evidence_selector import lihua_qa
    from reproduce.oracle_headroom.run import RESPONSE_TYPE
    rows = contexts(split)
    d = ladder(split)
    template = runpy.run_path(str(ROOT / 'minirag/prompt.py'))['PROMPTS']['rag_response']
    lihua_qa.MODEL = GEN_MODEL  # the request body names the served model; Qwen keeps its old bodies (cache hits)

    class Reader(lihua_qa.Qwen):
        def __init__(self, out):
            super().__init__(out)
            base = (Path.home() / '.config/minirag' / URL_FILE).read_text().strip().rstrip('/')
            self.url = (base if base.endswith('/v1') else base + '/v1') + '/chat/completions'

    qwen = Reader(SPLIT[split]['dir'])  # body-hash cache shared with the earlier qa.py / nondev.py runs
    done = {(r['id'], r['arm'], r['round']) for r in lines(d / 'answers.jsonl')}
    lock = threading.Lock()

    def one(r, k):
        seeded = {**r, 'id': r['id'] + 100000 * (k - 1)}  # Qwen seed = 13 + id; round 1 == earlier runs
        v = qwen.call(seeded, template, RESPONSE_TYPE)
        with lock:
            append(d / 'answers.jsonl', {**{x: v[x] for x in ('prediction', 'prediction_sha256', 'seed', 'body_sha256')},
                                         'id': r['id'], 'arm': r['arm'], 'round': k, 'question': r['question'],
                                         'gold': r['gold'], 'type': r['type'], 'context_sha256': r['context_sha256']})

    for k in range(1, rounds + 1):
        for arm in ('BASELINE',) + tuple(a for a in ARMS if a != 'BASELINE'):  # identical bodies hit the cache
            todo = [r for r in rows if r['arm'] == arm and (r['id'], arm, k) not in done]
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for n, f in enumerate(as_completed([pool.submit(one, r, k) for r in todo]), 1):
                    f.result()
                    if n % 50 == 0 or n == len(todo):
                        print(f'round {k} {arm}: {n}/{len(todo)}', flush=True)


# ---------------------------------------------------------------- judge
def judge(split, workers):
    from reproduce.evidence_set.deepseek_judge import judge_answers
    judge_answers(lines(ladder(split) / 'answers.jsonl'), ladder(split) / 'judgments_deepseek.jsonl', workers)


# ---------------------------------------------------------------- report
def exact_p(b, c):
    n = b + c
    return min(1., 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n) if n else 1.


def majority(labels):
    """per-round verdict for McNemar: the label most passes gave; 3-way split -> pass 1."""
    top = max(LABELS, key=lambda l: (labels.count(l), l == labels[0]))
    return top if labels.count(top) > 1 else labels[0]


def report(split):
    from reproduce.evidence_set.deepseek_judge import PASSES
    d = ladder(split)
    rows = contexts(split)
    build_info = json.loads((d / 'build.json').read_text())
    meta = {(r['id'], r['arm']): r for r in rows}
    verdict = defaultdict(dict)
    for j in lines(d / 'judgments_deepseek.jsonl'):
        verdict[j['id'], j['prediction_sha256']][j['judge_pass']] = j['verdict']
    ans = defaultdict(dict)  # round -> (id, arm) -> [verdict per pass]
    for a in lines(d / 'answers.jsonl'):
        v = verdict.get((a['id'], a['prediction_sha256']), {})
        if all(p in v for p in PASSES):
            ans[a['round']][a['id'], a['arm']] = [v[p] for p in PASSES]
    ids = sorted({r['id'] for r in rows})
    rounds = sorted(k for k in ans if all((i, a) in ans[k] for i in ids for a in ARMS))
    assert rounds, 'no complete round yet: run generate and judge'
    groups = {'all': ids, **{t: [i for i in ids if meta[i, 'BASELINE']['type'] == t] for t in ('Single', 'Multi', 'Null')}}
    res = {'slm': SLM, 'generator': GEN_MODEL, 'split': split, 'questions': len(ids), 'rounds': rounds,
           'judge': 'deepseek-flash', 'judge_passes': list(PASSES), 'build': build_info, 'table': {}}
    maj = {k: {key: majority(v) for key, v in ans[k].items()} for k in rounds}
    for g, s in groups.items():
        res['table'][g] = {}
        for j, arm in enumerate(ARMS):
            # one number per (round, pass); mean over all, sd over rounds (pass-averaged) and over passes
            cell = {l: [[100 * sum(ans[k][i, arm][p] == l for i in s) / len(s) for p in range(len(PASSES))]
                        for k in rounds] for l in LABELS}
            row = {}
            for l, m in cell.items():
                per_round = [statistics.mean(x) for x in m]
                per_pass = [statistics.mean(m[k][p] for k in range(len(rounds))) for p in range(len(PASSES))]
                row[l] = {'mean': round(statistics.mean(per_round), 2), 'per_round': [round(x, 2) for x in per_round],
                          'sd_rounds': round(statistics.stdev(per_round), 2) if len(per_round) > 1 else None,
                          'sd_passes': round(statistics.stdev(per_pass), 2)}
            for ref in ('BASELINE', ARMS[j - 1] if j else None):
                if ref is None or ref == arm:
                    continue
                row[f'vs_{ref}'] = []
                for k in rounds:
                    m = {}
                    for l in ('accurate', 'error'):
                        up = sum(maj[k][i, ref] != l and maj[k][i, arm] == l for i in s)
                        dn = sum(maj[k][i, ref] == l and maj[k][i, arm] != l for i in s)
                        m[l] = {'became': up, 'ceased': dn, 'p_exact': exact_p(up, dn)}
                    row[f'vs_{ref}'].append(m)
            res['table'][g][arm] = row
    write(d / 'results.json', res)
    fe, lab = build_info['full_evidence'], build_info['labelled']
    sd = lambda x: f" ± {x['sd_rounds']:.2f}" if x['sd_rounds'] is not None else ''
    cmp = lambda r, key, l: '; '.join(f"{m[l]['became']}/{m[l]['ceased']}, p={m[l]['p_exact']:.2g}"
                                      for m in r[key]) if key in r else '—'
    md = [f"# Table 1 — {SPEC['name']}, {split} ({len(ids)} questions)", '',
          f"{len(rounds)} generation round(s) × {len(PASSES)} DeepSeek judge passes. ACC/ERR = mean over rounds × passes, "
          "± = sd between generation rounds. McNemar on the per-round majority verdict, one entry per round "
          "(became / ceased, exact p).", '',
          '| # | Configuration | Full evidence | ACC | ERR | Neither | ACC vs baseline | ACC vs row above | ERR vs row above |',
          '|---|---|---:|---:|---:|---:|---|---|---|']
    for j, arm in enumerate(ARMS):
        r = res['table']['all'][arm]
        above = 'vs_' + ARMS[j - 1] if j else None
        md.append(f"| {j + 1} | {LABEL[arm]} | {fe[arm]}/{lab} | {r['accurate']['mean']:.2f}{sd(r['accurate'])} | "
                  f"{r['error']['mean']:.2f}{sd(r['error'])} | {r['neither']['mean']:.2f} | "
                  f"{cmp(r, 'vs_BASELINE', 'accurate')} | {cmp(r, above, 'accurate') if above else '—'} | "
                  f"{cmp(r, above, 'error') if above else '—'} |")
    md += ['', '## ACC by question type', '', '| Configuration | ' + ' | '.join(f'{g} ({len(s)})' for g, s in groups.items() if g != 'all') + ' |',
           '|---|' + '---:|' * 3]
    for arm in ARMS:
        md.append(f'| {LABEL[arm]} | ' + ' | '.join(f"{res['table'][g][arm]['accurate']['mean']:.2f}"
                                                   for g in groups if g != 'all') + ' |')
    md += ['', f"Judge noise: sd between passes of baseline ACC = {res['table']['all']['BASELINE']['accurate']['sd_passes']:.2f}.",
           f"Rows 3–5 score the first 45 candidates of the baseline ranking. Widening 30 → 45 without re-scoring "
           f"leaves every context identical to the baseline. Scores: {build_info['scores']}."]
    (d / 'REPORT.md').write_text('\n'.join(md) + '\n')
    print('\n'.join(md))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('step', choices=('capture', 'score', 'build', 'generate', 'judge', 'report', 'all'))
    ap.add_argument('--split', choices=tuple(SPLIT), default='nondev')
    ap.add_argument('--rounds', type=int, default=1)
    ap.add_argument('--workers', type=int, default=16)
    ap.add_argument('--judge-workers', type=int, default=32)
    a = ap.parse_args()
    steps = ('capture', 'score', 'build', 'generate', 'judge', 'report') if a.step == 'all' else (a.step,)
    for s in steps:
        print(f'== {s} ({a.split})', flush=True)
        if s == 'capture':
            capture(a.split)
        elif s == 'score':
            score()
        elif s == 'build':
            build(a.split)
        elif s == 'generate':
            generate(a.split, a.rounds, a.workers)
        elif s == 'judge':
            judge(a.split, a.judge_workers)
        else:
            report(a.split)
