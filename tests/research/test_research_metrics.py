"""Synthetic-only metrics tests; no real model answers or external services."""

import argparse
import importlib.util
import json
import math
import os
from pathlib import Path

import pytest

ROOT = Path(os.environ.get('MINIRAG_2WIKI_REPO', Path(__file__).resolve().parents[2]))
spec = importlib.util.spec_from_file_location('research_metrics', ROOT / 'reproduce/research/metrics.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def row(qid, labels):
    return {'query_id': qid, 'Type': 'comparison', **{f'pass{i}': x for i, x in enumerate(labels, 1)},
            'majority': m.vote(labels)}


def test_failed_parse_never_becomes_neither_and_missing_is_counted():
    expected = [{'query_id': str(i), 'Type': 'comparison'} for i in range(6)]
    judged = [row('0', ['accurate']*3), row('1', ['error']*3), row('2', ['neither']*3),
              row('3', ['accurate', 'error', 'neither']), row('4', ['parse_failed', 'judge_failed', 'accurate'])]
    rows, long, passes = m.prepare(expected, judged, '101')
    stats = m.groups_summary(rows, passes)['all']
    assert len(long) == 18
    assert stats['judge_passes'][0]['n_parse_failed'] == 1
    assert stats['judge_passes'][0]['n_missing'] == 1
    assert stats['judge_passes'][1]['n_infra_failed'] == 1
    assert stats['judge_passes'][0]['counts']['neither'] == 1
    assert stats['majority']['n_no_majority'] == 1
    assert stats['majority']['n_incomplete'] == 2
    assert stats['majority']['percent_of_judged_complete']['accurate'] == 25


@pytest.mark.parametrize('change', ['unknown_label', 'duplicate', 'wrong_type', 'wrong_majority', 'unknown_id'])
def test_corrupt_input_is_rejected(change):
    qs = [{'query_id': 'q', 'Type': 'comparison'}]
    verdicts = [row('q', ['accurate']*3)]
    if change == 'unknown_label':
        verdicts[0]['pass1'] = 'inaccurate'
    elif change == 'duplicate':
        verdicts += verdicts[:]
    elif change == 'wrong_type':
        verdicts[0]['Type'] = 'inference'
    elif change == 'wrong_majority':
        verdicts[0]['majority'] = 'error'
    elif change == 'unknown_id':
        verdicts[0]['query_id'] = 'unknown'
    with pytest.raises(ValueError):
        m.prepare(qs, verdicts, '101')


@pytest.mark.parametrize('b,c', [(0, 0), (9, 0), (9, 4), (24, 29), (110, 58)])
def test_mcnemar_matches_exact_binomial(b, c):
    expected = min(1, 2*sum(math.comb(b+c, k) for k in range(min(b, c)+1))/2**(b+c))
    assert m.mcnemar_exact(b, c) == pytest.approx(expected)


def test_paired_counts_use_ids_not_row_order():
    a = {'a': 'error', 'b': 'accurate', 'c': 'neither', 'd': 'incomplete'}
    b = {'d': 'accurate', 'c': 'accurate', 'b': 'error', 'a': 'accurate'}
    stats = m.paired_counts(a, b)
    assert stats['b_up'] == 2 and stats['c_down'] == 1
    assert stats['n_paired_complete'] == 3 and stats['n_excluded_incomplete'] == 1
    with pytest.raises(ValueError):
        m.paired_counts(a, {'a': 'accurate'})


def test_bootstrap_resamples_queries_and_is_reproducible():
    a = m.query_bootstrap([1, 0, -1, .5], 1000, 13)
    assert a == m.query_bootstrap([1, 0, -1, .5], 1000, 13)
    assert a['n_queries'] == 4 and a['delta_pp'] == 12.5
    assert m.query_bootstrap([1]*6, 1000, 13)['ci95_pp'] == [100, 100]


def make_bundle(tmp, config, repeat, labels, identity=True):
    tmp.mkdir(parents=True, exist_ok=True)
    questions = tmp / 'questions.csv'
    questions.write_bytes(m.encode_csv([{'query_id': 'q1', 'Type': 'comparison'}, {'query_id': 'q2', 'Type': 'comparison'}]))
    judged = tmp / f'{config}-{repeat}-judge.csv'
    judged.write_bytes(m.encode_csv([row('q1', [labels[0]]*3), row('q2', [labels[1]]*3)]))
    manifest = tmp / f'{config}-{repeat}-manifest.json'
    if identity:
        manifest.write_bytes(m.json_bytes({'config_hash': config, 'index_hash': 'same-index',
                                          'split_hash': 'same-split', 'rubric_version': 'fixture-v1',
                                          'judge_model': 'fixture-only-no-api'}))
    out = tmp / f'{config}-{repeat}'
    m.summarize_cli(argparse.Namespace(questions=questions, judge_csv=judged, gen_repeat=repeat,
                                     run_manifest=manifest if identity else None, out=out))
    return out


def test_metrics_recompute_roundtrip_and_tampering_rejection(tmp_path):
    out = make_bundle(tmp_path, 'baseline', '101', ['accurate', 'error'])
    report, labels, _ = m.load_bundle(out)
    assert labels == {'q1': 'accurate', 'q2': 'error'}
    report['groups']['all']['majority']['counts']['accurate'] = 999
    (out / 'metrics.json').write_bytes(m.json_bytes(report))
    with pytest.raises(ValueError, match='recomputed'):
        m.load_bundle(out)


def test_compare_repeats_clustered_by_query(tmp_path):
    a = [make_bundle(tmp_path, 'base', r, ['error', 'error']) for r in ('101', '202', '303')]
    b = [make_bundle(tmp_path, 'variant', r, ['accurate', 'accurate']) for r in ('101', '202', '303')]
    out = tmp_path / 'comparison.json'
    m.compare_cli(argparse.Namespace(baseline=a, variant=b, out=out, bootstrap_draws=1000, seed=13))
    result = json.loads(out.read_bytes())
    assert result['comparison_provenance_verified'] is True
    assert result['accuracy_clustered_bootstrap']['n_queries'] == 2  # not 6 repeats or 18 verdicts
    assert result['accuracy_clustered_bootstrap']['ci95_pp'] == [100, 100]
    assert all(r['accuracy']['b_up'] == 2 for r in result['per_repeat'].values())


def test_compare_rejects_judge_identity_mismatch(tmp_path):
    a = make_bundle(tmp_path, 'base', '101', ['error', 'error'])
    b = make_bundle(tmp_path, 'variant', '101', ['accurate', 'accurate'])
    data = json.loads((b / 'metrics.json').read_bytes())
    data['comparison_identity']['judge_model'] = 'different-judge'
    (b / 'metrics.json').write_bytes(m.json_bytes(data))
    with pytest.raises(ValueError, match='judge_model'):
        m.compare_cli(argparse.Namespace(baseline=[a], variant=[b], out=tmp_path/'comparison.json', bootstrap_draws=1000, seed=13))


def test_no_manifest_does_not_claim_verified_provenance(tmp_path):
    a = make_bundle(tmp_path, 'base', '101', ['error', 'error'], identity=False)
    b = make_bundle(tmp_path, 'variant', '101', ['accurate', 'accurate'], identity=False)
    out = tmp_path / 'comparison.json'
    m.compare_cli(argparse.Namespace(baseline=[a], variant=[b], out=out, bootstrap_draws=1000, seed=13))
    assert json.loads(out.read_bytes())['comparison_provenance_verified'] is False
