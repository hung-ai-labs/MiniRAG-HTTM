"""Reproduce C0 graph Sources from diagnostic contributions, without retrieval models.

The diagnostic stream contains the runtime's post-boost contributions. Chunk text
is read only to reproduce the runtime o200k_base token cut.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

import tiktoken

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CHUNKS = ROOT.parents[1] / "LiHua-World-qwen-modal" / "kv_store_text_chunks.json"


def load_diag(path):
    with open(path, encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def rank(diag, limit=30):
    """Counter insertion order preserves kwd2chunk's tie order."""
    scores = Counter()
    for cid, entries in diag["contributions"].items():
        scores[cid] = sum(entry["contribution"] for entry in entries)
    return [cid for cid, _ in scores.most_common(limit)]


def pack(ordered, chunks, budget=4000, encoder=None):
    """Runtime prefix-stop: missing chunks are skipped; first overflow ends pack."""
    encoder = encoder or tiktoken.get_encoding("o200k_base")
    used, kept = 0, []
    for cid in ordered:
        if cid not in chunks:
            continue
        used += len(encoder.encode(chunks[cid]["content"]))
        if used > budget:
            break
        kept.append(cid)
    return kept


def simulate(diag, chunks, encoder=None):
    top = rank(diag, int(diag["top_k"]) // 2)
    # The runtime returns no Sources when node/edge retrieval failed.
    return top, pack(top, chunks, encoder=encoder) if diag["chunk_ids"] else []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--diag", type=Path, required=True)
    parser.add_argument("--frozen", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    args = parser.parse_args()
    diags = load_diag(args.diag)
    frozen = {row["question"]: row for row in load_diag(args.frozen)}
    chunks = json.loads(args.chunks.read_text(encoding="utf-8"))
    encoder = tiktoken.get_encoding("o200k_base")
    if len(diags) != len(frozen) or set(d["query"] for d in diags) != set(frozen):
        raise ValueError("DIAG/frozen question sets differ")
    matches = sum(simulate(d, chunks, encoder)[1] == frozen[d["query"]]["chunk_ids"] for d in diags)
    print(f"{matches}/{len(diags)}")
    return 0 if matches == len(diags) else 1


if __name__ == "__main__":
    raise SystemExit(main())
