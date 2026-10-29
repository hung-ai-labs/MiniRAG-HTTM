"""Per-HTTP-request payloads and metadata for minirag/llm/gemini.py.

gemini_complete_if_cache returns only the reply text, so response.model,
finish_reason and token usage are lost -- yet they are what tells a truncated
extraction (finish_reason "length") or a silently swapped model apart from a
normal reply. This wraps the OpenAI client inside the running process instead
of editing minirag/, which other experiments depend on byte for byte.

Every HTTP attempt (including the backend's own tenacity retries) is passed to
the sink in the current context, if any, with the reply text:

    with trace(records.append):
        text = await gemini_complete_if_cache(model, prompt)

The allowlisted provider payload includes messages; credentials, transport
headers, endpoint URLs and exception text are never copied. Request content
may itself contain document URLs. Keep these artifacts in ignored run/index
directories, not in public source commits.
"""

from contextlib import contextmanager
import copy
import contextvars
import hashlib
import json
import time
import uuid

_SINK = contextvars.ContextVar("llm_trace_sink", default=None)
_REQUEST = contextvars.ContextVar("llm_trace_request", default=None)
REQUEST_FIELDS = ("model", "messages", "max_tokens", "max_completion_tokens", "seed", "temperature",
                  "top_p", "n", "stop", "presence_penalty", "frequency_penalty", "response_format")


@contextmanager
def request_context(*, query_id, phase):
    """Bind retries to one logical query call, isolated between asyncio tasks."""
    token = _REQUEST.set({"metadata": {"query_id": query_id, "phase": phase},
                          "request_id": uuid.uuid4().hex, "attempt": 0})
    try:
        yield
    finally:
        _REQUEST.reset(token)


def _wrap_create(create):
    async def traced_create(*args, **kwargs):
        scope = _SINK.get()
        sink, annotate = (scope["sink"], scope["annotate"]) if scope else (None, None)
        started = time.perf_counter()
        record = {"request_model": kwargs.get("model"), "max_tokens": kwargs.get("max_tokens"),
                  "seed": kwargs.get("seed"),
                  "prompt_sha256": hashlib.sha256(repr(kwargs.get("messages")).encode()).hexdigest()}
        if sink and annotate:
            record |= annotate(kwargs.get("messages") or [])
        if sink:
            # Allowlist provider payload fields. Never copy client options, headers,
            # credentials, URLs or arbitrary extra_body/extra_headers into artifacts.
            record["request"] = copy.deepcopy({k: kwargs[k] for k in REQUEST_FIELDS if k in kwargs})
            record["request_sha256"] = hashlib.sha256(json.dumps(
                record["request"], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            logical = _REQUEST.get()
            if logical is not None:
                record |= logical["metadata"]
            else:
                key = (record["request_sha256"], record.get("phase"), record.get("chunk_id"))
                logical = scope["requests"].setdefault(key, {"request_id": uuid.uuid4().hex, "attempt": 0})
            logical["attempt"] += 1
            record |= {"trace_schema": 2, "request_id": logical["request_id"], "attempt": logical["attempt"]}
        try:
            response = await create(*args, **kwargs)
        except BaseException as exc:
            if sink:
                sink(record | {"ok": False, "error_type": type(exc).__name__,
                               "latency_s": round(time.perf_counter() - started, 3)})
            raise
        if sink:
            choice = (getattr(response, "choices", None) or [None])[0]
            usage = getattr(response, "usage", None)
            sink(record | {
                "ok": True, "latency_s": round(time.perf_counter() - started, 3),
                "response_model": getattr(response, "model", None),
                "finish_reason": getattr(choice, "finish_reason", None),
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "response_text": getattr(getattr(choice, "message", None), "content", None),
                "response": response.model_dump(mode="json") if callable(getattr(response, "model_dump", None)) else None,
            })
        return response

    traced_create._llm_traced = True
    return traced_create


def install():
    """Idempotently route every client made by minirag.llm.gemini through the tracer."""
    from minirag.llm import gemini

    if getattr(gemini._client, "_llm_traced", False):
        return
    original = gemini._client

    def traced_client(*args, **kwargs):
        client = original(*args, **kwargs)
        completions = client.chat.completions
        if not getattr(completions.create, "_llm_traced", False):
            completions.create = _wrap_create(completions.create)
        return client

    traced_client._llm_traced = True
    gemini._client = traced_client


@contextmanager
def trace(sink, annotate=None):
    """annotate(messages) -> dict of extra fields, e.g. which chunk a prompt is about."""
    token = _SINK.set({"sink": sink, "annotate": annotate, "requests": {}})
    try:
        yield
    finally:
        _SINK.reset(token)
