"""Check the SLM endpoint before a paid run: alive, right model, right vLLM.

Makes three requests to MINIRAG_SLM_URL with MINIRAG_SLM_KEY (from .env or
the shell): GET /version, GET /v1/models, and one short chat completion. The
first request may wait several minutes while Modal starts the GPU, and the GPU
then stays up for SCALEDOWN seconds (modal_slm.py), so this costs a few cents.

It compares what the server reports with --serving (default serving_qwen_modal.json)
and writes the observation to --out. The key and URL are never printed or written.

--longrope adds a descriptive check for Phi-3.5 (LongRoPE switches rotary factors
past 4,096 positions): one short prompt at temperature 0 alone, then the same prompt
sent together with a prompt longer than 4,096 tokens. Different replies mean the
batch's composition can change an answer; that is recorded, not a failed check.

    python reproduce/research/slm_smoke.py --out runs/multihop_rag/_serving/smoke.json
"""

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import qa_run  # noqa: E402


def endpoint():
    """(root URL without /v1, auth headers) from MINIRAG_SLM_URL / MINIRAG_SLM_KEY."""
    root = os.environ["MINIRAG_SLM_URL"].strip().rstrip("/").removesuffix("/v1")
    return root, {"Authorization": f"Bearer {os.environ['MINIRAG_SLM_KEY'].strip()}"}


def served_models(timeout=900.0):
    """Model ids the endpoint serves (GET /v1/models); raises when the server does not answer 200."""
    import httpx

    root, headers = endpoint()
    r = httpx.get(f"{root}/v1/models", headers=headers, timeout=timeout)
    r.raise_for_status()
    return sorted(m["id"] for m in r.json().get("data", []))


def expected_names(serving):
    """Model ids the endpoint must serve: the model, the pipeline alias, and the serving file's own alias if any
    (the static-RoPE Phi app has one, so a run cannot land on the unpatched Phi app by a stale URL)."""
    return {serving["model"], "minirag-slm"} | ({serving["served_alias"]} if serving.get("served_alias") else set())


def require_model(serving, timeout=900.0):
    """Refuse to send work unless the endpoint serves the model the serving file names (and the alias)."""
    served = served_models(timeout)
    if not expected_names(serving) <= set(served):
        raise SystemExit(f"endpoint serves {served}, not {serving['model']}: wrong MINIRAG_SLM_URL?")
    return served


async def longrope_check(client):
    question = [{"role": "user", "content": "Name the capital of France in one word."}]
    filler = "The quick brown fox jumps over the lazy dog. " * 600  # ~6,000 tokens, past 4,096 positions
    long_prompt = [{"role": "user", "content": filler + "\nHow many times does the word fox appear? Reply briefly."}]

    async def ask(messages):
        resp = await client.chat.completions.create(model="minirag-slm", messages=messages, max_tokens=16,
                                                    temperature=0, seed=101)
        return resp.choices[0].message.content, getattr(resp.usage, "prompt_tokens", None)

    alone = [await ask(question) for _ in range(3)]
    mixed = await asyncio.gather(*([ask(question) for _ in range(3)] + [ask(long_prompt) for _ in range(3)]))
    replies_alone = sorted({r for r, _ in alone})
    replies_mixed = sorted({r for r, _ in mixed[:3]})
    return {"alone": replies_alone, "batched_with_long": replies_mixed,
            "long_prompt_tokens": mixed[3][1], "same_reply": replies_alone == replies_mixed}


async def probe(expected, timeout, longrope=False):
    import httpx
    from openai import AsyncOpenAI

    root, headers = endpoint()
    out = {"checked_at": qa_run.utc_now()}
    async with httpx.AsyncClient(timeout=timeout) as http:
        started = time.perf_counter()
        r = await http.get(f"{root}/version", headers=headers)
        out["first_response_s"] = round(time.perf_counter() - started, 1)  # includes any cold start
        out["vllm_version"] = r.json().get("version") if r.status_code == 200 else f"HTTP {r.status_code}"
        r = await http.get(f"{root}/v1/models", headers=headers)
        out["served_models"] = sorted(m["id"] for m in r.json().get("data", [])) if r.status_code == 200 \
            else f"HTTP {r.status_code}"
    client = AsyncOpenAI(api_key=os.environ["MINIRAG_SLM_KEY"].strip(), base_url=f"{root}/v1",
                         timeout=timeout, max_retries=0)
    started = time.perf_counter()
    resp = await client.chat.completions.create(
        model="minirag-slm", messages=[{"role": "user", "content": "Reply with exactly: ok"}],
        max_tokens=8, seed=101)
    out["completion"] = {"latency_s": round(time.perf_counter() - started, 2), "response_model": resp.model,
                         "finish_reason": resp.choices[0].finish_reason, "reply": resp.choices[0].message.content,
                         "completion_tokens": getattr(resp.usage, "completion_tokens", None)}
    out["checks"] = {
        "vllm_version_matches": out["vllm_version"] == expected["vllm_version"],
        "serves_expected_model": isinstance(out["served_models"], list)
                                 and expected_names(expected) <= set(out["served_models"]),
        "completion_ok": bool(resp.choices[0].message.content),
    }
    if longrope:
        out["longrope"] = await longrope_check(client)  # descriptive: not one of the checks
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--serving", type=Path, default=Path(__file__).with_name("serving_qwen_modal.json"))
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--timeout", type=float, default=900.0, help="Seconds; covers a cold GPU start")
    p.add_argument("--longrope", action="store_true", help="Also record the LongRoPE batching check (Phi-3.5)")
    args = p.parse_args(argv)
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    if not os.environ.get("MINIRAG_SLM_URL", "").strip() or not os.environ.get("MINIRAG_SLM_KEY", "").strip():
        print("MINIRAG_SLM_URL and MINIRAG_SLM_KEY must be set (in .env or the shell)")
        return 2
    result = asyncio.run(probe(json.loads(args.serving.read_text(encoding="utf-8")), args.timeout,
                             args.longrope))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if all(result["checks"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
