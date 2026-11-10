"""Gate G1b of the LiHua MiniCPM ablation (LIHUA_ABLATION_MINICPM.md): long prompts, alone and in mixed batches.

Why this exists: Phi-3.5 passed G1 with one short prompt, then failed the pilot index because vLLM 0.11 switches
LongRoPE factors for the whole batch once any sequence passes position 4,096 (LIHUA_ABLATION_PHI.md, 03/11/2026).
This gate sends prompts that cross that range and checks that the answers do not depend on batching.

Prompts, all built from dataset/LiHua-World/processed/docs.jsonl and identical on every run:
  needle   8 answer prompts (phased_qa.answer_messages, the pipeline's own) of 3k/4k/5k/8k tokens, a synthetic line
           with a 4-digit code at 15% or 85% of the context; lengths fitted with the server's POST /tokenize
  extract  4 entity-extraction prompts on real LiHua chunks, built as operate.py builds them
  probe    4 short answer prompts (one message of context)
Runs: alone and alone_repeat (sequential, temperature 0), mixed_1 and mixed_2 (every prompt twice, concurrently,
temperature 0), registered (every prompt once, concurrently, the served sampling). max_tokens 1024, seed 101.

Talks to MINIRAG_SLM_URL with MINIRAG_SLM_KEY; neither is printed or written. Exit 0 only when every check holds.

    python reproduce/research/compat_gate.py --serving reproduce/research/serving_minicpm_modal.json \\
        --out runs/lihua_world/ablation_minicpm/compat_gate.json
"""

import argparse
import asyncio
import collections
import difflib
import json
import os
from pathlib import Path
import random
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
DOCS = ROOT / "dataset/LiHua-World/processed/docs.jsonl"
TARGETS = (3000, 4000, 5000, 8000)
NEEDLE_AT = (0.15, 0.85)
TOLERANCE = 64          # a fitted needle prompt must have target..target+64 tokens
EXTRACT_CHUNKS = 4
PROBES = 4
MAX_TOKENS = 1024       # MINIRAG_MAX_TOKENS of every run
SEED = 101
T0_RUNS = ("alone", "alone_repeat", "mixed_1", "mixed_2")
RUNS = T0_RUNS + ("registered",)
PLACES = ("east wing pantry", "rooftop garden shed", "basement bike room", "studio prop closet",
          "library map cabinet", "harbour office locker", "community hall attic", "gym equipment cage",
          "bakery flour store", "music room drum case", "clinic supply shelf", "garage tool chest")

# Degenerate output, calibrated before registration on outputs already logged (no model calls): flags 24/24
# Phi pilot replies cut at 1,024 tokens and 0 of 18,264 Qwen v2 answers / requests.
REPEAT = re.compile(r"(.{1,8}?)\1{7,}", re.S)     # a unit of <= 8 chars repeated >= 8 times in a row
SYMBOLS = re.compile(r"[^\w\s]{16,}")             # >= 16 symbols in a row
WORD = re.compile(r"[A-Za-z']+")
DOMINANT_WINDOW, DOMINANT_MIN, DOMINANT_SHARE = 200, 100, 0.25


def looks_degenerate(text):
    """Reasons the text looks like broken decoding; empty when it looks like language."""
    text = text or ""
    reasons = []
    if m := REPEAT.search(text):
        reasons.append(f"repeat:{m.group(1)!r}")
    if SYMBOLS.search(text):
        reasons.append("symbol_run")
    if "�" in text:
        reasons.append("replacement_char")
    words = [w.lower() for w in WORD.findall(text)]
    for i in range(0, max(1, len(words) - DOMINANT_WINDOW + 1), 50):
        window = words[i:i + DOMINANT_WINDOW]
        if len(window) < DOMINANT_MIN:
            break
        word, n = collections.Counter(window).most_common(1)[0]
        if n / len(window) >= DOMINANT_SHARE:
            reasons.append(f"dominant_word:{word}")
            break
    return reasons


def extraction_problems(text, finish_reason):
    """Format check of an entity-extraction reply, with the delimiters and record regex of operate.py."""
    from minirag.prompt import PROMPTS
    from minirag.utils import split_string_by_multi_markers

    text = text or ""
    tup, rec, done = (PROMPTS[k] for k in ("DEFAULT_TUPLE_DELIMITER", "DEFAULT_RECORD_DELIMITER",
                                            "DEFAULT_COMPLETION_DELIMITER"))
    records = split_string_by_multi_markers(text, [rec, done])
    if finish_reason == "length" and records:
        records = records[:-1]  # the record being written when the cap hit
    problems, entities = [], 0
    for record in records:
        m = re.search(r"\((.*)\)", record)
        kind = split_string_by_multi_markers(m.group(1), [tup])[0] if m else None
        if kind not in ('"entity"', '"relationship"', '"content_keywords"'):
            problems.append(f"unparsed_record:{record[:40]!r}")
        entities += kind == '"entity"'
    if not entities:
        problems.append("no_entity")
    if finish_reason == "stop" and done not in text:
        problems.append("no_completion_delimiter")
    return problems


def needles(n):
    codes = random.Random(13).sample(range(1000, 10000), n)
    return [{"line": f"Notice: the storage locker code for the {PLACES[i]} is {codes[i]}.",
             "question": f"What is the storage locker code for the {PLACES[i]}?", "code": str(codes[i])}
            for i in range(n)]


def sources(texts, needle_line, at):
    """A Sources table like the pipeline's, the needle on its own line at the first line break past fraction `at`."""
    body = "\n".join(f"{i},\t{t}" for i, t in enumerate(texts))
    cut = body.find("\n", int(at * len(body)))
    body = body + "\n" + needle_line if cut < 0 else body[:cut] + "\n" + needle_line + body[cut:]
    return f"-----Sources-----\n```csv\nid,\tcontent\n{body}\n```"


def answer_prompt(texts, needle, at):
    import phased_qa
    from minirag.base import QueryParam

    prompt, system = phased_qa.answer_messages("mini", needle["question"], sources(texts, needle["line"], at),
                                               QueryParam().response_type)
    return [{"role": "system", "content": system}, {"role": "user", "content": prompt}]


def fit_to_length(build, count, target, tolerance=TOLERANCE, limit=None):
    """Smallest prefix (in characters) whose messages reach `target` tokens: (messages, tokens).

    build(chars) -> messages; count(messages) -> tokens. Raises when the corpus is too short or the fit overshoots.
    """
    # Gallop to an upper bound first: one count of the whole corpus (~286k Phi tokens) took 80 s on the server and the
    # next request timed out (07/11/2026). For a count that grows with the prefix the bisection below still returns
    # the same smallest prefix as a search over [1, limit].
    lo, hi = 1, min(limit, max(1, 8 * target))
    while count(build(hi)) < target:
        if hi >= limit:
            raise ValueError(f"corpus too short for {target} tokens")
        lo, hi = hi + 1, min(limit, 2 * hi)
    while lo < hi:
        mid = (lo + hi) // 2
        if count(build(mid)) >= target:
            hi = mid
        else:
            lo = mid + 1
    messages = build(lo)
    tokens = count(messages)
    if not target <= tokens <= target + tolerance:
        raise ValueError(f"fitted {tokens} tokens for target {target}")
    return messages, tokens


def read_docs(path=DOCS):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def build_prompts(docs, count):
    """The 16 gate prompts; count(messages) is the server's token count."""
    import index_run
    from minirag.prompt import PROMPTS

    texts = [d["text"] for d in docs]
    joined_limit = sum(len(t) for t in texts)
    marks = needles(len(TARGETS) * len(NEEDLE_AT) + PROBES)
    prompts = []
    for k, (target, at) in enumerate((t, a) for t in TARGETS for a in NEEDLE_AT):
        start = k * len(texts) // (len(TARGETS) * len(NEEDLE_AT))  # a different stretch of the corpus each
        pool = texts[start:] + texts[:start]

        def build(chars, pool=pool, needle=marks[k], at=at):
            kept, used = [], 0
            for t in pool:
                if used >= chars:
                    break
                kept.append(t[:chars - used])
                used += len(kept[-1])
            return answer_prompt(kept, needle, at)

        messages, tokens = fit_to_length(build, count, target, limit=joined_limit)
        system = messages[0]["content"]
        prompts.append({"id": f"needle_{target}_{int(at * 100)}", "kind": "needle", "target": target,
                        "needle_at": at, "needle_char_share": round(system.find(marks[k]["line"]) / len(system), 3),
                        "expect": marks[k]["code"], "messages": messages, "tokenized": tokens})
    chunks = index_run.chunk_map(docs, index_run.index_settings())
    base = {"tuple_delimiter": PROMPTS["DEFAULT_TUPLE_DELIMITER"],
            "record_delimiter": PROMPTS["DEFAULT_RECORD_DELIMITER"],
            "completion_delimiter": PROMPTS["DEFAULT_COMPLETION_DELIMITER"],
            "entity_types": ",".join(PROMPTS["DEFAULT_ENTITY_TYPES"])}
    for chunk_id in sorted(chunks)[:EXTRACT_CHUNKS]:
        messages = [{"role": "user", "content": PROMPTS["entity_extraction"].format(
            **base, input_text=chunks[chunk_id][1])}]
        prompts.append({"id": f"extract_{chunk_id}", "kind": "extract", "target": None, "messages": messages,
                        "tokenized": count(messages)})
    for j in range(PROBES):
        needle = marks[len(TARGETS) * len(NEEDLE_AT) + j]
        messages = answer_prompt([texts[j * 97 % len(texts)]], needle, 0.5)
        prompts.append({"id": f"probe_{j}", "kind": "probe", "target": None, "expect": needle["code"],
                        "messages": messages, "tokenized": count(messages)})
    return prompts


def response_problems(prompt, resp, expected_model, max_model_len):
    """Conditions 1-5 of the registration for one reply."""
    if not resp.get("ok"):
        return [f"error:{resp.get('error_type')}"]
    problems = []
    if resp.get("prompt_tokens") != prompt["tokenized"]:
        problems.append(f"prompt_tokens {resp.get('prompt_tokens')} != tokenize {prompt['tokenized']}")
    if prompt["target"] is not None and not prompt["target"] <= prompt["tokenized"] <= prompt["target"] + TOLERANCE:
        problems.append("prompt_off_target")
    if prompt["tokenized"] + MAX_TOKENS > max_model_len:
        problems.append("prompt_plus_max_tokens_over_window")
    if resp.get("response_model") != expected_model:
        problems.append(f"response_model:{resp.get('response_model')}")
    text = resp.get("text") or ""
    if prompt["kind"] == "extract":
        problems += extraction_problems(text, resp.get("finish_reason"))
    else:
        if resp.get("finish_reason") != "stop":
            problems.append(f"finish_reason:{resp.get('finish_reason')}")
        if prompt["expect"] not in text:
            problems.append("needle_missing")
    problems += [f"degenerate:{r}" for r in looks_degenerate(text)]
    return problems


def evaluate(prompts, responses, served, serving):
    """Verdict of the gate from the prompts, every reply (dicts with run/prompt_id/copy) and GET /v1/models."""
    by_id = {p["id"]: p for p in prompts}
    expected = {(run, p["id"], c) for p in prompts for run in RUNS
                for c in range(2 if run.startswith("mixed") else 1)}
    got = {(r["run"], r["prompt_id"], r["copy"]): r for r in responses}
    checked = []
    for key in sorted(expected & set(got)):
        r = got[key]
        checked.append({"run": key[0], "prompt_id": key[1], "copy": key[2],
                        "problems": response_problems(by_id[key[1]], r, serving["model"], served["max_model_len"])})
    failed = [c for c in checked if c["problems"]]
    kinds = collections.Counter(p.split(":")[0].split(" ")[0] for c in failed for p in c["problems"])
    verdicts = collections.defaultdict(set)
    for c in checked:
        verdicts[c["prompt_id"]].add(not c["problems"])
    t0 = collections.defaultdict(list)
    for (run, pid, _), r in sorted(got.items()):
        if run in T0_RUNS and r.get("ok"):
            t0[pid].append(r.get("text") or "")
    similarity = {pid: {"exact_match_share": round(sum(t == texts[0] for t in texts) / len(texts), 3),
                        "min_ratio_to_alone": round(min(difflib.SequenceMatcher(None, texts[0], t).ratio()
                                                        for t in texts), 3)}
                  for pid, texts in t0.items()}

    def none_of(*prefixes):
        return not any(k.startswith(prefixes) for k in kinds)

    gate = {
        "all_responses_received": expected <= set(got),
        "served_window_matches": served["max_model_len"] == serving["max_model_len"],
        "context_length_ok": none_of("prompt_tokens", "prompt_off_target", "prompt_plus_max_tokens_over_window"),
        "only_expected_model": none_of("response_model"),
        "finish_ok": none_of("finish_reason", "error"),
        "answers_ok": none_of("needle_missing"),
        "extraction_format_ok": none_of("unparsed_record", "no_entity", "no_completion_delimiter"),
        "no_degenerate_output": none_of("degenerate"),
        "stable_across_runs": all(v == {True} for v in verdicts.values()) and set(verdicts) == set(by_id),
    }
    return {"gate": gate, "failed": failed, "problem_counts": dict(kinds), "similarity_t0": similarity,
            "prompt_tokens": {p["id"]: p["tokenized"] for p in prompts}}


async def collect(prompts):
    from openai import AsyncOpenAI
    import slm_smoke

    root, _ = slm_smoke.endpoint()
    client = AsyncOpenAI(api_key=os.environ["MINIRAG_SLM_KEY"].strip(), base_url=f"{root}/v1", timeout=900.0,
                         max_retries=0)

    async def ask(run, prompt, copy):
        kwargs = {} if run == "registered" else {"temperature": 0}
        out = {"run": run, "prompt_id": prompt["id"], "copy": copy}
        try:
            resp = await client.chat.completions.create(model="minirag-slm", messages=prompt["messages"],
                                                        max_tokens=MAX_TOKENS, seed=SEED, **kwargs)
        except Exception as exc:
            return out | {"ok": False, "error_type": type(exc).__name__}
        choice = resp.choices[0]
        return out | {"ok": True, "response_model": resp.model, "finish_reason": choice.finish_reason,
                      "prompt_tokens": resp.usage.prompt_tokens, "completion_tokens": resp.usage.completion_tokens,
                      "text": choice.message.content}

    responses = []
    for run in ("alone", "alone_repeat"):
        for p in prompts:
            responses.append(await ask(run, p, 0))
    for run in ("mixed_1", "mixed_2"):
        responses += await asyncio.gather(*(ask(run, p, c) for c in range(2) for p in prompts))
    responses += await asyncio.gather(*(ask("registered", p, 0) for p in prompts))
    return responses


def server_counter():
    import httpx
    import slm_smoke

    root, headers = slm_smoke.endpoint()
    http = httpx.Client(timeout=900.0, headers=headers)

    def count(messages):
        r = http.post(f"{root}/tokenize", json={"model": "minirag-slm", "messages": messages,
                                                  "add_generation_prompt": True})
        r.raise_for_status()
        return r.json()["count"]

    models = http.get(f"{root}/v1/models")
    models.raise_for_status()
    alias = next(m for m in models.json()["data"] if m["id"] == "minirag-slm")
    return count, {"models": sorted(m["id"] for m in models.json()["data"]), "max_model_len": alias["max_model_len"]}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--serving", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)
    sys.path.insert(0, str(ROOT))
    from dotenv import load_dotenv
    import slm_smoke

    load_dotenv(ROOT / ".env")
    serving = json.loads(args.serving.read_text(encoding="utf-8"))
    slm_smoke.require_model(serving)
    count, served = server_counter()
    prompts = build_prompts(read_docs(), count)
    responses = asyncio.run(collect(prompts))
    result = {"serving": args.serving.as_posix(), "model": serving["model"], "served": served,
              **evaluate(prompts, responses, served, serving), "responses": responses}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("gate", "problem_counts", "prompt_tokens")}, indent=2))
    return 0 if all(result["gate"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
