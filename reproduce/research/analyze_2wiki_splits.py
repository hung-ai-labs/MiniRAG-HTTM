"""Explore grouped 80/20 splits; report aggregates only, never freeze a split."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import sys


def digest(data):
    return hashlib.sha256(data).hexdigest()


def components(rows):
    parent = list(range(len(rows)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    owners = {}
    for i, q in enumerate(rows):
        for title in sorted({t for t, _ in q['supporting_facts']}):
            if title in owners:
                parent[find(i)] = find(owners[title])
            else:
                owners[title] = i
    groups = {}
    for i in range(len(rows)):
        groups.setdefault(find(i), []).append(i)
    return sorted(groups.values(), key=lambda g: min(rows[i]['_id'] for i in g))


def candidate_split(rows, fraction, seed):
    groups = components(rows)
    totals = Counter(q['type'] for q in rows)
    targets = {kind: count * fraction for kind, count in totals.items()}
    chosen = Counter()
    test = set()
    order = list(groups)
    random.Random(seed).shuffle(order)
    order.sort(key=len, reverse=True)

    def loss(counts):
        # Predeclared exploratory heuristic: squared errors in total test size
        # and each type, scaled by the target so rare types also matter.
        return ((sum(counts.values()) - len(rows) * fraction) ** 2 / max(1, len(rows) * fraction)
                + sum((counts[k] - targets[k]) ** 2 / max(1, targets[k]) for k in totals))

    for group in order:
        extra = Counter(rows[i]['type'] for i in group)
        if loss(chosen + extra) < loss(chosen):
            chosen.update(extra)
            test.update(group)
    # Repair early greedy choices without breaking any connected component.
    # Fixed cap and strict improvement keep the search deterministic and bounded.
    for _ in range(20):
        improved = False
        for group in order:
            extra = Counter(rows[i]['type'] for i in group)
            selected = group[0] in test
            candidate = chosen - extra if selected else chosen + extra
            if loss(candidate) < loss(chosen) - 1e-12:
                chosen = candidate
                if selected:
                    test.difference_update(group)
                else:
                    test.update(group)
                improved = True
        if not improved:
            break
    dev = set(range(len(rows))) - test
    assert dev and test and dev.isdisjoint(test)
    assert all(set(group) <= dev or set(group) <= test for group in groups)
    return dev, test, groups


def title_overlap(rows, dev, test, key):
    def counts(indices):
        return Counter(title for i in indices for title in {t for t, _ in rows[i][key]})
    a, b = counts(dev), counts(test)
    common = sorted(a.keys() & b.keys())
    return {'shared_unique_titles': len(common),
            'cross_split_query_pairs_sharing_a_title_sum': sum(a[t] * b[t] for t in common),
            'pair_count_note': 'sum over shared titles; a query pair sharing multiple titles is counted multiple times'}


def summarize(rows, dev, test, groups):
    by_type = {}
    for kind in sorted({q['type'] for q in rows}):
        a = sum(rows[i]['type'] == kind for i in dev)
        b = sum(rows[i]['type'] == kind for i in test)
        by_type[kind] = {'internal_dev': a, 'internal_test': b,
                         'dev_percent': round(100 * a / len(dev), 3),
                         'test_percent': round(100 * b / len(test), 3),
                         'absolute_distribution_gap_pp': round(abs(100*a/len(dev) - 100*b/len(test)), 3)}
    gold_overlap = title_overlap(rows, dev, test, 'supporting_facts')
    assert gold_overlap['shared_unique_titles'] == 0
    return {'n_queries': len(rows), 'internal_dev_count': len(dev), 'internal_test_count': len(test),
            'actual_test_fraction': len(test) / len(rows),
            'gold_components': len(groups), 'largest_gold_component': max(map(len, groups)),
            'types': by_type, 'gold_title_overlap': gold_overlap,
            'all_context_title_overlap': title_overlap(rows, dev, test, 'context'),
            'near_duplicate_text_check': 'not_implemented_not_yet_checked',
            'query_ids_sha256': digest(json.dumps(sorted(q['_id'] for q in rows), ensure_ascii=False,
                                                separators=(',', ':')).encode('utf-8'))}


def self_test():
    def q(i, titles, kind):
        return {'_id': str(i), 'type': kind, 'supporting_facts': [[t, 0] for t in titles],
                'context': [[t, ['text']] for t in titles] + [['distractor', ['shared']]]}
    rows = [q(0, ['a'], 'x'), q(1, ['a', 'b'], 'y'), q(2, ['b'], 'x')]
    rows += [q(i, [f'gold-{i}'], 'x' if i % 2 else 'y') for i in range(3, 20)]
    dev, test, groups = candidate_split(rows, .2, 13)
    assert any(set(g) == {0, 1, 2} for g in groups)
    assert (dev, test, groups) == candidate_split(rows, .2, 13)
    report = summarize(rows, dev, test, groups)
    assert report['gold_title_overlap']['shared_unique_titles'] == 0
    assert report['all_context_title_overlap']['shared_unique_titles'] >= 1
    print('SELF-TEST OK: transitive gold groups, deterministic allocation, zero shared gold titles, shared distractor detection')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--repo', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--sizes', nargs='+', type=int, default=[200, 500, 1000, 2000])
    parser.add_argument('--seed', type=int, default=13)
    parser.add_argument('--test-fraction', type=float, default=.2)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.repo is None or args.out is None:
        parser.error('Supply --repo and --out, or --self-test')
    if args.out.exists():
        parser.error('Report already exists; use a new filename')
    if not 0 < args.test_fraction < 1:
        parser.error('test-fraction must be between zero and one')
    root = args.repo.resolve()
    measure_blob = (root / 'docs/research/env/2wiki_pool_measurements_seed13.json').read_bytes()
    measurements = json.loads(measure_blob)
    if measurements['sampling']['seed'] != args.seed:
        raise ValueError('Seed differs from the measurements report')
    raw_blob = (root / 'dataset/2WikiMultiHopQA/raw/extracted/dev.json').read_bytes()
    if digest(raw_blob) != measurements['provenance']['raw_dev_sha256']:
        raise ValueError('Source checksum mismatch')
    rows = sorted(json.loads(raw_blob), key=lambda q: q['_id'])
    random.Random(args.seed).shuffle(rows)
    recorded = {r['n_queries']: r for r in measurements['results']}
    reports = []
    for n in sorted(set(args.sizes)):
        if n not in recorded or not 1 < n <= len(rows):
            parser.error(f'Pool size {n} has not been measured')
        pool = rows[:n]
        dev, test, groups = candidate_split(pool, args.test_fraction, args.seed)
        report = summarize(pool, dev, test, groups)
        if report['query_ids_sha256'] != recorded[n]['query_ids_sha256']:
            raise ValueError(f'Pool identity mismatch at N={n}')
        reports.append(report)
        worst = max(v['absolute_distribution_gap_pp'] for v in report['types'].values())
        print(f"N={n}: dev={len(dev)}, test={len(test)}, gold_overlap=0, "
              f"context_overlap={report['all_context_title_overlap']['shared_unique_titles']}, "
              f"max_type_gap_pp={worst}")
    output = {'status': 'exploratory_only_not_a_frozen_split', 'selected_n': None,
              'requested_test_fraction': args.test_fraction, 'seed': args.seed,
              'allocation': 'gold-title connected components; seeded largest-first greedy squared-error allocation, then at most 20 strictly improving whole-group reassignment passes',
              'near_duplicate_text_check': 'pending; do not claim complete leakage prevention',
              'internal_test_policy': 'aggregate report only; no test IDs, question text, answers or predictions emitted',
              'provenance': {'measurement_report_sha256': digest(measure_blob),
                             'raw_dev_sha256': digest(raw_blob), 'script_sha256': digest(Path(__file__).read_bytes()),
                             'python_version': sys.version.split()[0]}, 'results': reports}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes((json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8'))
    print(f'Report: {args.out}')


if __name__ == '__main__':
    main()
