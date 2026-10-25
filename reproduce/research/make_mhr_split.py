"""Freeze the MultiHop-RAG dev / internal-test split by query_id.

MultiHop-RAG has no official split. Every tuning look happens on dev; the
internal test stays closed until the final, pre-registered confirmation run.
The split is drawn once, stratified by question type, and committed as ID
lists so that it cannot drift with the code that made it.

Reads dataset/MultiHop-RAG/processed/{questions.csv,gold.jsonl} and writes
dataset/MultiHop-RAG/splits/:

    dev400.ids            one query_id per line, sorted
    test_internal.ids     the remaining query_ids, sorted
    dev400.csv            questions.csv rows of dev, for qa_run.py / judging
    split_manifest.json   seed, quotas, per-type counts, sha256, overlap report

The internal test gets no CSV here on purpose: --emit-test writes it, and is
meant to be run only when Phase 3 opens the test set.

Dev and test share one corpus, so they also share evidence articles. That
leakage cannot be split away (one url-connected component holds 84% of the
questions); it is measured and reported for the Limitations section instead.

    python reproduce/research/make_mhr_split.py            # write
    python reproduce/research/make_mhr_split.py --check    # verify only
"""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[2]
SEED = 13
DEV_SIZE = 400
TYPES = ("comparison", "inference", "null", "temporal")


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def quotas(counts, size):
    """Proportional allocation with largest remainders; ties broken by type name."""
    total = sum(counts.values())
    exact = {t: size * n / total for t, n in counts.items()}
    out = {t: int(x) for t, x in exact.items()}
    for t in sorted(counts, key=lambda t: (-(exact[t] - out[t]), t))[: size - sum(out.values())]:
        out[t] += 1
    return out


def read_questions(processed):
    with open(processed / "questions.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def read_evidence(processed):
    evidence = {}
    for line in (processed / "gold.jsonl").read_text(encoding="utf-8").splitlines():
        g = json.loads(line)
        evidence[g["query_id"]] = {e["doc_id"] for e in g["evidence"]}
    return evidence


def draw(rows, seed=SEED, size=DEV_SIZE):
    by_type = {}
    for r in rows:
        by_type.setdefault(r["Type"], []).append(r["query_id"])
    unknown = set(by_type) - set(TYPES)
    if unknown:
        raise ValueError(f"unknown question types: {sorted(unknown)}")
    want = quotas({t: len(ids) for t, ids in by_type.items()}, size)
    rng = random.Random(seed)
    dev = set()
    for t in TYPES:  # fixed order: the rng stream must not depend on dict order
        dev.update(rng.sample(sorted(by_type[t]), want[t]))
    return dev, want


def overlap_report(dev, test, evidence):
    """How much evidence the two sides share. Null questions have none."""
    dev_docs = set().union(*(evidence[q] for q in dev))
    dev_sets = {frozenset(evidence[q]) for q in dev if evidence[q]}
    with_evidence = [q for q in test if evidence[q]]
    return {
        "dev_evidence_docs": len(dev_docs),
        "test_questions_with_evidence": len(with_evidence),
        "test_questions_sharing_any_doc_with_dev": sum(1 for q in with_evidence if evidence[q] & dev_docs),
        "test_questions_with_identical_evidence_set_in_dev": sum(1 for q in with_evidence
                                                                 if frozenset(evidence[q]) in dev_sets),
    }


def build(processed):
    fieldnames, rows = read_questions(processed)
    ids = [r["query_id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate query_id in questions.csv")
    dev, want = draw(rows)
    test = set(ids) - dev

    def id_list(selected):
        return "".join(q + "\n" for q in sorted(selected)).encode()

    def csv_of(selected):
        buf = io.StringIO(newline="")
        writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(r for r in rows if r["query_id"] in selected)  # input order = query_id order
        return buf.getvalue().encode()

    outputs = {"dev400.ids": id_list(dev), "test_internal.ids": id_list(test), "dev400.csv": csv_of(dev)}
    type_of = {r["query_id"]: r["Type"] for r in rows}
    manifest = {
        "dataset": "MultiHop-RAG",
        "method": "stratified random sample by question type, largest-remainder quotas, "
                  "random.Random(seed).sample over sorted query_ids, types in fixed order",
        "seed": SEED,
        "dev_size": DEV_SIZE,
        "quotas": dict(sorted(want.items())),
        "counts": {side: {t: sum(1 for q in sel if type_of[q] == t) for t in TYPES} | {"total": len(sel)}
                   for side, sel in (("dev", dev), ("test_internal", test))},
        "inputs": {name: {"sha256": sha256_bytes((processed / name).read_bytes())}
                   for name in ("gold.jsonl", "questions.csv")},
        "outputs": {name: {"sha256": sha256_bytes(blob)} for name, blob in sorted(outputs.items())},
        "evidence_overlap": overlap_report(dev, test, read_evidence(processed)),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
    }
    outputs["split_manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    return outputs, rows, test, fieldnames


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--processed", type=Path, default=ROOT / "dataset/MultiHop-RAG/processed")
    p.add_argument("--out", type=Path, default=ROOT / "dataset/MultiHop-RAG/splits")
    p.add_argument("--check", action="store_true", help="Verify existing outputs; write nothing")
    p.add_argument("--emit-test", type=Path, metavar="CSV",
                   help="Phase 3 only: also write the internal-test questions to this CSV")
    args = p.parse_args(argv)

    outputs, rows, test, fieldnames = build(args.processed)
    differing = [n for n, blob in outputs.items() if (args.out / n).exists() and (args.out / n).read_bytes() != blob]
    missing = [n for n in outputs if not (args.out / n).exists()]

    if args.check:
        for name in differing + missing:
            print(f"MISMATCH {name}" if name in differing else f"MISSING  {name}")
        print("OK" if not (differing or missing) else "FAILED")
        return 0 if not (differing or missing) else 1
    if differing:
        # A frozen split is never redrawn in place; a new split is a new experiment.
        print("Refusing to overwrite a frozen split: " + ", ".join(differing))
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    for name, blob in outputs.items():
        (args.out / name).write_bytes(blob)
    if args.emit_test:
        with open(args.emit_test, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(r for r in rows if r["query_id"] in test)
    print(json.dumps(json.loads(outputs["split_manifest.json"])["counts"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
