"""Per-HTTP-request metadata for runs that go through minirag/llm/gemini.py.

gemini_complete_if_cache returns only the reply text, so response.model,
finish_reason and token usage are lost -- yet they are what tells a truncated
extraction (finish_reason "length") or a silently swapped model apart from a
normal reply. This wraps the OpenAI client inside the running process instead
of editing minirag/, which other experiments depend on byte for byte.

Every HTTP attempt (including the backend's own tenacity retries) is passed to
the sink in the current context, if any, with the reply text:

    with trace(records.append):
        text = await gemini_complete_if_cache(model, prompt)

No API key, header or URL is ever recorded.
"""

from contextlib import contextmanager
import contextvars
import hashlib
import time

_SINK = contextvars.ContextVar("llm_trace_sink", default=None)


def _wrap_create(create):
    async def traced_create(*args, **kwargs):
        sink, annotate = _SINK.get() or (None, None)
        started = time.perf_counter()
        record = {"request_model": kwargs.get("model"), "max_tokens": kwargs.get("max_tokens"),
                  "seed": kwargs.get("seed"),
                  "prompt_sha256": hashlib.sha256(repr(kwargs.get("messages")).encode()).hexdigest()}
        if sink and annotate:
            record |= annotate(kwargs.get("messages") or [])
        try:
            response = await create(*args, **kwargs)
        except Exception as exc:
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
    token = _SINK.set((sink, annotate))
    try:
        yield
    finally:
        _SINK.reset(token)
