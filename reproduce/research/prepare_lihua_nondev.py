"""Prepare the LiHua-World 435 non-dev questions for the ablation v2 runners.

Reads reproduce/stage_d/nondev435.csv (pinned by sha256; the same 435 questions as stage D) and the frozen
index LiHua-World-qwen-modal (read only), and writes dataset/LiHua-World/splits/:

    nondev435.csv            Question, Gold Answer, Type, query_id (lh-NNNN = row position) -- the --questions
                             input of phased_qa.py / run_phased_dev.sh and judge_run.py
    nondev435_gold_chunks.jsonl
                             per question: evidence timestamps -> documents -> chunk ids, for Evidence Recall
                             only (never given to the system)
    nondev435_manifest.json  input/output sha256, counts, evidence mapping report

LiHua's Evidence column lists message timestamps ("20260121_10:00<and>20260701_10:00"); every document starts
with "Time: <timestamp>". A timestamp that matches no document, and a document without any stored chunk (the
index lost one article's chunks, doc-62f43652...), are reported, never guessed.

    python reproduce/research/prepare_lihua_nondev.py            # write
    python reproduce/research/prepare_lihua_nondev.py --check    # verify only
"""

import argparse
import collections
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reproduce/stage_d/nondev435.csv"
SOURCE_SHA256 = None  # filled from the first run's manifest; --check compares against it
INDEX = ROOT / "LiHua-World-qwen-modal"
TIME_RE = re.compile(r"^Time:\s*(\d{8}_\d{2}:\d{2})")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def normalize(timestamp):
    """Five Single questions carry typos: a "Time:" prefix or HHMM without the colon (20260426_1330)."""
    ts = timestamp.replace("Time:", "").strip()
    if re.fullmatch(r"\d{8}_\d{4}", ts):
        ts = f"{ts[:11]}:{ts[11:]}"
    return ts


def doc_index(index):
    """timestamp -> [doc ids] and doc id -> [chunk ids], read from the frozen index."""
    status = json.loads((index / "kv_store_doc_status.json").read_text(encoding="utf-8"))
    chunks = json.loads((index / "kv_store_text_chunks.json").read_text(encoding="utf-8"))
    by_time = collections.defaultdict(list)
    for doc_id, record in status.items():
        m = TIME_RE.match(record.get("content", ""))
        if m:
            by_time[m.group(1)].append(doc_id)
    doc_chunks = collections.defaultdict(list)
    for chunk_id, record in chunks.items():
        doc_chunks[record.get("full_doc_id")].append(chunk_id)
    return by_time, doc_chunks


def build(source, index):
    with open(source, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if len({r["Question"] for r in rows}) != len(rows):
        raise ValueError("duplicate question text")  # judge and resume key on it as well
    by_time, doc_chunks = doc_index(index)

    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["Question", "Gold Answer", "Type", "query_id"])
    gold, report = [], collections.Counter()
    unmatched, chunkless = [], set()
    for i, r in enumerate(rows):
        qid = f"lh-{i:04d}"
        w.writerow([r["Question"], r["Gold Answer"], r["Type"], qid])
        evidence = []
        if r["Type"] == "Null":  # Null questions have no evidence by design; their column holds free text
            report["null_questions_skipped"] += 1
            gold.append({"query_id": qid, "type": r["Type"], "evidence": None})
            continue
        for ts in [normalize(t) for t in r["Evidence"].split("<and>") if t.strip()]:
            docs = by_time.get(ts, [])
            if not docs:
                unmatched.append([qid, ts])
            ids = sorted(c for d in docs for c in doc_chunks.get(d, []))
            chunkless.update(d for d in docs if not doc_chunks.get(d))
            evidence.append({"timestamp": ts, "doc_ids": sorted(docs), "chunk_ids": ids})
            report["timestamps"] += 1
            report["timestamps_matched"] += bool(docs)
            report["timestamps_with_chunks"] += bool(ids)
        gold.append({"query_id": qid, "type": r["Type"], "evidence": evidence})
    outputs = {"nondev435.csv": buf.getvalue().encode(),
               "nondev435_gold_chunks.jsonl": "".join(json.dumps(g) + "\n" for g in gold).encode()}
    manifest = {
        "source": {"path": "reproduce/stage_d/nondev435.csv", "sha256": sha(source.read_bytes())},
        "index": "LiHua-World-qwen-modal",
        "query_id": "lh-NNNN = row position in the source file",
        "counts": {"questions": len(rows), "by_type": dict(sorted(collections.Counter(r["Type"] for r in rows).items()))},
        "evidence_mapping": dict(report) | {"unmatched_timestamps": unmatched,
                                            "evidence_docs_without_chunks": sorted(chunkless)},
        "outputs": {n: {"sha256": sha(b)} for n, b in sorted(outputs.items())},
    }
    outputs["nondev435_manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    return outputs


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--out", type=Path, default=ROOT / "dataset/LiHua-World/splits")
    p.add_argument("--check", action="store_true")
    args = p.parse_args(argv)
    outputs = build(SOURCE, INDEX)
    differing = [n for n, b in outputs.items() if (args.out / n).exists() and (args.out / n).read_bytes() != b]
    missing = [n for n in outputs if not (args.out / n).exists()]
    if args.check:
        print("OK" if not (differing or missing) else f"FAILED: differ {differing} missing {missing}")
        return 0 if not (differing or missing) else 1
    if differing:
        print("Refusing to overwrite differing outputs: " + ", ".join(differing))
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    for name, blob in outputs.items():
        (args.out / name).write_bytes(blob)
    m = json.loads(outputs["nondev435_manifest.json"])
    print(json.dumps({"counts": m["counts"], "evidence_mapping": {k: v for k, v in m["evidence_mapping"].items()
                                                                   if not isinstance(v, list)},
                      "unmatched": len(m["evidence_mapping"]["unmatched_timestamps"]),
                      "chunkless_docs": m["evidence_mapping"]["evidence_docs_without_chunks"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
