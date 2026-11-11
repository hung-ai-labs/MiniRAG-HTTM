"""Step A: how many questions does each candidate pool fully cover? (0 API calls)

Rule fixed BEFORE looking at the numbers (11/11/2026):
  n* = smallest native cut n in (30, 45, 60, 90, 120) whose full-evidence count is
       within ceil(2% of labelled questions) of the uncut native ranking ("all").
  If no cut qualifies, the pool is "all".
Expansions (date chunks, same-document chunks, dense top 30) are reported for
reference; adopting one is a separate decision.

    .venv/bin/python -m reproduce.evidence_set.coverage
"""
import json
import math
import statistics

from reproduce.graph_ablation.study import lines, write
from reproduce.evidence_set.data import corpus, gold, full
from reproduce.evidence_set.pool import OUT

CUTS = (30, 45, 60, 90, 120)


def variants(r):
    chunks, _, by_doc = corpus()
    ranked = [c for c in r['final_full'] if c in chunks]
    dates = [c for a in r['anchors'] for c in r['date_chunks'][a] if c in chunks]
    every = list(dict.fromkeys(ranked))
    out = {f'native@{n}': ranked[:n] for n in CUTS}
    out['native@all'] = every
    out['all+date'] = list(dict.fromkeys(every + dates))
    out['all+same_doc'] = list(dict.fromkeys(every + [s for c in every for s in by_doc[chunks[c]['doc']]]))
    out['all+dense30'] = list(dict.fromkeys(every + [c for c in r['dense_ids'] if c in chunks]))
    out['all+date+same_doc'] = list(dict.fromkeys(out['all+date'] + out['all+same_doc']))
    return out


def main():
    chunks, _, by_doc = corpus()
    rows = lines(OUT / 'pools_dev200.jsonl')
    assert len(rows) == 200, len(rows)
    per = []
    for r in rows:
        typ, sets, status = gold(r['question'])
        v = variants(r)
        rec = {'id': r['id'], 'type': typ, 'status': status, 'sizes': {k: len(x) for k, x in v.items()},
               'tokens': {k: sum(chunks[c]['tokens'] for c in x) for k, x in v.items()}}
        if sets:
            ranked = v['native@all']
            pos = {c: i for i, c in enumerate(ranked)}
            rec['full'] = {k: full(x, sets) for k, x in v.items()}
            rec['full']['baseline_kept'] = full(r['baseline_kept'], sets)
            rec['worst_gold_rank'] = max((min((pos[c] for c in g if c in pos), default=None) or 0)
                                         if any(c in pos for c in g) else math.inf for g in sets)
            missing = [g for g in sets if not any(c in pos for c in g)]
            where = []
            for g in missing:
                if any(c in r['dense_ids'] for c in g):
                    where.append('dense30')
                elif any(c in v['all+date'] for c in g):
                    where.append('date')
                elif any(c in v['all+same_doc'] for c in g):
                    where.append('same_doc')
                else:
                    where.append('unreached')
            rec['missing_gold_found_in'] = where
        per.append(rec)
    lab = [p for p in per if p['status'] == 'labelled']
    names = list(lab[0]['full'])
    count = lambda k, s: sum(p['full'][k] for p in s)
    table = {}
    for k in names:
        table[k] = {'full_evidence': count(k, lab),
                    'Single': count(k, [p for p in lab if p['type'] == 'Single']),
                    'Multi': count(k, [p for p in lab if p['type'] == 'Multi'])}
        if k != 'baseline_kept':
            sizes = [p['sizes'][k] for p in per]
            toks = [p['tokens'][k] for p in per]
            table[k].update(size_median=statistics.median(sizes), size_p90=sorted(sizes)[int(.9 * len(sizes))],
                            size_max=max(sizes), tokens_median=statistics.median(toks))
    tol = math.ceil(0.02 * len(lab))
    ok = [n for n in CUTS if table[f'native@{n}']['full_evidence'] >= table['native@all']['full_evidence'] - tol]
    choice = f'native@{ok[0]}' if ok else 'native@all'
    ranks = sorted(p['worst_gold_rank'] for p in lab if p['worst_gold_rank'] != math.inf)
    where = {}
    for p in lab:
        for w in p['missing_gold_found_in']:
            where[w] = where.get(w, 0) + 1
    result = {'labelled': len(lab), 'questions': len(per), 'table': table, 'rule_tolerance_questions': tol,
              'chosen_pool': choice,
              'worst_gold_rank_when_reachable': {'n': len(ranks), 'median': statistics.median(ranks),
                                                 'p90': ranks[int(.9 * len(ranks))], 'max': max(ranks),
                                                 'over_30': sum(x >= 30 for x in ranks),
                                                 'over_60': sum(x >= 60 for x in ranks)},
              'questions_with_unreachable_gold': sum(bool(p['missing_gold_found_in']) for p in lab),
              'unreachable_gold_stamps_found_in': where, 'api_calls': 0}
    write(OUT / 'coverage_dev200.json', result)
    write(OUT / "coverage_dev200_per_question.json", [{**p, "worst_gold_rank": None if p.get("worst_gold_rank") == math.inf else p.get("worst_gold_rank")} for p in per])
    print(json.dumps(result, indent=1, default=str))


if __name__ == '__main__':
    main()
