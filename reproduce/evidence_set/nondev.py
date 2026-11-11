"""Held-out test on the 435 non-dev questions (one shot; nothing here is tuned).

Frozen before this run, all from dev200 only:
  - CE0+F all-fold logistic regression (models/CE0+F_allfolds.pkl, quick_scorer --fit-all)
  - (beta, tau) for CE0F_SET: the near-best/fewest-token setting on all 177 labelled dev questions
  - pool native@45, budget 4,000 tokens
Non-dev Evidence labels are read only to report the offline full-evidence count.

Arms: BASELINE (native C0 + source-time + A1@4000 context captured by pool.py),
CE0F_SET, CE0F_RERANK. Same Qwen/Gemini settings as qa.py.

    .venv/bin/python -m reproduce.evidence_set.nondev build|generate|judge|report
"""
import argparse
import asyncio
import csv
import json
import math
import pickle
import statistics
from pathlib import Path

import numpy as np

from reproduce.graph_ablation.study import ROOT, sha, write, lines
from reproduce.evidence_set.data import corpus, gold, full
from reproduce.evidence_set.features import featurize, pool_of, FEATURES
from reproduce.evidence_set.pool import OUT as SET_OUT
from reproduce.evidence_set.select import facets, select, rerank
from reproduce.evidence_set.quick_scorer import ce_logits
from reproduce.evidence_set import qa as devqa
from reproduce.oracle_headroom import run as runner

OUT = SET_OUT / 'qa_nondev435'
ARMS = devqa.ARMS
POOL = 'native@45'


def dev_beta_tau(model):
    """(beta, tau) from all labelled dev questions, same rule as evaluate.tune (1% tolerance, fewest tokens)."""
    from reproduce.evidence_set.evaluate import BETAS, TAUS
    rows = lines(SET_OUT / 'codex/train_dev200.jsonl')
    chunks = {c['chunk_id']: c for c in lines(SET_OUT / 'codex/chunks.jsonl')}
    pools = {r['id']: r for r in lines(SET_OUT / 'pools_dev200.jsonl')}
    ce = ce_logits(rows, chunks, SET_OUT / 'ce0_logits_dev200.json')
    # cross-fitted p, exactly what evaluate.py used, so the choice is not fit on in-sample scores
    p = {}
    for s in lines(SET_OUT / 'scores/CE0+F.jsonl'):
        p.setdefault(s['id'], {})[s['chunk_id']] = s['p']
    lab = [r for r in rows if r['status'] == 'labelled']
    grid = {}
    for b in BETAS:
        for t in TAUS:
            res = []
            for r in lab:
                pool = [x['chunk_id'] for x in r['candidates']]
                ids, info = select(pool, p[r['id']], facets(pools[r['id']], pool), beta=b, tau=t)
                res.append((full(ids, gold(r['question'])[1]), info['tokens']))
            grid[b, t] = (sum(x[0] for x in res), statistics.mean(x[1] for x in res))
    best = max(v[0] for v in grid.values())
    ok = [bt for bt in grid if grid[bt][0] >= best - math.ceil(0.01 * len(lab))]
    return min(ok, key=lambda bt: (grid[bt][1], -grid[bt][0], bt)), grid


def build():
    chunks, _, _ = corpus()
    rows, ctxs = [], {}
    for k in range(4):
        rows += lines(SET_OUT / f'pools_nondev_{k}of4.jsonl')
        ctxs.update({r['id']: r for r in lines(SET_OUT / f'contexts_nondev_{k}of4.jsonl')})
    rows.sort(key=lambda r: r['id'])
    assert [r['id'] for r in rows] == list(range(435)), 'non-dev capture incomplete'
    dev = {r['question'] for r in lines(SET_OUT / 'pools_dev200.jsonl')}
    assert not dev & {r['question'] for r in rows}, 'dev question leaked into non-dev'
    model = pickle.load((SET_OUT / 'models/CE0+F_allfolds.pkl').open('rb'))
    beta, tau = dev_beta_tau(model)[0]
    cand = [{'id': r['id'], 'question': r['question'], 'candidates': featurize(r, pool_of(r, POOL))} for r in rows]
    ce = ce_logits(cand, chunks, SET_OUT / 'ce0_logits_nondev435.json')
    qa = {}
    with (ROOT / 'dataset/LiHua-World/qa/query_set.csv').open() as f:
        for q in csv.DictReader(f):
            qa.setdefault(q['Question'], q)
    out, offline = [], {a: 0 for a in ARMS}
    labelled = 0
    for r, c in zip(rows, cand):
        assert sha(ctxs[r['id']]['context']) == ctxs[r['id']]['context_sha256'] == r['context_sha256']
        pool = [x['chunk_id'] for x in c['candidates']]
        X = np.array([[ce[f"{r['id']}|{x['chunk_id']}"]] + [x['features'][k] for k in FEATURES]
                      for x in c['candidates']], float)
        p = dict(zip(pool, model.predict_proba(X)[:, 1]))
        sel = {'BASELINE': r['baseline_kept'],
               'CE0F_SET': select(pool, p, facets(r, pool), beta=beta, tau=tau)[0],
               'CE0F_RERANK': rerank(pool, p)}
        typ, sets, status = gold(r['question'])
        labelled += bool(sets)
        for arm in ARMS:
            ids = sel[arm]
            assert sum(chunks[i]['tokens'] for i in ids) <= 4000
            base = ctxs[r['id']]['context']
            ctx = base if arm == 'BASELINE' else devqa.with_sources(base, [chunks[i]['content'] for i in ids])
            fe = full(ids, sets) if sets else None
            offline[arm] += bool(fe)
            out.append({'id': r['id'], 'arm': arm, 'question': r['question'],
                        'gold': qa[r['question']]['Gold Answer'], 'type': qa[r['question']]['Type'],
                        'status': status, 'context': ctx, 'context_sha256': sha(ctx), 'chunk_ids': ids,
                        'full_evidence': fe})
    # baseline rebuilt from its own chunk list must equal the captured context (Sources format check)
    b0 = next(x for x in out if x['arm'] == 'BASELINE')
    assert devqa.with_sources(b0['context'], [chunks[i]['content'] for i in b0['chunk_ids']]).count('Time:') \
        == b0['context'].count('Time:')
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / 'contexts.jsonl'
    path.write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in out))
    summary = {'questions': 435, 'labelled': labelled, 'pool': POOL, 'beta_tau_from_dev': [beta, tau],
               'offline_full_evidence': offline,
               'model_sha256': sha((SET_OUT / 'models/CE0+F_allfolds.pkl').read_bytes()),
               'contexts_sha256': sha(path.read_bytes()), 'builder_sha256': sha(Path(__file__).read_bytes()),
               'api_calls': 0}
    write(OUT / 'build.json', summary)
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('step', choices=('build', 'generate', 'judge', 'report'))
    ap.add_argument('--workers', type=int, default=16)
    ap.add_argument('--concurrency', type=int, default=8)
    a = ap.parse_args()
    runner.OUT, runner.ARMS = OUT, ARMS
    devqa.OUT = OUT
    if a.step == 'build':
        build()
    elif a.step == 'generate':
        runner.generate(a.workers)
    elif a.step == 'judge':
        asyncio.run(runner.judge_all(a.concurrency))
    else:
        devqa.report()
