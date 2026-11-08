"""Time limiting must preserve committed batches and cancel uncommitted work."""
import argparse
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'reproduce/research'))
import index_run as ir

spec = importlib.util.spec_from_file_location('budget_index_fixture', ROOT / 'tests/research/test_index_run.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def test_expired_budget_never_constructs_backend(tmp_path):
    workdir = tmp_path / 'index'
    args = argparse.Namespace(workingdir=workdir, resume=False, batch_docs=1,
                              max_runtime_seconds=1, runtime_deadline=time.monotonic()-1)
    chunks = ir.chunk_map(fixture.DOCS, ir.index_settings())
    def forbidden(path):
        raise AssertionError('Constructed a backend after deadline')
    assert asyncio.run(ir.run_index(args, fixture.DOCS, forbidden, fixture.identity(chunks), chunks)) == 3
    assert json.loads((workdir / 'index_manifest.json').read_text())['stop_reason'] == 'time_limit'
    assert not (workdir / 'index_progress.jsonl').exists()


def test_mid_batch_timeout_is_partial_and_resume_skips_committed_docs(tmp_path):
    workdir = tmp_path / 'index'
    chunks = ir.chunk_map(fixture.DOCS, ir.index_settings())
    args = argparse.Namespace(workingdir=workdir, resume=False, batch_docs=1, max_runtime_seconds=1)
    ident = fixture.identity(chunks)
    llm = fixture.FakeLLM()
    state = {'cancelled': False}
    def slow_factory(path):
        rag = fixture.factory(llm)(path)
        real = rag.ainsert
        count = 0
        async def insert(texts):
            nonlocal count
            count += 1
            if count == 2:
                # Set a short deterministic deadline only after batch A commits.
                try:
                    await asyncio.sleep(60)
                except asyncio.CancelledError:
                    state['cancelled'] = True
                    raise
            await real(texts)
        rag.ainsert = insert
        return rag
    # The test controls timeout durations, not the event loop's monotonic clock.
    real_timeout = asyncio.timeout
    n = []
    def timer(seconds):
        n.append(seconds)
        return real_timeout(30 if len(n) == 1 else .01)
    # A large deadline lets initial fixture imports complete on slow machines.
    args.max_runtime_seconds = 300
    with patch.object(ir.asyncio, 'timeout', timer):
        assert asyncio.run(ir.run_index(args, fixture.DOCS, slow_factory, ident, chunks)) == 3
    assert state['cancelled']
    progress = ir.read_jsonl(workdir / 'index_progress.jsonl')
    assert len(progress) == 1 and progress[0]['doc_ids'] == [fixture.DOCS[0]['doc_id']]
    args.resume, args.max_runtime_seconds = True, None
    resumed = fixture.FakeLLM()
    assert asyncio.run(ir.run_index(args, fixture.DOCS, fixture.factory(resumed), ident, chunks)) == 0
    assert resumed.extracted == ['B', 'C']
    assert json.loads((workdir / 'index_manifest.json').read_text())['status'] == 'completed'


def test_non_budget_timeout_remains_a_failure(tmp_path):
    chunks = ir.chunk_map(fixture.DOCS, ir.index_settings())
    args = argparse.Namespace(workingdir=tmp_path / 'index', resume=False,
                              batch_docs=1, max_runtime_seconds=300)
    class Broken:
        async def ainsert(self, texts):
            raise TimeoutError('provider timeout')
    with pytest.raises(TimeoutError, match='provider timeout'):
        asyncio.run(ir.run_index(args, fixture.DOCS, lambda p: Broken(), fixture.identity(chunks), chunks))
    events = ir.read_jsonl(args.workingdir / 'events.jsonl')
    assert events[-1]['event'] == 'failed'
