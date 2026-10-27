"""Check the Qwen SLM endpoint before a paid run: alive, right model, right vLLM.

Makes three requests to MINIRAG_SLM_URL with MINIRAG_SLM_KEY (from .env or
the shell): GET /version, GET /v1/models, and one short chat completion. The
first request may wait several minutes while Modal starts the GPU, and the GPU
then stays up for SCALEDOWN seconds (modal_slm.py), so this costs a few cents.

It compares what the server reports with serving_qwen_modal.json and writes
the observation to --out. The key and URL are never printed or written.

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


async def probe(expected, timeout):
    import httpx
    from openai import AsyncOpenAI

    root = os.environ["MINIRAG_SLM_URL"].strip().rstrip("/").removesuffix("/v1")
    headers = {"Authorization": f"Bearer {os.environ['MINIRAG_SLM_KEY'].strip()}"}
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
                                 and {expected["model"], "minirag-slm"} <= set(out["served_models"]),
        "completion_ok": bool(resp.choices[0].message.content),
    }
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--serving", type=Path, default=Path(__file__).with_name("serving_qwen_modal.json"))
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--timeout", type=float, default=900.0, help="Seconds; covers a cold GPU start")
    args = p.parse_args(argv)
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    if not os.environ.get("MINIRAG_SLM_URL", "").strip() or not os.environ.get("MINIRAG_SLM_KEY", "").strip():
        print("MINIRAG_SLM_URL and MINIRAG_SLM_KEY must be set (in .env or the shell)")
        return 2
    result = asyncio.run(probe(json.loads(args.serving.read_text(encoding="utf-8")), args.timeout))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if all(result["checks"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
