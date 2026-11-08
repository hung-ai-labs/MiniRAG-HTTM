"""Paired retrieval must preserve Sources, Entities, prompts, early exits and IDs."""
import asyncio
import contextlib
import csv
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'reproduce/research'))
from reproduce.research.two_wiki_acceleration import common, pipeline, judge_worker
from reproduce.research.two_wiki_acceleration.shared_context import SharedContext, build_offline, paired_query, stable_log

spec = importlib.util.spec_from_file_location('acceleration_fixture', ROOT / 'tests/research/test_phased_qa.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
phased = common.load_repo(ROOT)


@pytest.fixture(scope='module')
def tiny_index():
    with contextlib.redirect_stdout(io.StringIO()):
        fixture.PhasedEquivalenceTests.setUpClass()
    yield fixture.PhasedEquivalenceTests.index
    fixture.PhasedEquivalenceTests.tearDownClass()


@pytest.mark.parametrize('no_edges', [False, True])
def test_paired_contexts_and_answer_prompts_match_original(tmp_path, tiny_index, no_edges):
    async def scenario():
        from minirag.base import QueryParam
        import minirag.operate as operate
        rag = fixture.rag_at(phased.snapshot(tmp_path / 'index', tiny_index), fixture.QueryLLM())
        kw = tmp_path / 'kw.jsonl'
        phased.apply_env('C0', 101, kw_cache=kw)
        await phased.keyword_phase(rag, fixture.ROWS, kw)
        async def forbidden(*args, **kwargs):
            raise AssertionError('CPU phase called an LLM')
        rag.llm_model_func = forbidden
        if no_edges:
            async def empty(*args, **kwargs):
                return []
            rag.relationships_vdb.query = empty
        old = {}
        for c in ('C0', 'C1'):
            phased.apply_env(c, 101, kw_cache=kw, cache_only=True, context_log=tmp_path / f'old_{c}.jsonl')
            old[c] = [await rag.aquery(r['Question'], param=QueryParam(mode='mini', only_need_context=True)) for r in fixture.ROWS]
        adapter = SharedContext(operate)
        with adapter.installed():
            for i, row in enumerate(fixture.ROWS):
                pair, _ = await paired_query(rag, row, 101, kw, tmp_path / 'new', phased, adapter)
                for c in ('C0', 'C1'):
                    assert pair[c]['context'] == old[c][i]
                    assert pair[c]['status'] == ('no_context' if no_edges else 'ok')
                    if not no_edges:
                        assert phased.answer_messages('mini', row['Question'], pair[c]['context'], QueryParam().response_type) == phased.answer_messages('mini', row['Question'], old[c][i], QueryParam().response_type)
        assert adapter.prefix_calls == adapter.reuses == len(fixture.ROWS)
        assert operate._build_mini_query_context is adapter.original
        for c in ('C0', 'C1'):
            old_log = common.read_jsonl(tmp_path / f'old_{c}.jsonl', 'query')
            new_log = common.read_jsonl(tmp_path / f'new/{c}_s101/context.jsonl', 'query')
            assert {q: stable_log(v) for q, v in old_log.items()} == {q: stable_log(v) for q, v in new_log.items()}
    with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
        asyncio.run(scenario())


def test_adapter_restored_and_foreign_adapter_rejected():
    import minirag.operate as operate
    a, b = SharedContext(operate), SharedContext(operate)
    with pytest.raises(RuntimeError, match='sentinel'):
        with a.installed():
            with pytest.raises(RuntimeError, match='Another context'):
                with b.installed():
                    pass
            raise RuntimeError('sentinel')
    assert operate._build_mini_query_context is a.original


def test_offline_builder_rejects_llm_and_needs_no_credentials():
    import gemini_common
    resolver = gemini_common._resolve_api_keys
    def factory(snapshot, llm_max_async):
        assert gemini_common._resolve_api_keys() == []
        return SimpleNamespace(llm_model_func=None)
    rag = build_offline(SimpleNamespace(build=factory), Path('unused'))
    with pytest.raises(RuntimeError, match='never call an LLM'):
        asyncio.run(rag.llm_model_func('forbidden'))
    assert resolver is gemini_common._resolve_api_keys


def test_smoke_does_not_unlock_heldout(tmp_path):
    path = tmp_path / 'validation.json'
    common.write_json(path, {'status': 'verified', 'validation_scope': 'subset',
                            'completed_queries': 20, 'total_queries': 20,
                            'logical_answer_contexts': 40, 'mismatches': [], 'llm_calls': 0})
    with pytest.raises(ValueError, match='Full frozen 2Wiki'):
        pipeline.verify_validation(path, tmp_path / 'index')


def test_offline_plan_never_opens_test_or_starts_children(capsys):
    original = Path.open
    def restricted(path, *args, **kwargs):
        if path.name.startswith('internal_test'):
            raise AssertionError('Plan opened held-out labels/questions')
        return original(path, *args, **kwargs)
    with patch.object(Path, 'open', restricted), patch('subprocess.Popen', side_effect=AssertionError('Child started')):
        assert pipeline.main(['--partition', 'test']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['n_questions'] == 1599
    assert not result['test_questions_opened'] and result['llm_calls_by_plan'] == 0
    assert result['nominal_judge_votes'] == 1599 * 2 * 3 * 3


def test_shared_context_rejects_changed_pair_identity(tmp_path, tiny_index):
    async def scenario():
        from minirag.base import QueryParam
        import minirag.operate as operate
        rag = fixture.rag_at(phased.snapshot(tmp_path / 'index', tiny_index), fixture.QueryLLM())
        kw = tmp_path / 'kw.jsonl'
        phased.apply_env('C0', 101, kw_cache=kw)
        await phased.keyword_phase(rag, fixture.ROWS, kw)
        adapter = SharedContext(operate)
        with adapter.installed():
            phased.apply_env('C0', 101, kw_cache=kw, cache_only=True)
            await rag.aquery(fixture.ROWS[0]['Question'], param=QueryParam(mode='mini', only_need_context=True))
            phased.apply_env('C1', 202, kw_cache=kw, cache_only=True)
            with pytest.raises(RuntimeError, match='Inputs changed'):
                await rag.aquery(fixture.ROWS[0]['Question'], param=QueryParam(mode='mini', only_need_context=True))
    with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
        asyncio.run(scenario())


def test_consumer_pair_order_aliases_and_resume(tmp_path):
    split = tmp_path / 'split'
    split.mkdir()
    questions, gold = split / 'internal_dev.csv', split / 'internal_dev_gold.jsonl'
    with questions.open('w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['query_id', 'Question', 'Gold Answer', 'Type'])
        w.writerow(['one', 'Synthetic?', 'A', 'comparison'])
    gold.write_text(json.dumps({'query_id': 'one', 'answer': 'A', 'aliases': ['A', 'Alias']})+'\n', encoding='utf-8')
    manifest = {'seeds': [101, 202], 'configs': ['C0', 'C1'], 'partition': 'dev',
                'questions_sha256': common.sha(questions), 'gold_sha256': common.sha(gold),
                'judge_model': 'gemini-fixture', 'source_hashes': common.source_hashes(ROOT)}
    common.write_json(tmp_path / 'RUN_MANIFEST.json', manifest)
    for seed in manifest['seeds']:
        ready = {'questions_sha256': common.sha(questions), 'answers': {}}
        for c in manifest['configs']:
            path = tmp_path / 'qa' / f's{seed}' / f'{c}_s{seed}' / 'answers.jsonl'
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({'query_id': 'one', 'answer': f'Alias {seed} {c}'})+'\n', encoding='utf-8')
            ready['answers'][c] = common.sha(path)
        common.write_json(tmp_path / f'READY_s{seed}.json', ready)
    calls = []
    async def request(model, prompt):
        assert model == 'gemini-fixture' and 'accepted_aliases' in prompt
        calls.append(prompt)
        return 'accurate'
    with patch.object(judge_worker, 'SPLIT', split), contextlib.redirect_stdout(io.StringIO()):
        asyncio.run(judge_worker.consume(tmp_path, request=request))
        assert len(calls) == 12
        for i, (seed, c) in enumerate((s, c) for s in manifest['seeds'] for c in manifest['configs']):
            assert all(f'Alias {seed} {c}' in p for p in calls[i*3:(i+1)*3])
        asyncio.run(judge_worker.consume(tmp_path, request=request))
        assert len(calls) == 12


def test_unreconciled_gpu_budget_never_starts_child(tmp_path):
    budget = tmp_path / 'budget.json'
    common.write_json(budget, {'consumed_s': 10, 'active': {'stage': 'interrupted'}})
    with patch('subprocess.Popen', side_effect=AssertionError('Started child')):
        with pytest.raises(ValueError, match='no end marker'):
            pipeline.gpu_child(['unused'], tmp_path / 'log', budget, 'next', 100)


def test_worker_checkpoint_export_and_input_drift(tmp_path, tiny_index):
    from reproduce.research.two_wiki_acceleration import shared_context
    from reproduce.research.two_wiki_acceleration.validate import write_questions
    async def scenario():
        index = phased.snapshot(tmp_path / 'source-index', tiny_index)
        files = {p.name: common.sha(p) for p in index.iterdir() if p.suffix in ('.json', '.graphml')}
        common.write_json(index / 'index_manifest.json', {'status': 'completed', 'file_sha256': files})
        rag = fixture.rag_at(index, fixture.QueryLLM())
        kw, questions = tmp_path / 'kw.jsonl', tmp_path / 'questions.csv'
        phased.apply_env('C0', 101, kw_cache=kw)
        await phased.keyword_phase(rag, fixture.ROWS, kw)
        write_questions(questions, fixture.ROWS)
        args = SimpleNamespace(repo=ROOT, questions=questions, kw=kw, index=index,
                               out=tmp_path / 'worker', seed=101, reference=None)
        def offline(phased, snapshot):
            return fixture.rag_at(snapshot, shared_context.forbidden)
        with patch.object(shared_context, 'build_offline', offline):
            await shared_context.worker(args)
            assert common.read_json(args.out / 'STATUS.json')['status'] == 'completed'
            before = (args.out / 'pairs.jsonl').read_bytes()
            await shared_context.worker(args)
            assert (args.out / 'pairs.jsonl').read_bytes() == before
            assert set(common.read_jsonl(args.out / 'C0_s101/contexts.jsonl')) == {r['query_id'] for r in fixture.ROWS}
            args.seed = 202
            with pytest.raises(ValueError, match='hashes changed'):
                await shared_context.worker(args)
    with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
        asyncio.run(scenario())


def test_completed_validation_with_source_drift_is_rejected(tmp_path):
    path = tmp_path / 'validation.json'
    n = common.read_json(common.SPLIT / 'split_manifest.json')['counts']['internal_dev_count']
    common.write_json(path, {'status': 'verified', 'validation_scope': 'all_2wiki_dev',
                            'completed_queries': n, 'total_queries': n, 'logical_answer_contexts': n*2,
                            'mismatches': [], 'llm_calls': 0,
                            'identity': {'source_hashes': {'old': 'hash'}, 'runtime': common.runtime_identity()}})
    with pytest.raises(ValueError, match='Source/runtime changed'):
        pipeline.verify_validation(path, tmp_path / 'index')
