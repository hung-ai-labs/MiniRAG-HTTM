"""Offline checks for 2Wiki preparation; no optional model/backend imports."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest


ROOT = Path(os.environ.get('MINIRAG_2WIKI_REPO', Path(__file__).resolve().parents[2]))


def module(name):
    path = ROOT / 'reproduce/research' / (name + '.py')
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_normalization_fixture():
    module('prepare_2wiki').self_test()


def test_grouped_split_fixture():
    module('analyze_2wiki_splits').self_test()


def test_pool_measurement_fixture():
    module('measure_2wiki_pools').self_test()


def test_near_duplicate_join_matches_exhaustive_search():
    module('audit_2wiki_duplicates').self_test()


def test_empty_short_and_boundary_shingles():
    audit = module('audit_2wiki_duplicates')
    assert audit.shingles('!!!') == set()
    assert audit.shingles('Hi') == {'hi'}
    pairs, _ = audit.similar_pairs([set(range(20)), set(range(17)), set(range(16))])
    assert (0, 1) in pairs  # exactly 0.85
    assert (0, 2) not in pairs


@pytest.mark.skipif(not (ROOT / 'dataset/2WikiMultiHopQA/processed/manifest.json').exists(),
                    reason='Local normalized dataset is not available')
def test_full_normalized_data_checksums_and_gold_separation():
    path = ROOT / 'dataset/2WikiMultiHopQA/processed'
    manifest = json.loads((path / 'manifest.json').read_bytes())
    for name, expected in manifest['outputs'].items():
        assert hashlib.sha256((path / name).read_bytes()).hexdigest() == expected['sha256']
    queries = [json.loads(line) for line in (path / 'queries.jsonl').read_bytes().splitlines()]
    gold = [json.loads(line) for line in (path / 'gold.jsonl').read_bytes().splitlines()]
    assert len(queries) == 12576
    assert len({q['query_id'] for q in queries}) == len(queries)
    assert all(set(q) == {'query_id', 'question', 'type'} for q in queries)
    assert [q['query_id'] for q in queries] == [g['query_id'] for g in gold]
    assert all(g['answer'] for g in gold)
    missing = [e for g in gold for e in g['evidence'] if e['mapping_status'] != 'ok']
    assert len(missing) == manifest['counts']['unmapped_supporting_facts'] == 70
    assert all(e['fact'] is None for e in missing)
    for line in (path / 'docs.jsonl').read_bytes().splitlines():
        doc = json.loads(line)
        assert set(doc) == {'doc_id', 'minirag_doc_id', 'title', 'text', 'sentences'}
        assert doc['text'] == doc['title'] + '\n' + ' '.join(doc['sentences'])
        assert doc['minirag_doc_id'] == 'doc-' + hashlib.md5(doc['text'].encode('utf-8')).hexdigest()


def test_aggregate_audit_keeps_test_content_private():
    path = ROOT / 'docs/research/env/2wiki_near_duplicate_audit_seed13.json'
    if not path.exists():
        pytest.skip('Aggregate audit has not been generated')
    report = json.loads(path.read_bytes())
    assert report['test_content_exported'] is False
    assert report['selected_n'] is None
    forbidden = {'question', 'answer', 'query_id', 'doc_id', 'internal_test_ids'}

    def check(value):
        if isinstance(value, dict):
            assert not (forbidden & value.keys())
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)
    check(report)
