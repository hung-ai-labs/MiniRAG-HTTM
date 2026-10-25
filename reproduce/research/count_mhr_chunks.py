"""Count the chunks MiniRAG will make from docs.jsonl -- no LLM, no network.

Uses MiniRAG's own chunker and its dataclass defaults (chunk size, overlap,
tokenizer), so the count is what indexing will extract, not an estimate.
Chunk IDs are content hashes, so identical chunks across articles collapse
into one extraction; both numbers are reported.

Writes dataset/MultiHop-RAG/processed/chunk_stats.json.

    python reproduce/research/count_mhr_chunks.py            # write
    python reproduce/research/count_mhr_chunks.py --check    # verify only
"""

import argparse
import dataclasses
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]


def chunk_settings():
    from minirag.minirag import MiniRAG

    defaults = {f.name: f.default for f in dataclasses.fields(MiniRAG)}
    return {name: defaults[name] for name in ("chunk_token_size", "chunk_overlap_token_size", "tiktoken_model_name")}


def stats(docs, settings):
    from minirag.operate import chunking_by_token_size
    from minirag.utils import compute_mdhash_id

    per_doc, ids, tokens, overlap_only = [], set(), [], 0
    for doc in docs:
        chunks = chunking_by_token_size(doc["text"], settings["chunk_overlap_token_size"],
                                        settings["chunk_token_size"], settings["tiktoken_model_name"])
        per_doc.append(len(chunks))
        tokens.extend(c["tokens"] for c in chunks)
        # A tail no longer than the overlap repeats the end of the previous chunk.
        overlap_only += sum(1 for c in chunks[1:] if c["tokens"] <= settings["chunk_overlap_token_size"])
        ids.update(compute_mdhash_id(c["content"], prefix="chunk-") for c in chunks)
    return {
        "settings": settings,
        "docs": len(docs),
        "chunks": sum(per_doc),
        "unique_chunk_ids": len(ids),
        # One extraction call plus one gleaning call per unique chunk (gleaning = 1),
        # before retries -- the static reading in EXECUTION_PLAN A5.
        "expected_index_llm_calls": 2 * len(ids),
        "docs_with_more_than_one_chunk": sum(1 for n in per_doc if n > 1),
        "chunks_without_metadata_header": sum(n - 1 for n in per_doc),
        "tail_chunks_inside_overlap": overlap_only,
        "chunks_per_doc": {"median": statistics.median(per_doc), "max": max(per_doc)},
        "tokens_per_chunk": {"median": statistics.median(tokens), "max": max(tokens)},
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--processed", type=Path, default=ROOT / "dataset/MultiHop-RAG/processed")
    p.add_argument("--check", action="store_true")
    args = p.parse_args(argv)
    sys.path.insert(0, str(ROOT))

    docs_path = args.processed / "docs.jsonl"
    docs = [json.loads(line) for line in docs_path.read_text(encoding="utf-8").splitlines()]
    result = {"docs_jsonl_sha256": hashlib.sha256(docs_path.read_bytes()).hexdigest()} | stats(docs, chunk_settings())
    blob = (json.dumps(result, indent=2) + "\n").encode()
    out = args.processed / "chunk_stats.json"
    if args.check:
        ok = out.exists() and out.read_bytes() == blob
        print("OK" if ok else "FAILED")
        return 0 if ok else 1
    out.write_bytes(blob)
    print(blob.decode())
    return 0


if __name__ == "__main__":
    sys.exit(main())
