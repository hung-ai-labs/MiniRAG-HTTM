"""Index MultiHop-RAG with the Qwen SLM endpoint, logged per request, resumable.

Reads dataset/MultiHop-RAG/processed/docs.jsonl and inserts each article's
`text` with MiniRAG's normal ainsert, in batches of --batch-docs articles (one
batch is the unit of checkpointing; within a batch MiniRAG extracts chunks
concurrently). Nothing in minirag/ is changed.

Guards, because a wrong index is expensive and silent:
  * the LLM must be the Modal SLM endpoint -- never Gemini (Gemini only judges);
  * the index directory must be indexes/multihop_rag-*, so no LiHua index or
    any other existing directory can be touched;
  * a fresh run refuses an existing directory; --resume opens one only when its
    index_manifest.json matches the docs, selection, settings and source code.

Resume. MiniRAG persists its stores at different moments: doc status on every
upsert, extracted_chunks.json right after extraction, chunks/graph/vectors only
at the end of ainsert (_insert_done). A crash in between leaves an article
"processed" whose chunks were never saved -- MiniRAG would then never chunk it
again, and its graph nodes would cite missing chunks (found by the offline
kill-and-resume test). index_progress.jsonl is written only after a batch's
ainsert has returned; on --resume, every article not in it loses its doc status
and checkpointed chunks (reconcile_checkpoint), so MiniRAG redoes it. Hence:
  - a chunk whose batch completed is never sent to the LLM again;
  - chunks of the interrupted batch may be extracted again;
  - entities/relations are keyed by name and chunks/vectors by id, so a repeat
    adds at most another description variant, never a duplicate node or chunk.
--verify (and the end of every run) checks doc-chunk-vector-graph links.

Outputs in the index directory, next to MiniRAG's own files:
  index_manifest.json   identity, status, counts, verification, file sha256
  index_requests.jsonl  one line per HTTP attempt: phase (extract/glean),
                        chunk_id, max_tokens, response model, finish_reason,
                        tokens, latency, reply text, error type
  index_progress.jsonl  completed batches
  events.jsonl          start, resume, reconcile, batch, finish, failure

    python reproduce/research/index_run.py --subset pilot \
        --workingdir indexes/multihop_rag-qwen-pilot30
"""

import argparse
import asyncio
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import qa_run  # noqa: E402  (light: helpers only, heavy imports are deferred there)

INDEX_ROOT = ROOT / "indexes"
PREFIX = "multihop_rag-"
GEMINI_HOST = "generativelanguage.googleapis.com"
IDENTITY_KEYS = ("docs_jsonl_sha256", "selected_doc_ids_sha256", "settings", "source_sha256")


class WrongBackend(RuntimeError):
    pass


def check_workingdir(path, resume, index_root=INDEX_ROOT, prefix=PREFIX):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("The index directory must not be a symlink")
    resolved = path.resolve()
    if resolved.parent != Path(index_root).resolve() or not resolved.name.startswith(prefix):
        raise ValueError(f"The index must be a direct child of {index_root} named {prefix}*: {path}")
    if resolved.exists() and not resume:
        raise ValueError("Index directory already exists; a fresh run never writes into it (use --resume)")
    if resume and not (resolved / "index_manifest.json").is_file():
        raise ValueError("Nothing to resume: no index_manifest.json in this directory")
    return resolved


def select_docs(docs, subset, size, seed):
    if subset == "full":
        return list(docs)
    picked = set(random.Random(seed).sample(sorted(d["doc_id"] for d in docs), size))
    return [d for d in docs if d["doc_id"] in picked]  # keep docs.jsonl order


def require_slm_backend(model):
    base = os.environ.get("GEMINI_API_BASE", "").strip()
    if not base or GEMINI_HOST in base:
        raise WrongBackend("Indexing must run on the SLM endpoint; GEMINI_API_BASE points at Gemini")
    if "gemini" in model.lower():
        raise WrongBackend(f"Indexing must use the SLM, not {model}")


def chunk_map(docs, settings):
    """chunk_id -> (minirag_doc_id, content), exactly as MiniRAG will chunk."""
    from minirag.operate import chunking_by_token_size
    from minirag.utils import compute_mdhash_id

    out = {}
    for d in docs:
        for c in chunking_by_token_size(d["text"], settings["chunk_overlap_token_size"],
                                        settings["chunk_token_size"], settings["tiktoken_model_name"]):
            out[compute_mdhash_id(c["content"], prefix="chunk-")] = (d["minirag_doc_id"], c["content"])
    return out


def index_settings():
    from minirag.minirag import MiniRAG

    defaults = {f.name: f.default for f in dataclasses.fields(MiniRAG)}
    names = ("chunk_token_size", "chunk_overlap_token_size", "tiktoken_model_name", "entity_extract_max_gleaning")
    return {name: defaults[name] for name in names}


def annotator(chunks):
    contents = [(cid, content) for cid, (_, content) in chunks.items()]

    def annotate(messages):
        turns = [m for m in messages if m.get("role") != "system"]
        user_text = "\n".join(m.get("content") or "" for m in turns if m.get("role") == "user")
        found = [(len(content), cid) for cid, content in contents if content and content in user_text]
        # A tail chunk no longer than the overlap is a substring of the chunk before it, so a
        # prompt about the longer chunk matches both: the longest match is the one asked about.
        # The first turn is extraction; gleaning replays it as history plus a continue prompt.
        return {"phase": "extract" if len(turns) == 1 else "glean",
                "chunk_id": max(found)[1] if found else None}

    return annotate


def append_jsonl(path, record):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_jsonl(path):
    if not Path(path).exists():
        return []
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _rewrite_json(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def reconcile_checkpoint(workdir, chunks, done_docs):
    """Undo what an unfinished batch left behind. Returns (chunks, docs) dropped.

    extracted_chunks.json: a chunk whose batch never completed may be marked
    although its entities were never persisted -- drop it so it is extracted
    again. kv_store_doc_status.json is persisted on every upsert, while the chunk
    and vector stores are only written at the end of ainsert; a doc left as
    "processed" would therefore never be chunked again and its graph nodes would
    point at chunks that do not exist. Drop its status so MiniRAG re-chunks it.
    """
    workdir = Path(workdir)
    dropped_chunks = dropped_docs = 0
    path = workdir / "extracted_chunks.json"
    if path.exists():
        ids = json.loads(path.read_text(encoding="utf-8"))
        keep = sorted(c for c in ids if c in chunks and chunks[c][0] in done_docs)
        dropped_chunks = len(ids) - len(keep)
        if dropped_chunks:
            _rewrite_json(path, keep)
    path = workdir / "kv_store_doc_status.json"
    if path.exists():
        status = json.loads(path.read_text(encoding="utf-8"))
        keep = {k: v for k, v in status.items() if k in done_docs}
        dropped_docs = len(status) - len(keep)
        if dropped_docs:
            _rewrite_json(path, keep)
    return dropped_chunks, dropped_docs


def verify(workdir, docs, chunks):
    """Doc-chunk-vector-graph integrity of a finished index. Returns (checks, counts)."""
    import networkx as nx

    workdir = Path(workdir)

    def load(name):
        return json.loads((workdir / name).read_text(encoding="utf-8"))

    status = load("kv_store_doc_status.json")
    text_chunks = load("kv_store_text_chunks.json")
    vdb_ids = {r["__id__"] for r in load("vdb_chunks.json")["data"]}
    extracted = set(load("extracted_chunks.json"))
    graph = nx.read_graphml(workdir / "graph_chunk_entity_relation.graphml")
    expected_docs = {d["minirag_doc_id"] for d in docs}

    def sources(attrs):
        return {s for s in str(attrs.get("source_id", "")).split("<SEP>") if s}

    graph_sources = set()
    for _, attrs in graph.nodes(data=True):
        graph_sources |= sources(attrs)
    for _, _, attrs in graph.edges(data=True):
        graph_sources |= sources(attrs)
    checks = {
        "all_docs_processed": set(status) == expected_docs
                              and all(v.get("status") == "processed" for v in status.values()),
        "chunks_match_expected": set(text_chunks) == set(chunks),
        "chunks_point_to_their_doc": all(text_chunks[c].get("full_doc_id") == chunks[c][0]
                                         for c in text_chunks if c in chunks),
        "chunk_vectors_match_chunks": vdb_ids == set(text_chunks),
        "every_chunk_extracted": set(chunks) <= extracted,
        "graph_sources_exist": graph_sources <= set(text_chunks),
    }
    counts = {"docs": len(status), "chunks": len(text_chunks), "nodes": graph.number_of_nodes(),
              "edges": graph.number_of_edges(), "chunks_without_graph_source": len(set(text_chunks) - graph_sources)}
    return checks, counts


async def run_index(args, docs, rag_factory, identity, chunks):
    """Insert docs batch by batch into args.workingdir. Returns 0 when complete and verified."""
    import llm_trace

    workdir = Path(args.workingdir)
    manifest_path = workdir / "index_manifest.json"
    events = workdir / "events.jsonl"
    progress = workdir / "index_progress.jsonl"
    if args.resume:
        stored = json.loads(manifest_path.read_text(encoding="utf-8"))
        changed = [k for k in IDENTITY_KEYS if stored.get(k) != identity[k]]
        if changed:
            raise ValueError(f"Index identity differs from the existing run ({', '.join(changed)}); refusing to resume")
    else:
        workdir.mkdir(parents=True)
    manifest = identity | {"status": "running", "updated_at": qa_run.utc_now()}
    qa_run.atomic_json(manifest_path, manifest)

    done_docs = {doc for rec in read_jsonl(progress) for doc in rec["minirag_doc_ids"]}
    append_jsonl(events, {"event": "resume" if args.resume else "start", "at": qa_run.utc_now(),
                          "docs_done": len(done_docs), "docs_total": len(docs)})
    if args.resume:
        dropped_chunks, dropped_docs = reconcile_checkpoint(workdir, chunks, done_docs)
        append_jsonl(events, {"event": "reconcile", "at": qa_run.utc_now(),
                              "checkpointed_chunks_dropped": dropped_chunks, "doc_status_dropped": dropped_docs})

    def sink(record):
        append_jsonl(workdir / "index_requests.jsonl", record | {"at": qa_run.utc_now()})
        if "gemini" in str(record.get("response_model") or "").lower():
            raise WrongBackend(f"The endpoint answered as {record['response_model']}")

    todo = [d for d in docs if d["minirag_doc_id"] not in done_docs]
    rag = rag_factory(str(workdir))
    try:
        with llm_trace.trace(sink, annotator(chunks)):
            for start in range(0, len(todo), args.batch_docs):
                batch = todo[start:start + args.batch_docs]
                started = time.perf_counter()
                await rag.ainsert([d["text"] for d in batch])
                append_jsonl(progress, {"doc_ids": [d["doc_id"] for d in batch],
                                        "minirag_doc_ids": [d["minirag_doc_id"] for d in batch],
                                        "seconds": round(time.perf_counter() - started, 1), "at": qa_run.utc_now()})
                done = len(docs) - len(todo) + start + len(batch)
                append_jsonl(events, {"event": "batch", "at": qa_run.utc_now(), "docs_done": done})
                print(f"{done}/{len(docs)} docs")
    except BaseException as exc:
        append_jsonl(events, {"event": "failed", "at": qa_run.utc_now(), "error_type": type(exc).__name__})
        qa_run.atomic_json(manifest_path, manifest | {"status": "partial", "updated_at": qa_run.utc_now()})
        raise

    checks, counts = verify(workdir, docs, chunks)
    ok = all(checks.values())
    files = {p.relative_to(workdir).as_posix(): qa_run.file_hash(p) for p in sorted(workdir.iterdir())
             if p.is_file() and p.suffix in (".json", ".graphml")}
    files.pop("index_manifest.json", None)
    manifest |= {"status": "completed" if ok else "invalid", "updated_at": qa_run.utc_now(),
                 "verification": checks, "counts": counts, "file_sha256": files}
    qa_run.atomic_json(manifest_path, manifest)
    append_jsonl(events, {"event": "finish", "at": qa_run.utc_now(), "status": manifest["status"]})
    print(json.dumps({"status": manifest["status"], "verification": checks, "counts": counts}, indent=2))
    return 0 if ok else 1


def parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--docs", type=Path, default=ROOT / "dataset/MultiHop-RAG/processed/docs.jsonl")
    p.add_argument("--dataset-id", default="multihop_rag",
                   help="Index directories must be indexes/<dataset-id>-*; e.g. 2wiki for 2WikiMultiHopQA")
    p.add_argument("--workingdir", type=Path, required=True, help="indexes/multihop_rag-<name>")
    p.add_argument("--subset", choices=("pilot", "full"), required=True)
    p.add_argument("--pilot-size", type=int, default=30)
    p.add_argument("--seed", type=int, default=13)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--verify", action="store_true", help="Only check an existing index; no LLM calls")
    p.add_argument("--batch-docs", type=qa_run.positive, default=8)
    p.add_argument("--llm-max-async", type=qa_run.positive, default=8)
    p.add_argument("--model", default="minirag-slm")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "reproduce"))
    docs = select_docs(read_jsonl(args.docs), args.subset, args.pilot_size, args.seed)
    settings = index_settings()
    chunks = chunk_map(docs, settings)

    if args.verify:
        checks, counts = verify(args.workingdir, docs, chunks)
        print(json.dumps({"verification": checks, "counts": counts}, indent=2))
        return 0 if all(checks.values()) else 1

    args.workingdir = check_workingdir(args.workingdir, args.resume, prefix=f"{args.dataset_id}-")
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    args.backend = "modal"
    qa_run.configure_environment(args)  # points the shared backend at MINIRAG_SLM_URL / KEY
    require_slm_backend(args.model)

    import llm_trace
    llm_trace.install()
    sources = list((ROOT / "minirag").rglob("*.py")) + [ROOT / "reproduce/gemini_common.py", Path(__file__),
                                                         Path(__file__).with_name("llm_trace.py")]
    identity = {
        "dataset": args.dataset_id, "subset": args.subset,
        "docs_jsonl_sha256": qa_run.file_hash(args.docs),
        "selected_doc_ids_sha256": qa_run.digest(sorted(d["doc_id"] for d in docs)),
        "settings": settings | {"model": args.model, "embedmodel": "local",
                                "max_tokens": os.environ.get("MINIRAG_MAX_TOKENS", ""),
                                "llm_model_max_token_size": 200, "pilot_seed": args.seed,
                                "pilot_size": args.pilot_size if args.subset == "pilot" else None},
        "source_sha256": qa_run.digest({p.relative_to(ROOT).as_posix(): qa_run.file_hash(p) for p in sorted(sources)}),
        "endpoint_sha256": qa_run.digest(os.environ.get("GEMINI_API_BASE", "")),
        "expected": {"docs": len(docs), "chunks": len(chunks), "llm_calls_before_retries": 2 * len(chunks)},
    }
    from gemini_common import build_rag

    def factory(workdir):
        return build_rag(argparse.Namespace(model=args.model, embedmodel="local", workingdir=workdir),
                         llm_max_async=args.llm_max_async)

    return asyncio.run(run_index(args, docs, factory, identity, chunks))


if __name__ == "__main__":
    sys.exit(main())
