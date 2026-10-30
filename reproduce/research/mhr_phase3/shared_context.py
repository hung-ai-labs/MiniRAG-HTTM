"""Split the existing context function at its Sources-ranking branch.

The prefix and suffix are copied as Python AST statements from the installed
source, not rewritten retrieval algorithms. minirag_query's keyword parser is
still called once for each config. Only the common prefix is reused for a pair.
This module makes no LLM requests. Its worker installs a rejecting LLM function.
"""
import argparse
import ast
import asyncio
import contextlib
import copy
from dataclasses import asdict
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
import time

from .common import DEFAULT_REPO, digest, load_repo, now, read_json, read_jsonl, sha, write_json

TAIL_INPUTS = ("final_chunk_id", "chunks_ids", "originalquery", "query_param", "results_node",
               "results_edge", "text_chunks_db", "entities_context", "_n_seeds", "_n_paths", "_t0")
SHARED_OBJECTS = {"text_chunks_db"}
DISALLOWED_ENV = ("MINIRAG_PATH_PRUNE", "MINIRAG_PATH_SCORE", "MINIRAG_RERANK",
                  "MINIRAG_MAX_TOKEN_TEXT_UNIT")


def compile_split(function):
    source = inspect.getsource(function)
    node = ast.parse(source).body[0]
    if not isinstance(node, ast.AsyncFunctionDef):
        raise ValueError("Expected the original async context builder")
    split = [i for i, statement in enumerate(node.body)
             if isinstance(statement, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == "fusion" for t in statement.targets)]
    if len(split) != 1:
        raise ValueError("Context source changed: cannot locate the unique fusion boundary")
    boundary = split[0]
    before = copy.deepcopy(node)
    before.name = "_phase3_prefix"
    before.decorator_list = []
    before.body = copy.deepcopy(node.body[:boundary]) + [ast.Return(value=ast.Call(
        func=ast.Name(id="locals", ctx=ast.Load()), args=[], keywords=[]))]
    bindings = [ast.Assign(targets=[ast.Name(id=name, ctx=ast.Store())], value=ast.Subscript(
        value=ast.Name(id="shared", ctx=ast.Load()), slice=ast.Constant(name), ctx=ast.Load()))
                for name in TAIL_INPUTS]
    after = ast.AsyncFunctionDef(name="_phase3_suffix", args=ast.arguments(
        posonlyargs=[], args=[ast.arg(arg="shared")], vararg=None, kwonlyargs=[],
        kw_defaults=[], kwarg=None, defaults=[]), body=bindings + copy.deepcopy(node.body[boundary:]),
        decorator_list=[], returns=None)
    module = ast.fix_missing_locations(ast.Module(body=[before, after], type_ignores=[]))
    namespace = dict(function.__globals__)
    exec(compile(module, "<phase3-source-preserving-split>", "exec"), namespace)
    return namespace[before.name], namespace[after.name], hashlib.sha256(source.encode()).hexdigest(), ast.unparse(module)


class SharedContext:
    """One pair at a time, no global or cross-seed result cache."""
    def __init__(self, operate):
        self.operate = operate
        self.original = operate._build_mini_query_context
        self.prefix, self.suffix, self.source_sha, self.generated = compile_split(self.original)
        self.signature = inspect.signature(self.original)
        self.cached = None
        self.key = None
        self.prefix_calls = 0
        self.reuses = 0

    @contextlib.contextmanager
    def installed(self):
        if self.operate._build_mini_query_context is not self.original:
            raise RuntimeError("Another context adapter is installed")
        self.operate._build_mini_query_context = self.call
        try:
            yield self
        finally:
            self.operate._build_mini_query_context = self.original
            self.clear()

    def clear(self):
        self.cached = None
        self.key = None

    async def call(self, *args, **kwargs):
        if any(os.environ.get(name, "").strip() for name in DISALLOWED_ENV):
            raise RuntimeError("Unsupported experimental retrieval environment")
        bound = self.signature.bind(*args, **kwargs).arguments
        identity = digest({
            "entities": bound["ent_from_query"], "types": bound["type_keywords"],
            "query": bound["originalquery"], "params": asdict(bound["query_param"]),
            "seed": os.environ.get("MINIRAG_SLM_SEED"),
            "answer_type": os.environ.get("MINIRAG_ANSWER_TYPE_FIX"),
            "path_fix": os.environ.get("MINIRAG_PATH2CHUNK_FIX"),
            "storage_ids": [id(bound[name]) for name in ("knowledge_graph_inst", "entity_name_vdb",
                           "relationships_vdb", "chunks_vdb", "text_chunks_db")],
        })
        if self.cached is None:
            self.cached = await self.prefix(*args, **kwargs)
            self.key = identity
            self.prefix_calls += 1
        else:
            if identity != self.key:
                raise RuntimeError("Inputs changed inside a supposedly identical C0/C1 pair")
            self.reuses += 1
        shared = {name: self.cached[name] if name in SHARED_OBJECTS else copy.deepcopy(self.cached[name])
                  for name in TAIL_INPUTS}
        return await self.suffix(shared)


def stable_log(record):
    return {k: v for k, v in record.items() if k not in ("retrieval_ms", "bm25_ms")}


def context_record(query_id, value, fail_response, seconds):
    status = "no_context" if value is None else "early_exit" if value == fail_response else "ok"
    return {"query_id": query_id, "status": status, "context": value if status == "ok" else None,
            "retrieval_s": round(seconds, 4)}


async def forbidden(*args, **kwargs):
    raise RuntimeError("Offline context validation must never call an LLM")


def build_offline(phased, snapshot):
    # The existing builder checks credentials even when only local embeddings
    # are needed. Bypass that check only while constructing this CPU-only RAG;
    # replace its LLM before any query can run. No key is created or copied.
    from unittest.mock import patch
    with patch("gemini_common._resolve_api_keys", return_value=[]):
        rag = phased.build(snapshot, llm_max_async=1)
    rag.llm_model_func = forbidden
    return rag


async def paired_query(rag, row, seed, kw, out, phased, adapter):
    from minirag.base import QueryParam
    from minirag.prompt import PROMPTS
    adapter.clear()
    values = {}
    started = time.perf_counter()
    try:
        for config in ("C0", "C1"):
            folder = Path(out) / f"{config}_s{seed}"
            folder.mkdir(parents=True, exist_ok=True)
            phased.apply_env(config, seed, kw_cache=kw, cache_only=True, context_log=folder / "context.jsonl")
            t = time.perf_counter()
            value = await rag.aquery(row["Question"], param=QueryParam(mode="mini", only_need_context=True))
            values[config] = context_record(row["query_id"], value, PROMPTS["fail_response"], time.perf_counter() - t)
    finally:
        adapter.clear()
    return values, time.perf_counter() - started


def compare_pair(row, pair, references, logs, original_logs, phased):
    from minirag.base import QueryParam
    mismatches = []
    for config in ("C0", "C1"):
        qid = row["query_id"]
        expected, actual = references[config][qid], pair[config]
        for field in ("status", "context"):
            if expected[field] != actual[field]:
                mismatches.append(f"{config}:{qid}:{field}")
        expected_log = original_logs[config].get(row["Question"])
        actual_log = logs[config].get(row["Question"])
        if (expected_log is None) != (actual_log is None) or (
                expected_log is not None and stable_log(expected_log) != stable_log(actual_log)):
            mismatches.append(f"{config}:{qid}:canonical_log")
        if expected["status"] == actual["status"] == "ok":
            response_type = QueryParam().response_type
            old_prompt = phased.answer_messages("mini", row["Question"], expected["context"], response_type)
            new_prompt = phased.answer_messages("mini", row["Question"], actual["context"], response_type)
            if old_prompt != new_prompt:
                mismatches.append(f"{config}:{qid}:answer_prompt")
    return mismatches


async def worker(args):
    phased = load_repo(args.repo)
    import minirag.operate as operate
    rows = phased.read_questions(args.questions)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    identity = {"questions": sha(args.questions), "keywords": sha(args.kw),
                "index_manifest": sha(args.index / "index_manifest.json"),
                "operate": sha(args.repo / "minirag/operate.py"), "adapter": sha(__file__),
                "seed": args.seed, "reference": str(args.reference) if args.reference else None}
    manifest = out / "manifest.json"
    if manifest.exists() and json.loads(manifest.read_text(encoding="utf-8")) != identity:
        raise ValueError("Worker checkpoint input/settings hashes changed")
    write_json(manifest, identity)
    phased.apply_env("C0", args.seed, kw_cache=args.kw, cache_only=True)
    snap = out / "index_snapshot"
    if not snap.exists():
        phased.snapshot(snap, args.index)
    for name, expected in read_json(args.index / "index_manifest.json")["file_sha256"].items():
        if sha(snap / name) != expected:
            raise ValueError("Worker index snapshot changed: " + name)
    rag = build_offline(phased, snap)
    adapter = SharedContext(operate)
    (out / "generated_context_split.py").write_text(adapter.generated + "\n", encoding="utf-8")
    done = read_jsonl(out / "pairs.jsonl")
    references, original_logs = {}, {}
    if args.reference:
        for config in ("C0", "C1"):
            run = args.reference / f"{config}_s{args.seed}"
            references[config] = read_jsonl(run / "contexts.jsonl")
            original_logs[config] = read_jsonl(run / "context.jsonl", "query")
    status = {"status": "running", "pid": os.getpid(), "total_queries": len(rows),
              "completed_queries": len(done), "started_at": now(), "mismatches": [],
              "llm_calls": 0, "prefix_calls_this_process": 0, "reuses_this_process": 0}
    write_json(out / "STATUS.json", status)
    try:
        with adapter.installed(), (out / "pairs.jsonl").open("a", encoding="utf-8") as fh:
            for row in rows:
                if row["query_id"] in done:
                    continue
                pair, elapsed = await paired_query(rag, row, args.seed, args.kw, out, phased, adapter)
                mismatches = []
                if args.reference:
                    logs = {c: read_jsonl(out / f"{c}_s{args.seed}/context.jsonl", "query") for c in ("C0", "C1")}
                    mismatches = compare_pair(row, pair, references, logs, original_logs, phased)
                record = {"query_id": row["query_id"], "pair": pair, "wall_s": round(elapsed, 4),
                          "mismatches": mismatches}
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
                done[row["query_id"]] = record
                status.update(completed_queries=len(done), updated_at=now(),
                              mismatches=[m for p in done.values() for m in p["mismatches"]],
                              wall_s=sum(p["wall_s"] for p in done.values()),
                              prefix_calls_this_process=adapter.prefix_calls, reuses_this_process=adapter.reuses)
                write_json(out / "STATUS.json", status)
                if mismatches:
                    raise ValueError("Context equivalence failed: " + ",".join(mismatches))
        for config in ("C0", "C1"):
            path = out / f"{config}_s{args.seed}/contexts.jsonl"
            with path.open("w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(done[row["query_id"]]["pair"][config], ensure_ascii=False) + "\n")
        status.update(status="completed", completed_at=now(), source_function_sha256=adapter.source_sha)
        write_json(out / "STATUS.json", status)
    except Exception as exc:
        status.update(status="failed", updated_at=now(), error_type=type(exc).__name__, error=str(exc))
        write_json(out / "STATUS.json", status)
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    p.add_argument("--questions", type=Path, required=True)
    p.add_argument("--kw", type=Path, required=True)
    p.add_argument("--index", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--reference", type=Path)
    p.add_argument("--seed", type=int, default=101)
    args = p.parse_args()
    asyncio.run(worker(args))


if __name__ == "__main__":
    main()
