"""Map every MultiHop-RAG evidence fact to the chunk(s) that contain it (M1.3).

Used only to score retrieval (Evidence Recall of the Sources table); nothing
here reaches the system under test. Chunk IDs are content hashes, so they are
computed with MiniRAG's own chunker and defaults without touching an index;
--index additionally checks that every mapped chunk exists in that index.

Every fact appears verbatim (after whitespace/case normalisation) in its
article. Within the chunks it is either inside one or more chunks (the
100-token overlap can hold it twice), or it straddles a boundary; then its
first and second halves are located separately and both chunks are listed.

Writes dataset/MultiHop-RAG/processed/gold_chunks.jsonl and
gold_chunks_report.json.

    python reproduce/research/map_mhr_evidence.py [--index indexes/multihop_rag-qwen-full609]
"""

import argparse
import collections
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))


def norm(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def locate(fact, chunks):
    """chunks: [(chunk_id, normalised content)] of one article, in order.
    Returns (chunk_ids, how) with how in {"inside", "spans", "missing"}."""
    f = norm(fact)
    inside = [cid for cid, text in chunks if f in text]
    if inside:
        return inside, "inside"
    half = len(f) // 2
    head = [cid for cid, text in chunks if f[:half] in text]
    tail = [cid for cid, text in chunks if f[half:] in text]
    if head and tail:
        return sorted(set(head[-1:] + tail[:1]), key=[c for c, _ in chunks].index), "spans"
    return [], "missing"


def build(processed):
    from index_run import chunk_map, index_settings

    docs = [json.loads(line) for line in (processed / "docs.jsonl").read_text(encoding="utf-8").splitlines()]
    settings = index_settings()
    per_doc = {}
    for d in docs:
        chunks = chunk_map([d], settings)  # insertion order = chunk order
        per_doc[d["doc_id"]] = [(cid, norm(content)) for cid, (_, content) in chunks.items()]
    rows, how = [], collections.Counter()
    for line in (processed / "gold.jsonl").read_text(encoding="utf-8").splitlines():
        g = json.loads(line)
        evidence = []
        for i, e in enumerate(g["evidence"]):
            ids, kind = locate(e["fact"], per_doc[e["doc_id"]])
            how[kind] += 1
            evidence.append({"fact_index": i, "doc_id": e["doc_id"], "chunk_ids": ids, "located": kind})
        rows.append({"query_id": g["query_id"], "evidence": evidence})
    return rows, how, per_doc


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--processed", type=Path, default=ROOT / "dataset/MultiHop-RAG/processed")
    p.add_argument("--index", type=Path, help="Also check that every mapped chunk exists in this index")
    args = p.parse_args(argv)
    sys.path.insert(0, str(ROOT))
    rows, how, per_doc = build(args.processed)

    report = {"facts": sum(how.values()), "located": dict(sorted(how.items())),
              "facts_in_more_than_one_chunk": sum(1 for r in rows for e in r["evidence"]
                                                  if e["located"] == "inside" and len(e["chunk_ids"]) > 1),
              "questions_with_evidence": sum(1 for r in rows if r["evidence"])}
    if args.index:
        stored = set(json.loads((args.index / "kv_store_text_chunks.json").read_text(encoding="utf-8")))
        mapped = {c for r in rows for e in r["evidence"] for c in e["chunk_ids"]}
        report["index_checked"] = args.index.name
        report["mapped_chunks_missing_from_index"] = len(mapped - stored)
    blob = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows).encode()
    (args.processed / "gold_chunks.jsonl").write_bytes(blob)
    (args.processed / "gold_chunks_report.json").write_bytes((json.dumps(report, indent=2) + "\n").encode())
    print(json.dumps(report, indent=2))
    return 0 if not how["missing"] and not report.get("mapped_chunks_missing_from_index") else 1


if __name__ == "__main__":
    sys.exit(main())
