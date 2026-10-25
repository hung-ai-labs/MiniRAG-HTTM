"""Turn the raw MultiHop-RAG release into the inputs this project's runners read.

Reads dataset/MultiHop-RAG/raw/{corpus.json,MultiHopRAG.json} (pinned by
sha256) and writes dataset/MultiHop-RAG/processed/:

    docs.jsonl      one article per line; `text` is the exact string to index
    queries.jsonl   query_id, question, type -- no answers, safe to hand around
    gold.jsonl      query_id, answer, evidence (doc_id + fact)
    questions.csv   Question, Gold Answer, Type, query_id -- the --questions
                    input of qa_run.py and the --queryset of Step_2_evaluate.py
    manifest.json   input/output sha256, counts, text format version

No LLM, no network. The output is byte-deterministic (LF, UTF-8, fixed order),
so two machines that run this get identical files; --check verifies that.

Why the metadata header: 91% of questions name the outlet ("as reported by
TechCrunch") and 33% name a date, yet the outlet appears in only 31% of bodies
and the publication date in none. Indexing the body alone would make most
questions unanswerable by construction. The URL is left out: it is an ID, not
text a question refers to. Only the first chunk of a long article carries the
header -- MiniRAG's chunker is not changed here.

    python reproduce/research/prepare_multihop_rag.py            # write
    python reproduce/research/prepare_multihop_rag.py --check    # verify only
"""

import argparse
import csv
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
RAW_SHA256 = {
    "corpus.json": "20b61b5ab84de84a927420c5d265b7ec8d859ae49980699958a787ade9e4d28f",
    "MultiHopRAG.json": "03cfb4926461f868684903aadc8024447bdda5bb3f6804741424cce338515bff",
}
# Bump whenever the indexed text changes: a different text is a different index.
TEXT_FORMAT_VERSION = 1
TYPES = {"comparison_query": "comparison", "inference_query": "inference",
         "temporal_query": "temporal", "null_query": "null"}


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def minirag_doc_id(text):
    # Same as MiniRAG.ainsert without ids: compute_mdhash_id(clean_text(doc), "doc-").
    return "doc-" + hashlib.md5(text.encode()).hexdigest()


def format_published(value):
    when = datetime.fromisoformat(value)
    return f"{when:%B} {when.day}, {when.year} ({value})"


def doc_text(article):
    lines = [f"Title: {article['title'].strip()}", f"Source: {article['source'].strip()}"]
    if (article.get("author") or "").strip():
        lines.append(f"Author: {article['author'].strip()}")
    lines.append(f"Published: {format_published(article['published_at'])}")
    lines.append(f"Category: {article['category'].strip()}")
    text = "\n".join(lines) + "\n\n" + article["body"].replace("\x00", "").strip()
    # clean_text() must be a no-op, otherwise MiniRAG would hash a different string.
    assert text == text.strip().replace("\x00", "")
    return text


def build(corpus, queries):
    """Return {filename: bytes} for every output except the manifest."""
    docs, by_url, by_doc_id = [], {}, set()
    for article in corpus:
        url = article["url"]
        if url in by_url:
            raise ValueError(f"duplicate url in corpus: {url}")
        text = doc_text(article)
        doc_id = minirag_doc_id(text)
        if doc_id in by_doc_id:
            raise ValueError(f"two articles produce the same indexed text: {url}")
        by_url[url] = article
        by_doc_id.add(doc_id)
        docs.append({"doc_id": url, "minirag_doc_id": doc_id, "title": article["title"],
                     "source": article["source"], "published_at": article["published_at"],
                     "category": article["category"], "text": text})

    query_rows, gold_rows, seen = [], [], set()
    for position, item in enumerate(queries):
        if item["question_type"] not in TYPES:
            raise ValueError(f"unknown question_type: {item['question_type']}")
        if item["query"] in seen:
            # Step_2_evaluate joins verdicts back on the question text.
            raise ValueError(f"duplicate question text at row {position}")
        seen.add(item["query"])
        evidence = []
        for ev in item["evidence_list"]:
            if ev["url"] not in by_url:
                raise ValueError(f"evidence url not in corpus at row {position}: {ev['url']}")
            evidence.append({"doc_id": ev["url"], "fact": ev["fact"]})
        query_id = f"mhr-{position:04d}"
        query_rows.append({"query_id": query_id, "question": item["query"],
                           "type": TYPES[item["question_type"]]})
        gold_rows.append({"query_id": query_id, "answer": item["answer"], "evidence": evidence})

    def jsonl(rows):
        return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows).encode()

    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["Question", "Gold Answer", "Type", "query_id"])
    for q, g in zip(query_rows, gold_rows):
        writer.writerow([q["question"], g["answer"], q["type"], q["query_id"]])

    return {"docs.jsonl": jsonl(docs), "queries.jsonl": jsonl(query_rows),
            "gold.jsonl": jsonl(gold_rows), "questions.csv": buf.getvalue().encode()}


def manifest(raw_hashes, outputs, corpus, queries):
    types = {}
    for item in queries:
        types[TYPES[item["question_type"]]] = types.get(TYPES[item["question_type"]], 0) + 1
    data = {
        "dataset": "MultiHop-RAG",
        "text_format_version": TEXT_FORMAT_VERSION,
        "text_header": ["Title", "Source", "Author (omitted when empty)",
                        "Published (Month D, YYYY + raw ISO)", "Category"],
        "doc_id": "article url; minirag_doc_id is what MiniRAG.insert assigns",
        "query_id": "mhr-NNNN = row position in MultiHopRAG.json",
        "inputs": {name: {"sha256": raw_hashes[name]} for name in sorted(raw_hashes)},
        "outputs": {name: {"sha256": sha256_bytes(blob)} for name, blob in sorted(outputs.items())},
        "counts": {"docs": len(corpus),
                   "docs_without_author": sum(1 for a in corpus if not (a.get("author") or "").strip()),
                   "queries": len(queries), "queries_by_type": dict(sorted(types.items()))},
    }
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()


def generate(raw_dir, pin=True):
    raw_bytes = {name: (raw_dir / name).read_bytes() for name in RAW_SHA256}
    raw_hashes = {name: sha256_bytes(blob) for name, blob in raw_bytes.items()}
    if pin:
        for name, expected in RAW_SHA256.items():
            if raw_hashes[name] != expected:
                raise ValueError(f"{name} sha256 {raw_hashes[name]} != pinned {expected}")
    corpus = json.loads(raw_bytes["corpus.json"])
    queries = json.loads(raw_bytes["MultiHopRAG.json"])
    outputs = build(corpus, queries)
    outputs["manifest.json"] = manifest(raw_hashes, outputs, corpus, queries)
    return outputs


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--raw", type=Path, default=ROOT / "dataset/MultiHop-RAG/raw")
    p.add_argument("--out", type=Path, default=ROOT / "dataset/MultiHop-RAG/processed")
    p.add_argument("--check", action="store_true", help="Verify existing outputs; write nothing")
    p.add_argument("--force", action="store_true", help="Overwrite outputs that differ")
    p.add_argument("--no-pin", action="store_true", help=argparse.SUPPRESS)  # tests only
    args = p.parse_args(argv)

    outputs = generate(args.raw, pin=not args.no_pin)
    differing = [name for name, blob in outputs.items()
                 if (args.out / name).exists() and (args.out / name).read_bytes() != blob]
    missing = [name for name in outputs if not (args.out / name).exists()]

    if args.check:
        for name in differing + missing:
            print(f"MISMATCH {name}" if name in differing else f"MISSING  {name}")
        print("OK" if not (differing or missing) else "FAILED")
        return 0 if not (differing or missing) else 1
    if differing and not args.force:
        # Processed files may already back an index; changing them silently would not.
        print("Refusing to overwrite differing outputs (use --force): " + ", ".join(differing))
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    for name, blob in outputs.items():
        (args.out / name).write_bytes(blob)
    counts = json.loads(outputs["manifest.json"])["counts"]
    print(f"Wrote {len(outputs)} files to {args.out}: {counts['docs']} docs, "
          f"{counts['queries']} queries {counts['queries_by_type']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
