"""Offline evaluation of selection arms on dev200 (0 API calls).

Metric: questions whose Sources keep FULL evidence (every Evidence stamp has a
chunk present), paired McNemar against BASELINE. Qwen answers ~83% of
full-evidence questions correctly (oracle 11/11), so this tracks ACC closely
and costs nothing. QA is run only for arms that clear this gate.

Scorer files (from the trained SLM) are JSONL rows
  {"id": <dev id>, "chunk_id": ..., "p": <calibrated probability>, "trained_on_folds": [...]}
and must be cross-fitted: a question's own fold is never in trained_on_folds.
beta and tau are chosen per outer fold on the OTHER folds only (nested), so the
reported numbers never use a question's own label for tuning.

    .venv/bin/python -m reproduce.evidence_set.evaluate [--scores name=path ...] [--pool NAME]
"""
import argparse
from math import ceil, comb
import json
from pathlib import Path
import statistics

from reproduce.graph_ablation.study import lines, write
from reproduce.evidence_set.data import corpus, gold, full, a1, folds, BUDGET
from reproduce.evidence_set.features import pool_of
from reproduce.evidence_set.pool import OUT
from reproduce.evidence_set.select import facets, select, rerank

BETAS = (0.0, 0.25, 0.5, 1.0, 2.0)
TAUS = (0.0, 0.05, 0.1, 0.2, 0.5, 1.0)


def exact_p(b, c):
    n = b + c
    return min(1., 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n) if n else 1.


def load_scores(path, rows, fold):
    by_q = {}
    for s in lines(Path(path)):
        by_q.setdefault(s['id'], {})[s['chunk_id']] = float(s['p'])
        q = rows[s['id']]['question']
        assert fold[q] not in s.get('trained_on_folds', []), f'leak: question {s["id"]} scored by a model trained on its fold'
        assert 0.0 <= float(s['p']) <= 1.0, 'p must be a probability'
    return by_q


def tune(qs, rows, pools, fmap, p, fold, betas=BETAS):
    """Nested choice of (beta, tau) for each outer fold, on labelled questions of the other folds."""
    lab = [i for i in qs if gold(rows[i]['question'])[2] == 'labelled']
    grid = {}
    for b in betas:
        for t in TAUS:
            res = {i: select(pools[i], p.get(i, {}), fmap[i], beta=b, tau=t) for i in lab}
            grid[b, t] = {i: (full(res[i][0], gold(rows[i]['question'])[1]), res[i][1]['tokens']) for i in lab}
    choice = {}
    for f in range(5):
        train = [i for i in lab if fold[rows[i]['question']] != f]
        score = lambda bt: sum(grid[bt][i][0] for i in train)
        best = max(score(bt) for bt in grid)
        tol = ceil(0.01 * len(train))
        ok = [bt for bt in grid if score(bt) >= best - tol]
        # among near-best settings: fewest tokens, then the highest score, then the simplest
        choice[f] = min(ok, key=lambda bt: (statistics.mean(grid[bt][i][1] for i in train), -score(bt), bt))
    return choice


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--scores', nargs='*', default=[], help='name=path of cross-fitted scorer output')
    ap.add_argument('--pool', default=None)
    ap.add_argument('--oracle-set', action='store_true', help='also run set selection with oracle p (sanity only)')
    ap.add_argument('--tag', default='', help='suffix for the output files (keeps the main eval untouched)')
    a = ap.parse_args()
    chunks, _, _ = corpus()
    pool_name = a.pool or json.loads((OUT / 'coverage_dev200.json').read_text())['chosen_pool']
    rows = {r['id']: r for r in lines(OUT / 'pools_dev200.jsonl')}
    fold = folds([r['question'] for r in rows.values()])
    ids = sorted(rows)
    pools = {i: pool_of(rows[i], pool_name) for i in ids}
    pool30 = {i: [c for c in rows[i]['baseline_pool'] if c in chunks] for i in ids}
    fmap = {i: facets(rows[i], pools[i]) for i in ids}
    fmap30 = {i: facets(rows[i], pool30[i]) for i in ids}
    from reproduce.evidence_set.features import bm25_scores
    arms = {'BASELINE': {i: rows[i]['baseline_kept'] for i in ids},
            'A1_WIDE': {i: a1(pools[i]) for i in ids}}
    gsets = {i: gold(rows[i]['question'])[1] for i in ids}
    arms['ORACLE_WIDE'] = {i: a1([c for c in pools[i] if gsets[i] and any(c in g for g in gsets[i])] +
                                 [c for c in pools[i] if not (gsets[i] and any(c in g for g in gsets[i]))])
                           for i in ids}
    bm = {i: bm25_scores(rows[i]['question']) for i in ids}
    arms['BM25_RERANK'] = {i: rerank(pools[i], bm[i]) for i in ids}
    tuned = {}
    scorers = dict(s.split('=', 1) for s in a.scores)
    if a.oracle_set:
        scorers['ORACLE_P'] = None
    for name, path in scorers.items():
        if path is None:
            p = {i: {c: (0.95 if gsets[i] and any(c in g for g in gsets[i]) else 0.02) for c in pools[i]} for i in ids}
        else:
            p = load_scores(path, rows, fold)
            missing = [(i, c) for i in ids for c in pools[i] if c not in p.get(i, {})]
            assert not missing, f'{name}: {len(missing)} pool candidates have no score, e.g. {missing[:3]}'
        choice = tune(ids, rows, pools, fmap, p, fold)
        tuned[name] = {f: list(bt) for f, bt in choice.items()}
        bt = lambda i: choice[fold[rows[i]['question']]]
        arms[f'{name}_RERANK'] = {i: rerank(pools[i], p[i]) for i in ids}
        arms[f'{name}_SET'] = {i: select(pools[i], p[i], fmap[i], beta=bt(i)[0], tau=bt(i)[1])[0] for i in ids}
        nocov = tune(ids, rows, pools, fmap, p, fold, betas=(0.0,))  # ablation tuned on its own
        arms[f'{name}_SET_NO_COVERAGE'] = {i: select(pools[i], p[i], fmap[i], beta=0.0,
                                                     tau=nocov[fold[rows[i]['question']]][1])[0] for i in ids}
        arms[f'{name}_SET_FILL'] = {i: select(pools[i], p[i], fmap[i], beta=bt(i)[0], tau=0.0)[0] for i in ids}
        arms[f'{name}_SET_POOL30'] = {i: select(pool30[i], p[i], fmap30[i], beta=bt(i)[0], tau=bt(i)[1])[0]
                                      for i in ids}
    lab = [i for i in ids if gsets[i]]
    tok = lambda ids_: sum(chunks[c]['tokens'] for c in ids_)
    table = {}
    for arm, sel in arms.items():
        assert all(tok(sel[i]) <= BUDGET for i in ids), arm
        hit = {i: full(sel[i], gsets[i]) for i in lab}
        base = {i: full(arms['BASELINE'][i], gsets[i]) for i in lab}
        up = sum(hit[i] and not base[i] for i in lab)
        down = sum(base[i] and not hit[i] for i in lab)
        table[arm] = {'full_evidence': sum(hit.values()),
                      'Single': sum(hit[i] for i in lab if gold(rows[i]['question'])[0] == 'Single'),
                      'Multi': sum(hit[i] for i in lab if gold(rows[i]['question'])[0] == 'Multi'),
                      'vs_baseline': {'up': up, 'down': down, 'p_exact': exact_p(up, down)},
                      'tokens_median': statistics.median(tok(sel[i]) for i in ids),
                      'tokens_mean': round(statistics.mean(tok(sel[i]) for i in ids), 1),
                      'chunks_median': statistics.median(len(sel[i]) for i in ids),
                      'identical_to_baseline': sum(sel[i] == arms['BASELINE'][i] for i in ids)}
    result = {'pool': pool_name, 'labelled': len(lab), 'questions': len(ids), 'budget': BUDGET,
              'tuned_beta_tau_per_fold': tuned, 'table': table, 'api_calls': 0}
    write(OUT / f'offline_eval_dev200{a.tag}.json', result)
    write(OUT / f'offline_selections_dev200{a.tag}.json', {arm: {str(i): sel[i] for i in ids} for arm, sel in arms.items()})
    print(f"pool={pool_name}  labelled={len(lab)}")
    for arm, t in table.items():
        v = t['vs_baseline']
        print(f"{arm:28s} full={t['full_evidence']:3d}  S={t['Single']:3d} M={t['Multi']:2d}  "
              f"+{v['up']}/-{v['down']} p={v['p_exact']:.3g}  tok_med={t['tokens_median']}  chunks={t['chunks_median']}")
    if tuned:
        print(json.dumps(tuned))


if __name__ == '__main__':
    main()
