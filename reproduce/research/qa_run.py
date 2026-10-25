"""Bounded parallel QA on a frozen MiniRAG index (no indexing or judging).

Heavy project imports are deferred so --help and offline tests need no models.
See QA_PARALLEL.md for Modal setup and the separately invoked paid benchmark.
"""

import argparse
import asyncio
import contextvars
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
TRACE = contextvars.ContextVar("qa_trace", default=None)
CACHE_FILE = "kv_store_llm_response_cache.json"
SCIENTIFIC_ENV = (
    "MINIRAG_ANSWER_TYPE_FIX", "MINIRAG_CHUNK_CUT", "MINIRAG_CHUNK_FUSION",
    "MINIRAG_KW_CACHE_ONLY", "MINIRAG_MAX_TOKEN_TEXT_UNIT", "MINIRAG_MAX_TOKENS",
    "MINIRAG_PATH_PRUNE", "MINIRAG_PATH_SCORE", "MINIRAG_PATH2CHUNK_FIX",
    "MINIRAG_RERANK", "MINIRAG_RERANK_BATCH", "MINIRAG_RERANK_DEVICE",
    "MINIRAG_SLM_SEED", "MINIRAG_TRUNCATE_SOURCES",
)


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--questions", type=Path, required=True)
    p.add_argument("--workingdir", type=Path, required=True, help="Existing source index")
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--concurrency", type=positive, default=4)
    p.add_argument("--llm-max-async", type=positive, default=4)
    p.add_argument("--serving-config", type=Path, help="JSON recording the actual remote model revision and serving setup")
    p.add_argument("--limit", type=positive, default=None)
    p.add_argument("--warmup", type=int, default=0, help="Untimed QA calls before the measured query phase")
    p.add_argument("--backend", choices=("modal", "configured"), default="modal")
    p.add_argument("--model", default="minirag-slm")
    p.add_argument("--embedmodel", default="local")
    p.add_argument("--mode", choices=("mini", "light", "naive"), default="mini")
    p.add_argument("--topk", type=positive, default=0)
    p.add_argument("--maxtokentextunit", type=positive, default=0)
    p.add_argument("--responsetype", default="")
    return p


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def index_files(path):
    return sorted(p for p in Path(path).rglob("*") if p.is_file()
                  and p.name != CACHE_FILE and p.suffix not in (".log", ".lock")
                  and "__pycache__" not in p.parts)


def index_hash(path):
    files = index_files(path)
    if not files:
        raise ValueError("Source index is missing or empty")
    return digest({p.relative_to(path).as_posix(): file_hash(p) for p in files})


def load_questions(path, limit=None):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not {"Question", "Gold Answer"}.issubset(reader.fieldnames or []):
            raise ValueError("CSV requires Question and Gold Answer columns")
        rows = []
        for position, row in enumerate(reader):
            if limit is not None and position >= limit:
                break
            if not row.get("Question", "").strip() or row.get("Gold Answer") is None:
                raise ValueError(f"Invalid CSV row {position + 2}")
            rows.append({"query_id": position, "question": row["Question"],
                         "gold": row["Gold Answer"]})
    if not rows:
        raise ValueError("Question input is empty")
    return rows


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary, path)


@contextmanager
def run_lock(directory):
    """OS lock is released even after a crash; lock files need no stale cleanup."""
    with (directory / ".qa.lock").open("a+b") as f:
        if f.tell() == 0:
            f.write(b"0")
            f.flush()
        f.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            f.seek(0)
            if os.name == "nt":
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f, fcntl.LOCK_UN)


def read_checkpoint(path, rows):
    latest = {}
    if not path.exists():
        return latest
    # A process can die halfway through its last write. Only a trailing,
    # unterminated line may be discarded; corrupt complete lines fail closed.
    with path.open("r+b") as f:
        good_end = 0
        for line in f:
            if not line.endswith(b"\n"):
                f.truncate(good_end)
                break
            rec = json.loads(line)
            qid = rec["query_id"]
            if type(qid) is not int or not 0 <= qid < len(rows):
                raise ValueError("Invalid checkpoint query_id")
            if rec["status"] not in ("ok", "infra_failed", "cancelled"):
                raise ValueError("Invalid checkpoint status")
            if rec["attempt"] != latest.get(qid, {}).get("attempt", 0) + 1:
                raise ValueError("Invalid checkpoint attempt sequence")
            if rec["status"] == "ok" and not isinstance(rec.get("answer"), str):
                raise ValueError("Successful checkpoint has no answer")
            if latest.get(qid, {}).get("status") == "ok":
                raise ValueError("Duplicate successful checkpoint")
            latest[qid] = rec
            good_end = f.tell()
    return latest


def instrument_llm(rag, mode):
    """Observe existing calls, including limiter wait, without changing kwargs."""
    original = rag.llm_model_func

    async def observed(*args, **kwargs):
        started = time.perf_counter()
        try:
            return await original(*args, **kwargs)
        finally:
            trace = TRACE.get()
            if trace is not None:
                phase = "llm"
                if mode in ("mini", "light"):
                    phase = "answer" if kwargs.get("system_prompt") else "kw_parse"
                trace.append({"phase": phase, "wall_s": time.perf_counter() - started})

    rag.llm_model_func = observed


async def run_qa(args, rag_factory, query_param, scientific_config):
    """Testable orchestration; the factory constructs one RAG inside this loop."""
    if args.concurrency < 1 or args.llm_max_async < 1:
        raise ValueError("Concurrency limits must be positive")
    if getattr(args, "warmup", 0) < 0:
        raise ValueError("Warmup must be nonnegative")
    source = args.workingdir.resolve()
    directory = args.run_dir.resolve()
    if directory == source or source in directory.parents or directory in source.parents:
        raise ValueError("Run and source index directories must not contain each other")
    rows = load_questions(args.questions, args.limit)
    identity = {"schema_version": 1, "input_sha256": file_hash(args.questions),
                "selected_rows": len(rows), "index_sha256": index_hash(source),
                "scientific_config": scientific_config}
    if args.resume:
        if not directory.is_dir():
            raise ValueError("Resume directory does not exist")
    else:
        directory.mkdir(parents=True, exist_ok=False)
    with run_lock(directory):
        manifest_path = directory / "manifest.json"
        snapshot = directory / "index_snapshot"
        if args.resume:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest["identity"] != identity:
                raise ValueError("Input, generation configuration or source index changed")
            if index_hash(snapshot) != identity["index_sha256"]:
                raise ValueError("Run index snapshot changed")
        else:
            snapshot.mkdir()
            for path in index_files(source):
                destination = snapshot / path.relative_to(source)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
            if (source / CACHE_FILE).exists():
                shutil.copy2(source / CACHE_FILE, snapshot / CACHE_FILE)
            if index_hash(snapshot) != identity["index_sha256"] or index_hash(source) != identity["index_sha256"]:
                raise ValueError("Source index changed while being copied")
            atomic_json(manifest_path, {"created_at": utc_now(), "identity": identity})
        checkpoint = directory / "generation.jsonl"
        latest = read_checkpoint(checkpoint, rows)
        pending = [row for row in rows if latest.get(row["query_id"], {}).get("status") != "ok"]
        started = time.perf_counter()
        cpu_started = time.process_time()
        session_records = []
        setup_wall = 0.0
        warmup_wall = 0.0
        warmup_count = 0
        query_elapsed = 0.0
        queue = asyncio.Queue()
        tasks = []
        writer = None
        try:
            if pending:
                rag = rag_factory(snapshot)
                instrument_llm(rag, scientific_config["query_param"]["mode"])
                setup_wall = time.perf_counter() - started
                warmup_started = time.perf_counter()
                warmup_count = min(getattr(args, "warmup", 0), len(pending))
                # Warmup uses the same development rows/params but is neither
                # scored nor reused as a measured generation.
                for row in pending[:warmup_count]:
                    await rag.aquery(row["question"], param=query_param)
                warmup_wall = time.perf_counter() - warmup_started
                work = asyncio.Queue()
                enqueued = time.perf_counter()
                for row in pending:
                    work.put_nowait(row)

                async def write_results():
                    with checkpoint.open("a", encoding="utf-8", newline="\n") as f:
                        while True:
                            rec = await queue.get()
                            if rec is None:
                                return
                            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                            f.flush()
                            os.fsync(f.fileno())
                            latest[rec["query_id"]] = rec
                            session_records.append(rec)

                async def worker():
                    while not work.empty():
                        row = work.get_nowait()
                        qid = row["query_id"]
                        begin = time.perf_counter()
                        rec = {"query_id": qid, "attempt": latest.get(qid, {}).get("attempt", 0) + 1,
                               "timestamp": utc_now(), "queue_wait_s": begin - enqueued,
                               "concurrency": args.concurrency, "llm_max_async": args.llm_max_async}
                        trace = []
                        token = TRACE.set(trace)
                        try:
                            answer = await rag.aquery(row["question"], param=query_param)
                            if not isinstance(answer, str) or not answer.strip():
                                raise ValueError("Empty or non-text answer")
                            rec.update(status="ok", answer=answer.replace("\n", "").replace("\r", ""))
                        except asyncio.CancelledError:
                            rec.update(status="cancelled", error_type="CancelledError")
                            raise
                        except Exception as exc:
                            # Never persist exception text: SDK messages may contain credentials.
                            rec.update(status="infra_failed", error_type=type(exc).__name__)
                        finally:
                            rec["query_wall_s"] = time.perf_counter() - begin
                            rec["llm_calls"] = trace
                            rec["non_llm_wall_s"] = max(0, rec["query_wall_s"] - sum(t["wall_s"] for t in trace))
                            TRACE.reset(token)
                            queue.put_nowait(rec)

                writer = asyncio.create_task(write_results())
                tasks = [asyncio.create_task(worker()) for _ in range(min(args.concurrency, len(pending)))]
                completion = asyncio.gather(*tasks)
                try:
                    done, _ = await asyncio.wait((completion, writer), return_when=asyncio.FIRST_COMPLETED)
                    if writer in done:
                        await writer  # Fail promptly on disk errors instead of spending more API calls.
                    await completion
                finally:
                    if not completion.done():
                        completion.cancel()
                    await asyncio.gather(completion, return_exceptions=True)
                query_elapsed = time.perf_counter() - enqueued
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            if writer is not None:
                queue.put_nowait(None)
                await writer
        elapsed = time.perf_counter() - started
        successful = sum(rec.get("status") == "ok" for rec in latest.values())
        complete = successful == len(rows)
        metrics = {"timestamp": utc_now(), "status": "completed" if complete else "partial",
                   "n_expected": len(rows), "n_ok": successful, "n_pending": len(rows) - successful,
                   "session_attempts": len(session_records),
                   "session_ok": sum(r["status"] == "ok" for r in session_records),
                   "session_errors": sum(r["status"] != "ok" for r in session_records),
                   "wall_s": elapsed, "process_cpu_s": time.process_time() - cpu_started,
                   "setup_wall_s": setup_wall, "warmup_wall_s": warmup_wall,
                   "warmup_questions": warmup_count, "query_phase_wall_s": query_elapsed,
                   "concurrency": args.concurrency, "llm_max_async": args.llm_max_async,
                   "mixed_concurrency": len({(r["concurrency"], r["llm_max_async"]) for r in latest.values()}) > 1,
                   "queue_wait_s_total": sum(r["queue_wait_s"] for r in session_records),
                   "llm_wall_s_total": sum(t["wall_s"] for r in session_records for t in r["llm_calls"]),
                   "non_llm_wall_s_total": sum(r["non_llm_wall_s"] for r in session_records)}
        metrics["questions_per_minute"] = 60 * metrics["session_ok"] / elapsed if elapsed else 0
        metrics["questions_per_minute_query_phase"] = 60 * metrics["session_ok"] / query_elapsed if query_elapsed else 0
        if index_hash(source) != identity["index_sha256"] or index_hash(snapshot) != identity["index_sha256"]:
            raise ValueError("Index content changed during QA; results are invalid")
        if complete:
            temporary = directory / "answers.csv.tmp"
            with temporary.open("w", encoding="utf-8", newline="") as f:
                output = csv.writer(f)
                output.writerow(["Question", "Gold Answer", "minirag"])
                for row in rows:
                    output.writerow([row["question"], row["gold"], latest[row["query_id"]]["answer"]])
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, directory / "answers.csv")
        atomic_json(directory / "metrics.json", metrics)
        return metrics


def configure_environment(args):
    if os.environ.get("MINIRAG_KW_CACHE", "").strip() and os.environ.get("MINIRAG_KW_CACHE_ONLY") != "1":
        raise ValueError("Parallel QA requires a frozen keyword cache (MINIRAG_KW_CACHE_ONLY=1), or no keyword cache")
    if args.backend == "modal":
        from urllib.parse import urlsplit
        url = os.environ.get("MINIRAG_SLM_URL", "").strip().rstrip("/")
        key = os.environ.get("MINIRAG_SLM_KEY", "").strip()
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.query or parsed.fragment or not key:
            raise ValueError("Modal requires an HTTPS MINIRAG_SLM_URL and MINIRAG_SLM_KEY")
        os.environ.update(GEMINI_API_BASE=url if url.endswith("/v1") else url + "/v1",
                          GEMINI_API_KEY_ONLY=key, GEMINI_RPM="100000", GEMINI_TPM="100000000")
        os.environ.setdefault("MINIRAG_MAX_TOKENS", "1024")


def scientific_settings(args, query_param):
    # Performance knobs are deliberately excluded: resume may change concurrency.
    # Allowlist scientific switches; never copy arbitrary user environment secrets.
    env = {name: os.environ.get(name, "") for name in SCIENTIFIC_ENV}
    # Files used as parser caches affect output, even when their path is unchanged.
    cache = os.environ.get("MINIRAG_KW_CACHE", "").strip()
    if cache:
        env["keyword_cache_sha256"] = file_hash(Path(cache)) if Path(cache).is_file() else "missing"
    sources = list((ROOT / "minirag").rglob("*.py")) + [ROOT / "reproduce" / "gemini_common.py", Path(__file__)]
    serving = None
    if args.serving_config:
        serving = json.loads(args.serving_config.read_text(encoding="utf-8"))
        required = {"model_revision", "vllm_version", "gpu", "dtype", "max_model_len", "sampling"}
        if not isinstance(serving, dict) or not required.issubset(serving):
            raise ValueError("Serving config requires model_revision, vllm_version, gpu, dtype, max_model_len and sampling")
        # Store only declared, scientific metadata rather than arbitrary secrets.
        serving = {name: serving[name] for name in sorted(required)}
    return {"model": args.model, "embedmodel": args.embedmodel, "backend": args.backend,
            "serving_config": serving,
            "query_param": asdict(query_param), "environment": env,
            "endpoint_sha256": digest(os.environ.get("GEMINI_API_BASE", "default-gemini")),
            "python_hash_seed": os.environ.get("PYTHONHASHSEED", "unset"),
            "source_sha256": digest({p.relative_to(ROOT).as_posix(): file_hash(p) for p in sorted(sources)})}


def main():
    args = parser().parse_args()
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "reproduce"))
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    configure_environment(args)
    required = ["kv_store_text_chunks.json", "vdb_chunks.json"]
    if args.mode in ("mini", "light"):
        required.append("graph_chunk_entity_relation.graphml")
    if not all((args.workingdir / name).is_file() for name in required):
        raise ValueError("A complete existing index is required; this runner does not index documents")
    from gemini_common import build_query_param, build_rag
    query_param = build_query_param(args)
    config = scientific_settings(args, query_param)

    def factory(snapshot):
        from copy import copy
        build_args = copy(args)
        build_args.workingdir = str(snapshot)
        return build_rag(build_args, llm_max_async=args.llm_max_async)

    metrics = asyncio.run(run_qa(args, factory, query_param, config))
    print(json.dumps(metrics, indent=2))
    return 0 if metrics["status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
