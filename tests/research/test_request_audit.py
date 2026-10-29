"""Offline audit contracts: concurrent query attribution, retries and payloads."""
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reproduce/research"))
import llm_trace
import phased_qa as pq
import index_run as ir


def response(text):
    return SimpleNamespace(model="qwen-fixture", usage=None,
                           choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=text))])


def test_concurrent_retries_preserve_query_ids_and_raw_messages():
    records = []
    calls = {}

    async def create(**kwargs):
        q = kwargs["messages"][0]["content"]
        calls[q] = calls.get(q, 0) + 1
        await asyncio.sleep(0)
        if q == "first" and calls[q] == 1:
            raise RuntimeError("never-log-exception-secret")
        return response(q)

    wrapped = llm_trace._wrap_create(create)

    async def one(q):
        with llm_trace.request_context(query_id=q, phase="answer"):
            for _ in range(2):
                try:
                    await wrapped(model="qwen", messages=[{"role": "user", "content": q}],
                                  max_tokens=1024, seed=101, temperature=0.7,
                                  api_key="never-log-key", extra_headers={"Authorization": "never-log-header"})
                    return
                except RuntimeError:
                    pass

    async def go():
        with llm_trace.trace(records.append):
            await asyncio.gather(one("first"), one("second"))

    asyncio.run(go())
    first = [r for r in records if r["query_id"] == "first"]
    second = [r for r in records if r["query_id"] == "second"]
    assert [r["attempt"] for r in first] == [1, 2]
    assert first[0]["request_id"] == first[1]["request_id"] != second[0]["request_id"]
    assert [r["ok"] for r in first] == [False, True]
    for r in records:
        assert r["request"]["messages"] == [{"role": "user", "content": r["query_id"]}]
        assert r["request"]["temperature"] == 0.7
        assert r["phase"] == "answer"
    assert "never-log" not in json.dumps(records)


def test_cancelled_http_attempt_is_preserved():
    records = []

    async def cancelled(**kwargs):
        raise asyncio.CancelledError()

    async def go():
        with llm_trace.trace(records.append), llm_trace.request_context(query_id="q", phase="kw_parse"):
            with pytest.raises(asyncio.CancelledError):
                await llm_trace._wrap_create(cancelled)(messages=[{"role": "user", "content": "parse"}])

    asyncio.run(go())
    assert records[0]["error_type"] == "CancelledError"
    assert records[0]["query_id"] == "q"


def test_complete_provider_response_is_serialized():
    from openai.types.chat import ChatCompletion
    raw = {"id": "response-fixture", "created": 0, "object": "chat.completion", "model": "qwen",
           "choices": [{"index": 0, "finish_reason": "length",
                        "message": {"role": "assistant", "content": "raw text"}}],
           "usage": {"prompt_tokens": 4, "completion_tokens": 5, "total_tokens": 9}}
    records = []

    async def create(**kwargs):
        return ChatCompletion.model_validate(raw)

    async def go():
        with llm_trace.trace(records.append):
            await llm_trace._wrap_create(create)(messages=[{"role": "user", "content": "question"}])

    asyncio.run(go())
    assert records[0]["response"]["id"] == "response-fixture"
    assert records[0]["response"]["choices"][0]["message"]["content"] == "raw text"
    assert records[0]["response"]["usage"]["total_tokens"] == 9
    assert records[0]["finish_reason"] == "length"
    json.dumps(records)


def test_index_retry_has_raw_input_chunk_and_doc_identity():
    records = []
    annotate = ir.annotator({"chunk-one": ("doc-one", "body")},
                            [{"minirag_doc_id": "doc-one", "doc_id": "title"}])

    async def create(**kwargs):
        return response("raw extraction")

    async def go():
        with llm_trace.trace(records.append, annotate):
            for _ in range(2):
                await llm_trace._wrap_create(create)(messages=[{"role": "user", "content": "extract body"}])

    asyncio.run(go())
    assert [r["attempt"] for r in records] == [1, 2]
    assert records[0]["request_id"] == records[1]["request_id"]
    assert records[0]["doc_id"] == "title"
    assert records[0]["minirag_doc_id"] == "doc-one"
    assert records[0]["chunk_id"] == "chunk-one"
    assert records[0]["response_text"] == "raw extraction"
    with pytest.raises(ValueError, match="attribute"):
        annotate([{"role": "user", "content": "unknown input"}])


def test_phased_sink_retains_raw_answer_context_and_keyword_ids(tmp_path):
    rows = [{"query_id": q, "Question": "Same question?", "Gold Answer": "gold"} for q in ("qa", "qb")]

    async def create(**kwargs):
        return response("raw answer")

    wrapped = llm_trace._wrap_create(create)

    async def llm(prompt, system_prompt=None):
        messages = ([{"role": "system", "content": system_prompt}] if system_prompt else [])
        messages.append({"role": "user", "content": prompt})
        return (await wrapped(model="qwen", messages=messages, max_tokens=1024, seed=101)).choices[0].message.content

    async def get_types():
        return ["ORGANIZATION"], None

    rag = SimpleNamespace(llm_model_func=llm, chunk_entity_relation_graph=SimpleNamespace(get_types=get_types))
    contexts = {r["query_id"]: {"status": "ok", "context": "retrieved context " + r["query_id"]} for r in rows}

    async def phases():
        await pq.keyword_phase(rag, rows, tmp_path / "kw.jsonl")
        await pq.answer_phase(llm, rows, contexts, "mini", tmp_path / "answers.jsonl", "short answer")

    with patch.object(llm_trace, "install"):
        pq.traced(tmp_path, phases)
    records = [json.loads(line) for line in (tmp_path / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {(r["query_id"], r["phase"]) for r in records} == {
        (q, phase) for q in ("qa", "qb") for phase in ("kw_parse", "answer")}
    for r in records:
        assert r["response_text"] == "raw answer"
        if r["phase"] == "answer":
            assert "retrieved context " + r["query_id"] in r["request"]["messages"][0]["content"]
