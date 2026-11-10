"""MultiHop-RAG QA in three phases so the paid GPU never waits for CPU retrieval
(amendment S2, MULTIHOP_RAG_ROADMAP.md).

MiniRAG answers a `mini` query with two LLM calls around a CPU-only retrieval:
keyword extraction, then retrieval/context building (~20 s of CPU per question
on the 18.5k-node graph), then the answer call. Run as one process, the GPU
sits idle through the retrieval. Here the same three steps run as phases:

  A  keywords  (GPU)  the exact keyword prompt MiniRAG builds, sent through the
                      same llm_model_func, written to a MINIRAG_KW_CACHE file
                      (MiniRAG's own cache format, keyed by prompt sha256)
  B  contexts  (CPU)  rag.aquery(only_need_context=True) in worker processes with
                      MINIRAG_KW_CACHE_ONLY=1 and the LLM replaced by a function
                      that raises -- a prompt differing by one byte, or any LLM
                      call, fails instead of silently reaching the GPU
  C  answers   (GPU)  the answer call MiniRAG would make, rebuilt verbatim from
                      the context (rag_response / naive_rag_response, same
                      llm_model_func, same post-processing), many in parallel

tests/research/test_phased_qa.py checks on a real MiniRAG index that phases
A-C send the same LLM calls and return the same answers as rag.aquery.

C3 (`naive`) has no keyword step and its retrieval does not depend on the seed.
Keyword output is shared by C0-C2 for one seed (amendment S2).

    python reproduce/research/phased_qa.py keywords --questions Q --seed 101 --out DIR
    python reproduce/research/phased_qa.py contexts --config C1 --questions Q --seed 101 --out DIR
    python reproduce/research/phased_qa.py answers  --config C1 --questions Q --seed 101 --out DIR

DIR/kw_s<seed>.jsonl is the keyword cache; DIR/<config>_s<seed>/ holds
contexts.jsonl, context.jsonl (retrieval log), answers.jsonl, answers.csv,
requests.jsonl (per-HTTP metadata) and run_note.json.

--serving names the SLM (default serving_qwen_modal.json). Qwen and Phi deployments
both accept the alias minirag-slm, so a stale MINIRAG_SLM_URL would only show up in
requests.jsonl after the calls were paid for: phases A and C refuse to start unless
GET /v1/models lists the serving file's model, and append what they saw to
DIR/serving_checks.jsonl.
"""

import argparse
import asyncio
import csv
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import qa_run  # noqa: E402

INDEX = ROOT / "indexes/multihop_rag-qwen-full609"
QWEN_SERVING = Path(__file__).with_name("serving_qwen_modal.json")
REGISTRATION = "7013291"  # MultiHop-RAG (MULTIHOP_RAG_ROADMAP.md)
LIHUA_REGISTRATION = "860f20f"  # LiHua ablation v2 (docs/research/lihua_world/LIHUA_ABLATION_V2.md), configs L-*
# LiHua ablation with Phi-3.5-mini (docs/research/lihua_world/LIHUA_ABLATION_PHI.md); None until registered
LIHUA_PHI_REGISTRATION = "56b65f2"
PHI_MODEL = "microsoft/Phi-3.5-mini-instruct"
# LiHua ablation with MiniCPM3-4B (docs/research/lihua_world/LIHUA_ABLATION_MINICPM.md); None until registered
LIHUA_MINICPM_REGISTRATION = "afd0288"
MINICPM_MODEL = "openbmb/MiniCPM3-4B"
# LiHua run with Phi-3.5-mini under static RoPE (serving_phi_rope_modal.json, docs/research/lihua_world/LIHUA_PHI_ROPE.md):
# same model id as the Phi run of 03/11, told apart by the serving file's served_alias; None until registered
LIHUA_PHI_ROPE_REGISTRATION = "0501474"
PHI_ROPE_ALIAS = "phi35-static-longrope"
# Amendment PA1 of the same file (07/11/2026): the pure BM25 arm of the BM25 reproduction added to the Phi run;
# None until committed
PHI_ROPE_PA1_REGISTRATION = "e6d26db"
PHI_ROPE_ARMS = {"L-C0": "registration", "L-B2": "registration", "P-BM25-K5": "PA1"}
# LiHua BM25 reproduction, 637 questions, configs P-* (docs/research/lihua_world/LIHUA_BM25_REPRO.md);
# None until registered
BM25_REPRO_REGISTRATION = "4219fa3"
# Amendment OB1 (same file, dated 07/11/2026): the original code's NaiveRAG and BM25 at its budget; None until committed
OB1_REGISTRATION = "5bd7965"
OB1_ARMS = ("P-NAIVE-ORIG", "P-BM25-K5-2K")
QWEN_MODEL = "Qwen/Qwen2.5-3B-Instruct"
# P-BM25-* contexts come from the standalone bm25_pure.py (no minirag import): (top_k, max_tokens)
PURE_BM25 = {"P-BM25-K5": (5, 6000), "P-BM25-4K": (60, 4000),
             "P-BM25-K5-2K": (5, 2000)}  # amendment OB1: the original code's text budget
# Amendment OB1: upstream naive_query with the original code's defaults (commit 4176657: top_k 5,
# max_token_for_text_unit 2000, cosine threshold 0)
QP_OVERRIDE = {"P-NAIVE-ORIG": {"top_k": 5, "max_token_for_text_unit": 2000}}


def registration_for(config, model=None, alias=None):
    if config == "L-T":
        return "TEMPORAL_REGISTRATION.md/Sửa đổi 1 (10/11/2026)"
    if model == PHI_MODEL and alias == PHI_ROPE_ALIAS:  # static-RoPE Phi run: only its registered arms
        if config not in PHI_ROPE_ARMS:
            raise SystemExit(f"the static-RoPE Phi run registers {sorted(PHI_ROPE_ARMS)}, not {config}")
        commit = LIHUA_PHI_ROPE_REGISTRATION if PHI_ROPE_ARMS[config] == "registration" else PHI_ROPE_PA1_REGISTRATION
        if commit is None:
            raise SystemExit(f"{config} of the static-RoPE Phi run is not registered yet: commit LIHUA_PHI_ROPE.md first")
        return commit
    if config in OB1_ARMS:
        if OB1_REGISTRATION is None:
            raise SystemExit("amendment OB1 is not registered yet: commit it in LIHUA_BM25_REPRO.md first")
        if model not in (None, QWEN_MODEL):
            raise SystemExit(f"amendment OB1 is registered for {QWEN_MODEL}, not {model}")
        return OB1_REGISTRATION
    if config.startswith("P-"):
        if BM25_REPRO_REGISTRATION is None:
            raise SystemExit("the BM25 reproduction is not registered yet: commit LIHUA_BM25_REPRO.md first")
        if model not in (None, QWEN_MODEL):
            raise SystemExit(f"the BM25 reproduction is registered for {QWEN_MODEL}, not {model}")
        return BM25_REPRO_REGISTRATION
    if not config.startswith("L-"):
        return REGISTRATION
    if model == PHI_MODEL:
        if LIHUA_PHI_REGISTRATION is None:
            raise SystemExit("the Phi ablation is not registered yet: commit LIHUA_ABLATION_PHI.md first")
        return LIHUA_PHI_REGISTRATION
    if model == MINICPM_MODEL:
        if LIHUA_MINICPM_REGISTRATION is None:
            raise SystemExit("the MiniCPM ablation is not registered yet: commit LIHUA_ABLATION_MINICPM.md first")
        return LIHUA_MINICPM_REGISTRATION
    return LIHUA_REGISTRATION


BASE_ENV = {"MINIRAG_ANSWER_TYPE_FIX": "1", "MINIRAG_PATH2CHUNK_FIX": "0", "MINIRAG_CHUNK_CUT": "",
            "MINIRAG_TRUNCATE_SOURCES": "1", "MINIRAG_MAX_TOKENS": "1024",
            "MINIRAG_DROP_ENTITIES": "", "MINIRAG_NO_GRAPH": ""}  # empty = off; set so no config inherits them
FUSION = {"C0": None, "C1": "vector_bm25", "C2": "vector", "C3": None, "C_orig": None,
          # LiHua ablation v2 (docs/research/lihua_world/LIHUA_ABLATION_V2.md)
          "L-C0": None, "L-T": None, "L-B2": "vector_bm25", "L-VEC": "vector", "L-BM25": "bm25", "L-B1": "rrf_bm25",
          "L-NOENT": "vector_bm25", "L-NOGRAPH": None,
          # LiHua BM25 reproduction (docs/research/lihua_world/LIHUA_BM25_REPRO.md): P-C0 = L-C0 switches;
          # P-NAIVE = upstream naive_query; P-BM25-* = bm25_pure.py contexts answered as naive_query would
          "P-C0": None, "P-NAIVE": None, "P-BM25-K5": None, "P-BM25-4K": None,
          "P-NAIVE-ORIG": None, "P-BM25-K5-2K": None}
MODE = {name: "mini" for name in FUSION} | {"C3": "naive", "P-NAIVE": "naive", "P-BM25-K5": "naive",
                                            "P-BM25-4K": "naive", "P-NAIVE-ORIG": "naive", "P-BM25-K5-2K": "naive"}
# C_orig (amendment S3): original MiniRAG at query time -- upstream answer-type matching, Sources uncapped.
EXTRA_ENV = {"C_orig": {"MINIRAG_ANSWER_TYPE_FIX": "0", "MINIRAG_TRUNCATE_SOURCES": "0"},
             "L-T": {"MINIRAG_TEMPORAL": "1"},
             "L-NOENT": {"MINIRAG_DROP_ENTITIES": "1"}, "L-NOGRAPH": {"MINIRAG_NO_GRAPH": "1"},
             "P-NAIVE-ORIG": {"COSINE_THRESHOLD": "0"}}
# Configs whose answer path never calls the keyword parser: no phase A cache is read or needed.
NO_KEYWORDS = {"C3", "L-NOGRAPH", "P-NAIVE", "P-BM25-K5", "P-BM25-4K", "P-NAIVE-ORIG", "P-BM25-K5-2K"}


# ---------------------------------------------------------------- shared
def config_env(config):
    """The retrieval switches apply_env sets for a config, as recorded in run notes."""
    return BASE_ENV | {"MINIRAG_CHUNK_FUSION": FUSION[config] or "", "MINIRAG_TEMPORAL": "1" if config == "L-T" else "0"} | EXTRA_ENV.get(config, {})


def apply_env(config, seed, kw_cache=None, cache_only=False, context_log=None):
    if config.startswith("P-") and os.environ.get("TOP_K"):  # QueryParam.top_k reads it; P-NAIVE needs upstream 60
        raise SystemExit(f"TOP_K={os.environ['TOP_K']} is set; the P-* arms run with QueryParam defaults")
    os.environ.update(BASE_ENV | EXTRA_ENV.get(config, {}))
    os.environ["MINIRAG_TEMPORAL"] = "1" if config == "L-T" else "0"
    os.environ["MINIRAG_SLM_SEED"] = str(seed)
    for name, value in (("MINIRAG_CHUNK_FUSION", FUSION[config]), ("MINIRAG_KW_CACHE", kw_cache),
                        ("MINIRAG_CONTEXT_LOG", context_log)):
        if value:
            os.environ[name] = str(value)
        else:
            os.environ.pop(name, None)
    if cache_only:
        os.environ["MINIRAG_KW_CACHE_ONLY"] = "1"
    else:
        os.environ.pop("MINIRAG_KW_CACHE_ONLY", None)


def read_questions(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if len({r["query_id"] for r in rows}) != len(rows):
        raise ValueError("duplicate query_id")
    return rows


def read_jsonl(path, key="query_id"):
    out = {}
    if Path(path).exists():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                out[record[key]] = record  # last record wins on resume
    return out


def append_jsonl(handle, record):
    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    handle.flush()


def is_context_overflow(exc):
    """vLLM rejects a prompt longer than max_model_len with HTTP 400; only C_orig (Sources uncapped) can hit it."""
    import openai

    text = str(exc).lower()
    return isinstance(exc, openai.BadRequestError) and ("context length" in text or "max_model_len" in text
                                                         or "maximum model length" in text)


def snapshot(dest, index=INDEX):
    """Writable copy of the frozen index: MiniRAG writes its log and LLM cache into its working dir."""
    dest = Path(dest)
    dest.mkdir(parents=True)
    for path in Path(index).iterdir():
        if path.is_file() and path.suffix != ".log":
            shutil.copyfile(path, dest / path.name)  # copyfile: no read-only flag carried over
    return dest


def check_family(rows, index, config=None):
    """Questions, index and config must belong to the same dataset. The first LiHua smoke silently ran on the
    MultiHop index (default --index) when the launcher lost its environment; this makes that impossible."""
    lihua_index = "lihua" in str(index).lower()
    lihua_questions = rows[0]["query_id"].startswith("lh-")
    if lihua_questions != lihua_index:
        raise SystemExit(f"questions ({rows[0]['query_id']}...) and index {index} belong to different datasets")
    if config is not None and config.startswith(("L-", "P-")) != lihua_index:
        raise SystemExit(f"config {config} does not run on index {index}")


def index_fingerprint(index):
    """sha256 of index_manifest.json when the index has one (index_run.py); older indexes such as LiHua's are hashed
    file by file with qa_run.index_hash (log and LLM cache excluded)."""
    manifest = Path(index) / "index_manifest.json"
    if manifest.is_file():
        return {"index_manifest_sha256": qa_run.file_hash(manifest)}
    return {"index_files_sha256": qa_run.index_hash(Path(index))}


def build(workdir, llm_max_async=32):
    from gemini_common import build_rag
    Path(workdir).mkdir(parents=True, exist_ok=True)  # MiniRAG opens its log there before creating the dir
    return build_rag(argparse.Namespace(model="minirag-slm", embedmodel="local", workingdir=str(workdir)),
                     llm_max_async=llm_max_async)


def read_serving(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def serving_identity(path):
    """(model, served_alias) of a serving file: what registration_for needs to pick the registration."""
    serving = read_serving(path)
    return serving["model"], serving.get("served_alias")


def use_slm(serving_path=QWEN_SERVING, log=None, **fields):
    """Point the backend at the SLM and refuse an endpoint that serves another model than --serving."""
    from dotenv import load_dotenv
    import slm_smoke

    load_dotenv(ROOT / ".env")
    qa_run.configure_environment(argparse.Namespace(backend="modal"))
    os.environ["MINIRAG_MAX_TOKENS"] = BASE_ENV["MINIRAG_MAX_TOKENS"]  # never the indexing cap
    serving = read_serving(serving_path)
    served = slm_smoke.require_model(serving)
    if log is not None:
        with open(log, "a", encoding="utf-8") as fh:
            append_jsonl(fh, fields | {"at": qa_run.utc_now(), "serving": str(serving_path),
                                       "serving_sha256": qa_run.file_hash(serving_path),
                                       "model": serving["model"], "served_models": served})


def write_note(directory, **fields):
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    note = {"registration_commit": REGISTRATION, "head_commit": head, "written_at": qa_run.utc_now()} | fields
    (Path(directory) / "run_note.json").write_text(json.dumps(note, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- phase A
KW_RETRIES = 5  # LiHua MiniCPM amendment M2: an unusable keyword reply is resampled up to 5 times


def keywords_valid(result):
    """A keyword reply minirag_query can use: a dict whose entities_from_query is a non-empty list (amendment M2)."""
    import json_repair

    try:
        data = json_repair.loads(result or "")
    except Exception:
        return False
    return (isinstance(data, dict) and isinstance(data.get("answer_type_keywords", []), list)
            and isinstance(data.get("entities_from_query"), list) and len(data["entities_from_query"]) > 0)


def kw_attempts_path(cache_path):
    return Path(cache_path).with_name(Path(cache_path).name.replace("kw_", "kw_attempts_", 1))


async def keyword_phase(rag, rows, cache_path, seed=None, out_requests=None):
    """Same prompt as minirag_query builds under MINIRAG_KW_CACHE (TYPE_POOL sorted).

    Amendment M2: attempt 0 uses the run's seed; an unusable reply is resampled with seed*100+k, k = 1..KW_RETRIES.
    Every attempt goes to kw_attempts_s<seed>.jsonl; the cache gets the accepted reply, or the last one when none is
    usable (minirag_query then returns fail_response). A model whose first reply is usable makes one call, as before.
    """
    from minirag.prompt import PROMPTS

    types, _ = await rag.chunk_entity_relation_graph.get_types()
    pool = sorted(types)
    done = read_jsonl(cache_path, key="prompt_sha256")
    tried = {}
    attempts_path = kw_attempts_path(cache_path)
    if attempts_path.exists():
        for line in attempts_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                tried.setdefault(record["prompt_sha256"], []).append(record)
    with open(cache_path, "a", encoding="utf-8") as fh, open(attempts_path, "a", encoding="utf-8") as log:
        async def one(row):
            prompt = PROMPTS["minirag_query2kwd"].format(query=row["Question"], TYPE_POOL=pool)
            key = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            history = tried.get(key, [])
            if key in done and not history:  # cached before attempts were logged: that reply is attempt 0
                history = [{"prompt_sha256": key, "query_id": row["query_id"], "attempt": 0, "seed": seed,
                            "valid": keywords_valid(done[key]["result"]), "result": done[key]["result"]}]
                append_jsonl(log, history[0])
            result = history[-1]["result"] if history else None
            k = len(history)
            while (k == 0 or not keywords_valid(result)) and k <= KW_RETRIES:
                attempt_seed = seed if k == 0 else (seed or 0) * 100 + k
                result = await rag.llm_model_func(prompt, **({} if k == 0 else {"seed": attempt_seed}))
                append_jsonl(log, {"prompt_sha256": key, "query_id": row["query_id"], "attempt": k,
                                   "seed": attempt_seed, "valid": keywords_valid(result), "result": result})
                k += 1
            if key not in done or done[key]["result"] != result:
                append_jsonl(fh, {"prompt_sha256": key, "result": result, "query_id": row["query_id"]})
        await asyncio.gather(*(one(r) for r in rows))


# ---------------------------------------------------------------- phase B
async def _forbidden_llm(*args, **kwargs):
    raise RuntimeError("phase B must not call the LLM: keyword output missing from the cache?")


async def context_phase(rag, rows, mode, out_path, overrides=None):
    """Sequential on purpose: retrieval is CPU-bound, so concurrency comes from processes."""
    from minirag.base import QueryParam
    from minirag.prompt import PROMPTS

    rag.llm_model_func = _forbidden_llm
    done = read_jsonl(out_path)
    with open(out_path, "a", encoding="utf-8") as fh:
        for row in rows:
            if row["query_id"] in done:
                continue
            started = time.perf_counter()
            param = QueryParam(mode=mode, only_need_context=True)
            for name, value in (overrides or {}).items():
                setattr(param, name, value)
            context = await rag.aquery(row["Question"], param=param)
            status = "no_context" if context is None else "early_exit" if context == PROMPTS["fail_response"] \
                else "ok"
            append_jsonl(fh, {"query_id": row["query_id"], "status": status,
                              "context": context if status == "ok" else None,
                              "retrieval_s": round(time.perf_counter() - started, 2)})


def run_context_workers(args, rows, out_dir):
    """Round-robin shards, one worker process each; merge in input order."""
    work = Path(tempfile.mkdtemp(prefix="ctx_", dir=out_dir))
    procs = []
    for k in range(args.workers):
        shard = rows[k::args.workers]
        if not shard:
            continue
        qfile = work / f"q{k}.csv"
        with open(qfile, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
            w.writeheader()
            w.writerows(shard)
        env = os.environ | {"PYTHONHASHSEED": "13", "PYTHONUTF8": "1"}  # set iteration order fixed per process
        cmd = [sys.executable, __file__, "contexts-worker", "--config", args.config, "--seed", str(args.seed),
               "--questions", str(qfile), "--out-file", str(out_dir / f"contexts_part{k}.jsonl"),
               "--snapshot", str(work / f"snap{k}"), "--kw", str(args.out / f"kw_s{args.seed}.jsonl"),
               "--index", str(args.index),
               "--context-log", str(out_dir / f"context_part{k}.jsonl")]
        procs.append(subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=open(work / f"w{k}.log", "w"),
                                      stderr=subprocess.STDOUT))
    codes = [p.wait() for p in procs]
    parts = {}
    for k in range(args.workers):
        parts |= read_jsonl(out_dir / f"contexts_part{k}.jsonl")
    missing = [r["query_id"] for r in rows if r["query_id"] not in parts]
    if missing or any(codes):
        print(f"contexts incomplete: exit codes {codes}, {len(missing)} missing; logs in {work}")
        return 1
    with open(out_dir / "contexts.jsonl", "w", encoding="utf-8") as fh:
        for r in rows:
            append_jsonl(fh, parts[r["query_id"]])
    with open(out_dir / "context.jsonl", "w", encoding="utf-8") as fh:
        for k in range(args.workers):
            log = out_dir / f"context_part{k}.jsonl"
            if log.exists():
                fh.write(log.read_text(encoding="utf-8"))
    shutil.rmtree(work, ignore_errors=True)  # snapshots are byte copies of the frozen index
    return 0


# ---------------------------------------------------------------- phase C
def answer_messages(mode, query, context, response_type):
    """(prompt, system_prompt) exactly as minirag_query / naive_query pass them."""
    from minirag.prompt import PROMPTS

    if mode == "mini":
        return query, PROMPTS["rag_response"].format(context_data=context, response_type=response_type)
    return query, PROMPTS["naive_rag_response"].format(content_data=context, response_type=response_type)


def postprocess(mode, query, system_prompt, response):
    """naive_query strips an echoed system prompt; minirag_query returns the reply as is."""
    if mode == "naive" and len(response) > len(system_prompt):
        response = (response[len(system_prompt):].replace(system_prompt, "").replace("user", "")
                    .replace("model", "").replace(query, "").replace("<system>", "")
                    .replace("</system>", "").strip())
    return response


async def answer_phase(llm_func, rows, contexts, mode, out_path, response_type):
    from minirag.prompt import PROMPTS

    done = read_jsonl(out_path)
    with open(out_path, "a", encoding="utf-8") as fh:
        async def one(row):
            if row["query_id"] in done:
                return
            ctx = contexts[row["query_id"]]
            status = ctx["status"]
            if status != "ok":  # MiniRAG answers these without an LLM call
                answer = PROMPTS["fail_response"]
            else:
                prompt, system_prompt = answer_messages(mode, row["Question"], ctx["context"], response_type)
                try:
                    answer = postprocess(mode, row["Question"], system_prompt,
                                         await llm_func(prompt, system_prompt=system_prompt))
                except Exception as exc:
                    if not is_context_overflow(exc):
                        raise
                    # Amendment S3: counted and reported, scored as not accurate -- an empty
                    # answer cannot convey the gold answer.
                    answer, status = "", "context_overflow"
            append_jsonl(fh, {"query_id": row["query_id"], "answer": answer, "context_status": status})
        await asyncio.gather(*(one(r) for r in rows))
    answers = read_jsonl(out_path)
    with open(Path(out_path).with_name("answers.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Question", "Gold Answer", "minirag"])
        for r in rows:
            w.writerow([r["Question"], r["Gold Answer"], answers[r["query_id"]]["answer"]])


# ---------------------------------------------------------------- CLI
def traced(out_dir, fn):
    """Run an LLM phase with every HTTP attempt logged; refuse anything but the SLM."""
    import llm_trace

    llm_trace.install()
    handle = open(Path(out_dir) / "requests.jsonl", "a", encoding="utf-8")

    def sink(record):
        record.pop("response_text", None)
        append_jsonl(handle, record | {"at": qa_run.utc_now()})
        if "gemini" in str(record.get("response_model") or "").lower():
            raise RuntimeError(f"endpoint answered as {record['response_model']}")

    try:
        with llm_trace.trace(sink):
            return asyncio.run(fn())
    finally:
        handle.close()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("phase", choices=("keywords", "contexts", "answers", "contexts-worker"))
    p.add_argument("--config", choices=tuple(FUSION), default="C0")  # C0..C3, C_orig
    p.add_argument("--questions", type=Path, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--out", type=Path, help="Phase directory (keyword cache + one folder per config/seed)")
    p.add_argument("--workers", type=int, default=4, help="Phase B processes (each loads the index: ~1.5 GB RAM)")
    # contexts-worker only
    p.add_argument("--out-file", type=Path)
    p.add_argument("--index", type=Path, default=INDEX, help="Frozen index to copy (default: MultiHop full609)")
    p.add_argument("--snapshot", type=Path)
    p.add_argument("--kw", type=Path)
    p.add_argument("--context-log", type=Path)
    p.add_argument("--serving", type=Path, default=QWEN_SERVING, help="Serving file of the SLM (default Qwen)")
    args = p.parse_args(argv)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "reproduce"))
    rows = read_questions(args.questions)
    if args.phase in ("keywords", "contexts", "contexts-worker"):  # the phases that read the index
        check_family(rows, args.index, None if args.phase == "keywords" else args.config)

    if args.phase == "contexts-worker":
        mode = MODE[args.config]
        apply_env(args.config, args.seed, kw_cache=None if args.config in NO_KEYWORDS else args.kw,
                  cache_only=True, context_log=args.context_log)
        rag = build(snapshot(args.snapshot, args.index), llm_max_async=1)
        if "COSINE_THRESHOLD" in EXTRA_ENV.get(args.config, {}):  # read at import time: make sure it took
            want = float(EXTRA_ENV[args.config]["COSINE_THRESHOLD"])
            if rag.chunks_vdb.cosine_better_than_threshold != want:
                raise SystemExit(f"chunk store threshold {rag.chunks_vdb.cosine_better_than_threshold} != {want}")
        asyncio.run(context_phase(rag, rows, mode, args.out_file, QP_OVERRIDE.get(args.config)))
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    run_dir = args.out / f"{args.config}_s{args.seed}"
    if args.phase == "keywords":
        use_slm(args.serving, args.out / "serving_checks.jsonl", phase="keywords", seed=args.seed)
        apply_env("C0", args.seed, kw_cache=args.out / f"kw_s{args.seed}.jsonl")
        with tempfile.TemporaryDirectory(dir=args.out, ignore_cleanup_errors=True) as tmp:
            rag = build(snapshot(Path(tmp) / "snap", args.index))
            traced(args.out, lambda: keyword_phase(rag, rows, args.out / f"kw_s{args.seed}.jsonl", args.seed))
        got = read_jsonl(args.out / f"kw_s{args.seed}.jsonl", key="query_id")
        missing = [r["query_id"] for r in rows if r["query_id"] not in got]
        print(f"keywords: {len(rows) - len(missing)}/{len(rows)} cached")
        return 1 if missing else 0

    run_dir.mkdir(exist_ok=True)
    if args.phase == "contexts":
        write_note(run_dir, config=args.config, seed=args.seed, mode=MODE[args.config], phase="contexts",
                   registration_commit=registration_for(args.config, *serving_identity(args.serving)),
                   serving=str(args.serving), serving_sha256=qa_run.file_hash(args.serving),
                   model=read_serving(args.serving)["model"],
                   questions=str(args.questions), questions_sha256=qa_run.file_hash(args.questions),
                   index=str(args.index), index_fingerprint=index_fingerprint(args.index),
                   environment=config_env(args.config), query_param_override=QP_OVERRIDE.get(args.config),
                   python_hash_seed=13, workers=args.workers,
                   kw_cache_sha256=qa_run.file_hash(args.out / f"kw_s{args.seed}.jsonl")
                   if args.config not in NO_KEYWORDS else None)
        if args.config in PURE_BM25:  # separate process: the P-BM25 retrieval path never imports minirag
            top_k, max_tokens = PURE_BM25[args.config]
            code = subprocess.run([sys.executable, str(Path(__file__).with_name("bm25_pure.py")),
                                   "--questions", str(args.questions), "--index", str(args.index),
                                   "--top-k", str(top_k), "--max-tokens", str(max_tokens),
                                   "--out-dir", str(run_dir)], cwd=ROOT).returncode
        else:
            code = run_context_workers(args, rows, run_dir)
        if code == 0:
            stats = {}
            for c in read_jsonl(run_dir / "contexts.jsonl").values():
                stats[c["status"]] = stats.get(c["status"], 0) + 1
            print(f"contexts: {stats}")
        return code

    # answers
    from minirag.base import QueryParam

    registration_for(args.config, *serving_identity(args.serving))  # an unregistered P-* run never generates

    use_slm(args.serving, args.out / "serving_checks.jsonl", phase="answers", config=args.config, seed=args.seed)
    apply_env(args.config, args.seed)
    contexts = read_jsonl(run_dir / "contexts.jsonl")
    if any(r["query_id"] not in contexts for r in rows):
        raise SystemExit("contexts.jsonl is incomplete; run the contexts phase first")
    response_type = QueryParam().response_type
    with tempfile.TemporaryDirectory(dir=args.out, ignore_cleanup_errors=True) as tmp:
        rag = build(Path(tmp) / "empty")  # only its llm_model_func is used
        traced(run_dir, lambda: answer_phase(rag.llm_model_func, rows, contexts, MODE[args.config],
                                             run_dir / "answers.jsonl", response_type))
    print(f"answers: {len(read_jsonl(run_dir / 'answers.jsonl'))}/{len(rows)} -> {run_dir / 'answers.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
