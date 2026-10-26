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
REGISTRATION = "7013291"
BASE_ENV = {"MINIRAG_ANSWER_TYPE_FIX": "1", "MINIRAG_PATH2CHUNK_FIX": "0", "MINIRAG_CHUNK_CUT": "",
            "MINIRAG_MAX_TOKENS": "1024"}
FUSION = {"C0": None, "C1": "vector_bm25", "C2": "vector", "C3": None}
MODE = {"C0": "mini", "C1": "mini", "C2": "mini", "C3": "naive"}


# ---------------------------------------------------------------- shared
def apply_env(config, seed, kw_cache=None, cache_only=False, context_log=None):
    os.environ.update(BASE_ENV)
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


def snapshot(dest, index=INDEX):
    """Writable copy of the frozen index: MiniRAG writes its log and LLM cache into its working dir."""
    dest = Path(dest)
    dest.mkdir(parents=True)
    for path in Path(index).iterdir():
        if path.is_file() and path.suffix != ".log":
            shutil.copyfile(path, dest / path.name)  # copyfile: no read-only flag carried over
    return dest


def build(workdir, llm_max_async=32):
    from gemini_common import build_rag
    Path(workdir).mkdir(parents=True, exist_ok=True)  # MiniRAG opens its log there before creating the dir
    return build_rag(argparse.Namespace(model="minirag-slm", embedmodel="local", workingdir=str(workdir)),
                     llm_max_async=llm_max_async)


def use_slm():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    qa_run.configure_environment(argparse.Namespace(backend="modal"))
    os.environ["MINIRAG_MAX_TOKENS"] = BASE_ENV["MINIRAG_MAX_TOKENS"]  # never the indexing cap


def write_note(directory, **fields):
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    note = {"registration_commit": REGISTRATION, "head_commit": head, "written_at": qa_run.utc_now()} | fields
    (Path(directory) / "run_note.json").write_text(json.dumps(note, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- phase A
async def keyword_phase(rag, rows, cache_path, out_requests=None):
    """Same prompt as minirag_query builds under MINIRAG_KW_CACHE (TYPE_POOL sorted)."""
    from minirag.prompt import PROMPTS

    types, _ = await rag.chunk_entity_relation_graph.get_types()
    pool = sorted(types)
    done = read_jsonl(cache_path, key="prompt_sha256")
    with open(cache_path, "a", encoding="utf-8") as fh:
        async def one(row):
            prompt = PROMPTS["minirag_query2kwd"].format(query=row["Question"], TYPE_POOL=pool)
            key = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            if key in done:
                return
            result = await rag.llm_model_func(prompt)
            append_jsonl(fh, {"prompt_sha256": key, "result": result, "query_id": row["query_id"]})
        await asyncio.gather(*(one(r) for r in rows))


# ---------------------------------------------------------------- phase B
async def _forbidden_llm(*args, **kwargs):
    raise RuntimeError("phase B must not call the LLM: keyword output missing from the cache?")


async def context_phase(rag, rows, mode, out_path):
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
            context = await rag.aquery(row["Question"], param=QueryParam(mode=mode, only_need_context=True))
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
            if ctx["status"] != "ok":  # MiniRAG answers these without an LLM call
                answer = PROMPTS["fail_response"]
            else:
                prompt, system_prompt = answer_messages(mode, row["Question"], ctx["context"], response_type)
                answer = postprocess(mode, row["Question"], system_prompt,
                                     await llm_func(prompt, system_prompt=system_prompt))
            append_jsonl(fh, {"query_id": row["query_id"], "answer": answer, "context_status": ctx["status"]})
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
    p.add_argument("--config", choices=tuple(FUSION), default="C0")
    p.add_argument("--questions", type=Path, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--out", type=Path, help="Phase directory (keyword cache + one folder per config/seed)")
    p.add_argument("--workers", type=int, default=4, help="Phase B processes (each loads the index: ~1.5 GB RAM)")
    # contexts-worker only
    p.add_argument("--out-file", type=Path)
    p.add_argument("--snapshot", type=Path)
    p.add_argument("--kw", type=Path)
    p.add_argument("--context-log", type=Path)
    args = p.parse_args(argv)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "reproduce"))
    rows = read_questions(args.questions)

    if args.phase == "contexts-worker":
        mode = MODE[args.config]
        apply_env(args.config, args.seed, kw_cache=args.kw if mode == "mini" else None,
                  cache_only=True, context_log=args.context_log)
        rag = build(snapshot(args.snapshot), llm_max_async=1)
        asyncio.run(context_phase(rag, rows, mode, args.out_file))
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    run_dir = args.out / f"{args.config}_s{args.seed}"
    if args.phase == "keywords":
        use_slm()
        apply_env("C0", args.seed, kw_cache=args.out / f"kw_s{args.seed}.jsonl")
        with tempfile.TemporaryDirectory(dir=args.out, ignore_cleanup_errors=True) as tmp:
            rag = build(snapshot(Path(tmp) / "snap"))
            traced(args.out, lambda: keyword_phase(rag, rows, args.out / f"kw_s{args.seed}.jsonl"))
        got = read_jsonl(args.out / f"kw_s{args.seed}.jsonl", key="query_id")
        missing = [r["query_id"] for r in rows if r["query_id"] not in got]
        print(f"keywords: {len(rows) - len(missing)}/{len(rows)} cached")
        return 1 if missing else 0

    run_dir.mkdir(exist_ok=True)
    if args.phase == "contexts":
        write_note(run_dir, config=args.config, seed=args.seed, mode=MODE[args.config], phase="contexts",
                   questions=str(args.questions), questions_sha256=qa_run.file_hash(args.questions),
                   index_manifest_sha256=qa_run.file_hash(INDEX / "index_manifest.json"),
                   environment={k: os.environ.get(k, "") for k in BASE_ENV} | {"fusion": FUSION[args.config]},
                   python_hash_seed=13, workers=args.workers,
                   kw_cache_sha256=qa_run.file_hash(args.out / f"kw_s{args.seed}.jsonl")
                   if MODE[args.config] == "mini" else None)
        code = run_context_workers(args, rows, run_dir)
        if code == 0:
            stats = {}
            for c in read_jsonl(run_dir / "contexts.jsonl").values():
                stats[c["status"]] = stats.get(c["status"], 0) + 1
            print(f"contexts: {stats}")
        return code

    # answers
    from minirag.base import QueryParam

    use_slm()
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
