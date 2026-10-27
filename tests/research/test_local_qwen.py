"""Offline local-adapter tests: all HTTP calls mocked."""

import asyncio
import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(os.environ.get('MINIRAG_2WIKI_REPO', Path(__file__).resolve().parents[2]))
spec = importlib.util.spec_from_file_location('local_qwen', ROOT/'reproduce/research/local_qwen.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


@pytest.mark.parametrize('url', ['https://api.openai.com', 'http://localhost:11434',
                                'http://127.0.0.1:11434/v1', 'http://127.0.0.1:11434?token=x'])
def test_noncanonical_endpoint_rejected(tmp_path, url):
    with pytest.raises(ValueError):
        m.LocalQwen(tmp_path, base=url)


def test_wrong_model_digest_rejected_without_pull(tmp_path, monkeypatch):
    client = m.LocalQwen(tmp_path)
    monkeypatch.setattr(client, 'request', lambda endpoint, payload=None:
                        {'models': [{'name': m.MODEL, 'digest': 'wrong'}]} if endpoint == '/api/tags' else {})
    with pytest.raises(ValueError, match='digest'):
        client.inspect()


def test_full_request_response_are_logged(tmp_path, monkeypatch):
    client = m.LocalQwen(tmp_path)
    captured = []

    def fake(endpoint, payload):
        captured.append(payload)
        return {'model': m.MODEL, 'done': True, 'message': {'content': 'fixture'}, 'eval_count': 1}
    monkeypatch.setattr(client, 'request', fake)
    client.phase = 'index'
    client.chunk_id, client.doc_id = 'synthetic-chunk', 'synthetic-doc'
    assert asyncio.run(client.complete('fixture extraction')) == 'fixture'
    record = json.loads((tmp_path/'requests.jsonl').read_text(encoding='utf-8').strip())
    assert record['phase'] == 'extract' and record['status'] == 'ok'
    assert record['request']['options']['num_predict'] == 4096
    assert record['request']['options']['num_ctx'] == 32768
    assert record['response']['message']['content'] == 'fixture'
    assert record['chunk_id'] == 'synthetic-chunk'
    assert record['request']['messages'] == [{'role': 'user', 'content': 'fixture extraction'}]


def test_history_and_phase_caps_preserved(tmp_path, monkeypatch):
    client = m.LocalQwen(tmp_path)
    calls = []

    def fake(endpoint, payload):
        calls.append(payload)
        return {'model': m.MODEL, 'done': True, 'message': {'content': 'ok'}}
    monkeypatch.setattr(client, 'request', fake)
    history = [{'role': 'user', 'content': 'original'}, {'role': 'assistant', 'content': 'entities'}]
    client.phase = 'index'
    asyncio.run(client.complete('glean', history_messages=history))
    client.phase = 'answer'
    asyncio.run(client.complete('question', system_prompt='context'))
    records = [json.loads(x) for x in (tmp_path/'requests.jsonl').read_text().splitlines()]
    assert records[0]['phase'] == 'glean'
    assert calls[0]['messages'][:-1] == history and calls[0]['options']['num_predict'] == 4096
    assert calls[1]['options']['num_predict'] == 1024
    assert calls[1]['messages'][0] == {'role': 'system', 'content': 'context'}


def test_infra_failure_is_logged_and_propagated(tmp_path, monkeypatch):
    client = m.LocalQwen(tmp_path)

    def fake(endpoint, payload):
        raise TimeoutError('synthetic timeout')
    monkeypatch.setattr(client, 'request', fake)
    with pytest.raises(TimeoutError):
        client.chat([{'role': 'user', 'content': 'fixture'}], phase='answer', max_tokens=1024)
    record = json.loads((tmp_path/'requests.jsonl').read_text().strip())
    assert record['status'] == 'failed' and record['error_type'] == 'TimeoutError'
    assert 'response' not in record


def test_wrong_response_model_fails_closed(tmp_path, monkeypatch):
    client = m.LocalQwen(tmp_path)
    monkeypatch.setattr(client, 'request', lambda *args:
                        {'model': 'different-model', 'done': True, 'message': {'content': 'wrong'}})
    with pytest.raises(ValueError, match='model response'):
        client.chat([{'role': 'user', 'content': 'fixture'}], phase='answer', max_tokens=1024)
    assert json.loads((tmp_path/'requests.jsonl').read_text())['status'] == 'failed'
