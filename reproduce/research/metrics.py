"""Offline metrics for the shared judge_run per_question.csv contract.

Summarize a generation repeat, then compare one or several matching repeats.
No model imports or API calls. Unknown labels and inconsistent majority columns
are rejected. Failed/missing verdicts remain failures, never become neither.
Full run completion cannot be certified from judge CSV alone.
"""

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import statistics

LABELS = ('accurate', 'error', 'neither')
FAILURES = ('parse_failed', 'judge_failed', 'missing')


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def read_csv(path):
    return list(csv.DictReader(io.StringIO(Path(path).read_text(encoding='utf-8-sig'), newline='')))


def vote(labels):
    if any(x not in LABELS for x in labels):
        return 'incomplete'
    best, n = Counter(labels).most_common(1)[0]
    return best if 2*n > len(labels) else 'no_majority'


def rates(values):
    counts = Counter(values)
    valid = sum(counts[k] for k in LABELS)
    return {'n_expected': len(values), 'n_valid': valid,
            'n_parse_failed': counts['parse_failed'], 'n_infra_failed': counts['judge_failed'],
            'n_missing': counts['missing'], 'counts': {k: counts[k] for k in LABELS},
            'percent': {k: 100*counts[k]/valid if valid else None for k in LABELS}}


def mean_sd(values):
    if not values or any(v is None for v in values):
        return {'mean': None, 'sd': None}
    return {'mean': statistics.mean(values), 'sd': statistics.stdev(values) if len(values) > 1 else 0.0}


def groups_summary(rows, passes):
    groups = defaultdict(list)
    for row in rows:
        groups['all'].append(row)
        groups['type:' + row['Type']].append(row)
    result = {}
    for key, group in sorted(groups.items()):
        per_pass = [rates([r[p] for r in group]) for p in passes]
        majority = Counter(vote([r[p] for p in passes]) for r in group)
        completed = len(group) - majority['incomplete']
        result[key] = {'judge_passes': per_pass,
                      'judge_pass_mean_sd_percent': {k: mean_sd([p['percent'][k] for p in per_pass]) for k in LABELS},
                      'majority': {'n_expected': len(group), 'n_judged_complete': completed,
                                   'n_incomplete': majority['incomplete'], 'n_no_majority': majority['no_majority'],
                                   'counts': {k: majority[k] for k in LABELS},
                                   'percent_of_judged_complete': {k: 100*majority[k]/completed if completed else None
                                                                 for k in (*LABELS, 'no_majority')}}}
    return result


def prepare(questions, verdicts, repeat):
    expected = {}
    for q in questions:
        qid = q['query_id']
        if not qid or qid in expected:
            raise ValueError('Empty or duplicate expected query_id')
        expected[qid] = q.get('Type', q.get('type', '?'))
    if not expected:
        raise ValueError('Empty expected question set')
    if not verdicts:
        raise ValueError('Empty judge CSV')
    passes = sorted((k for k in verdicts[0] if k.startswith('pass') and k[4:].isdigit()), key=lambda k: int(k[4:]))
    if passes != ['pass1', 'pass2', 'pass3']:
        raise ValueError('This protocol requires exactly pass1, pass2, pass3')
    by_id = {}
    for r in verdicts:
        qid = r['query_id']
        if qid not in expected or qid in by_id:
            raise ValueError('Unexpected or duplicate judge query_id')
        if r.get('Type', expected[qid]) != expected[qid]:
            raise ValueError('Question type differs between expected set and judge CSV')
        labels = [r[p] for p in passes]
        if any(x not in LABELS + FAILURES for x in labels):
            raise ValueError('Unknown label: raw output must be parsed by the judge runner')
        if r.get('majority') != vote(labels):
            raise ValueError('Majority column does not match pass labels')
        by_id[qid] = r
    rows, long = [], []
    for qid, kind in sorted(expected.items()):
        row = {'query_id': qid, 'Type': kind, **{p: by_id.get(qid, {}).get(p, 'missing') for p in passes}}
        rows.append(row)
        for p in passes:
            value = row[p]
            long.append({'query_id': qid, 'Type': kind, 'gen_repeat': str(repeat), 'judge_pass': int(p[4:]),
                         'status': 'ok' if value in LABELS else value,
                         'label': value if value in LABELS else ''})
    return rows, long, passes


def mcnemar_exact(up, down):
    if min(up, down) < 0 or type(up) is not int or type(down) is not int:
        raise ValueError('Discordant counts must be nonnegative integers')
    n = up + down
    term = total = 1
    for k in range(1, min(up, down)+1):
        term = term * (n-k+1) // k
        total += term
    return min(1.0, 2*total/(2**n)) if n else 1.0


def paired_counts(a, b, label='accurate'):
    if a.keys() != b.keys():
        raise ValueError('Paired comparisons require identical query IDs')
    ids = sorted(a)
    complete = [i for i in ids if a[i] != 'incomplete' and b[i] != 'incomplete']
    up = sum(a[i] != label and b[i] == label for i in complete)
    down = sum(a[i] == label and b[i] != label for i in complete)
    return {'n_expected': len(ids), 'n_paired_complete': len(complete),
            'n_excluded_incomplete': len(ids)-len(complete), 'b_up': up, 'c_down': down,
            'net': up-down, 'delta_pp': 100*(up-down)/len(complete) if complete else None,
            'p_exact_two_sided': mcnemar_exact(up, down) if complete else None}


def query_bootstrap(differences, repetitions=10000, seed=13):
    import numpy as np
    if repetitions < 1000:
        raise ValueError('At least 1000 bootstrap draws are required')
    if not differences:
        raise ValueError('No complete paired queries')
    values = np.array(differences, dtype=float)
    rng = np.random.default_rng(seed)
    samples = []
    for start in range(0, repetitions, 256):
        idx = rng.integers(0, len(values), size=(min(256, repetitions-start), len(values)))
        samples.extend(values[idx].mean(axis=1).tolist())
    low, high = np.quantile(samples, [.025, .975])
    return {'n_queries': len(values), 'draws': repetitions, 'seed': seed,
            'delta_pp': float(100*values.mean()), 'ci95_pp': [float(100*low), float(100*high)],
            'resampling_unit': 'query; all generation repeats for that query remain together',
            'numpy_version': np.__version__}


def encode_csv(rows):
    buf = io.StringIO(newline='')
    writer = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode('utf-8')


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def summarize_cli(args):
    rows, long, passes = prepare(read_csv(args.questions), read_csv(args.judge_csv), args.gen_repeat)
    encoded = encode_csv(long)
    groups = groups_summary(rows, passes)
    report = {'schema_version': 1, 'scope': 'judge_metrics_only_not_full_run_certification',
              'judge_status': 'complete' if groups['all']['majority']['n_incomplete'] == 0 else 'partial',
              'gen_repeat': str(args.gen_repeat), 'groups': groups,
              'majority_policy': 'no_majority is a separate outcome; counts as not-accurate for binary McNemar; incomplete records are excluded and counted',
              'generation_failure_counts': None, 'early_exit_counts': None,
              'retrieval_metrics': None,
              'unavailable_reason': 'judge CSV does not contain generation/retrieval statuses or evidence; not inferred',
              'provenance': {'questions_sha256': sha(args.questions.read_bytes()),
                             'judge_csv_sha256': sha(args.judge_csv.read_bytes()),
                             'long_csv_sha256': sha(encoded), 'metrics_script_sha256': sha(Path(__file__).read_bytes())}}
    if args.run_manifest:
        manifest = json.loads(args.run_manifest.read_bytes())
        report['provenance']['run_manifest_sha256'] = sha(args.run_manifest.read_bytes())
        report['comparison_identity'] = {k: manifest.get(k) for k in ('config_hash', 'index_hash', 'split_hash', 'rubric_version', 'judge_model')}
    else:
        report['comparison_identity'] = None
    args.out.mkdir(parents=True)
    (args.out / 'per_question.csv').write_bytes(encoded)
    (args.out / 'metrics.json').write_bytes(json_bytes(report))
    print(json.dumps({'judge_status': report['judge_status'], 'majority': groups['all']['majority']}))


def load_bundle(path):
    report = json.loads((path / 'metrics.json').read_bytes())
    blob = (path / 'per_question.csv').read_bytes()
    if sha(blob) != report['provenance']['long_csv_sha256']:
        raise ValueError('Per-question CSV checksum mismatch')
    groups, seen, types = defaultdict(dict), set(), {}
    repeat = report['gen_repeat']
    for r in read_csv(path / 'per_question.csv'):
        if r['gen_repeat'] != repeat:
            raise ValueError('Mixed generation repeats in one bundle')
        key = (r['query_id'], r['judge_pass'])
        if key in seen:
            raise ValueError('Duplicate query/pass record')
        seen.add(key)
        status, label = r['status'], r['label']
        if status not in ('ok', *FAILURES) or (status == 'ok' and label not in LABELS) or (status != 'ok' and label):
            raise ValueError('Invalid long-form status/label')
        groups[r['query_id']][r['judge_pass']] = label if status == 'ok' else status
        if r['query_id'] in types and types[r['query_id']] != r['Type']:
            raise ValueError('Inconsistent question type')
        types[r['query_id']] = r['Type']
    if any(set(v) != {'1', '2', '3'} for v in groups.values()):
        raise ValueError('Missing or unexpected judge passes')
    reconstructed = [{'query_id': qid, 'Type': types[qid],
                      **{'pass'+str(p): g[str(p)] for p in (1, 2, 3)}} for qid, g in sorted(groups.items())]
    if groups_summary(reconstructed, ['pass1', 'pass2', 'pass3']) != report['groups']:
        raise ValueError('Stored metrics differ from recomputed per-question metrics')
    return report, {qid: vote([g[str(p)] for p in (1, 2, 3)]) for qid, g in groups.items()}, types


def compare_cli(args):
    def load(paths):
        result = {}
        for path in paths:
            bundle = load_bundle(path)
            repeat = bundle[0]['gen_repeat']
            if repeat in result:
                raise ValueError('Duplicate generation repeat')
            result[repeat] = bundle
        return result
    a, b = load(args.baseline), load(args.variant)
    if a.keys() != b.keys():
        raise ValueError('Generation repeats do not match')
    per_repeat, effects, identities = {}, defaultdict(list), []
    all_ids = None
    expected_source = None
    expected_types = None
    shared_identity = None
    for repeat in sorted(a):
        ra, va, ta = a[repeat]
        rb, vb, tb = b[repeat]
        if ta != tb:
            raise ValueError('Query IDs or types differ')
        if all_ids is None:
            all_ids = set(va)
            expected_source = ra['provenance']['questions_sha256']
            expected_types = ta
        elif set(va) != all_ids:
            raise ValueError('Question set differs across generation repeats')
        if ta != expected_types or ra['provenance']['questions_sha256'] != expected_source:
            raise ValueError('Expected question types/source differ across repeats')
        if ra['provenance']['questions_sha256'] != rb['provenance']['questions_sha256']:
            raise ValueError('Expected question source differs')
        ia, ib = ra['comparison_identity'], rb['comparison_identity']
        if ia and ib:
            for key in ('index_hash', 'split_hash', 'rubric_version', 'judge_model'):
                if ia[key] != ib[key]:
                    raise ValueError(f'Comparison identity mismatch: {key}')
            identity = {k: ia[k] for k in ('index_hash', 'split_hash', 'rubric_version', 'judge_model')}
            if shared_identity is not None and shared_identity != identity:
                raise ValueError('Comparison identities differ across generation repeats')
            shared_identity = identity
        identities.append(bool(ia and ib and all(ia.values()) and all(ib.values())))
        per_repeat[repeat] = {'accuracy': paired_counts(va, vb), 'error': paired_counts(va, vb, 'error')}
        for qid in sorted(va):
            if va[qid] != 'incomplete' and vb[qid] != 'incomplete':
                effects[qid].append(int(vb[qid] == 'accurate') - int(va[qid] == 'accurate'))
    complete = [statistics.mean(effects[qid]) for qid in sorted(effects) if len(effects[qid]) == len(a)]
    output = {'scope': 'paired_judge_comparison_not_a_full_benchmark_report', 'per_repeat': per_repeat,
              'accuracy_clustered_bootstrap': query_bootstrap(complete, args.bootstrap_draws, args.seed) if complete else None,
              'n_expected_queries': len(all_ids), 'n_queries_complete_across_all_repeats': len(complete),
              'n_queries_excluded_from_clustered_bootstrap': len(all_ids)-len(complete),
              'comparison_provenance_verified': all(identities),
              'generation_sd_delta_pp': mean_sd([r['accuracy']['delta_pp'] for r in per_repeat.values()]),
              'provenance': {'baseline_metrics_sha256': [sha((p/'metrics.json').read_bytes()) for p in args.baseline],
                             'variant_metrics_sha256': [sha((p/'metrics.json').read_bytes()) for p in args.variant],
                             'metrics_script_sha256': sha(Path(__file__).read_bytes())}}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(json_bytes(output))
    print(json.dumps({'provenance_verified': all(identities), 'per_repeat': per_repeat}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    summary = sub.add_parser('summarize')
    summary.add_argument('--questions', type=Path, required=True)
    summary.add_argument('--judge-csv', type=Path, required=True)
    summary.add_argument('--gen-repeat', required=True)
    summary.add_argument('--run-manifest', type=Path)
    summary.add_argument('--out', type=Path, required=True)
    compare = sub.add_parser('compare')
    compare.add_argument('--baseline', type=Path, nargs='+', required=True)
    compare.add_argument('--variant', type=Path, nargs='+', required=True)
    compare.add_argument('--bootstrap-draws', type=int, default=10000)
    compare.add_argument('--seed', type=int, default=13)
    compare.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('Output exists; use a new directory/file')
    if args.command == 'summarize':
        summarize_cli(args)
    else:
        compare_cli(args)


if __name__ == '__main__':
    main()
