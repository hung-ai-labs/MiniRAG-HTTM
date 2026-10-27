"""Prepare the labeled official 2Wiki dev release offline, without selecting a corpus.

Standard library only; Python 3.13.5. Run --self-test first. Real data processing
is a draft until the shared protocol has been reviewed. Outputs contain ALL dev
candidates: docs.jsonl is NOT an approved indexing corpus. Select a pool and split
in a separate step. questions.csv and gold.jsonl contain labels, for runners/judge
only; never pass their gold fields to the generation model.
"""

import argparse
import copy
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path


PINS = {
    "dev.json": "79f77ae104088ea8e25b1a65dbece768d45771194663bc5660ec9a98070dadf5",
    "id_aliases.json": "f08ffcb6c2cefca9bdbe86b4248d6ad7a7743762d3f7264c14ff0bae85726fb6",
}
TYPES = {"compositional", "comparison", "bridge_comparison", "inference"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def jsonl(rows):
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows).encode("utf-8")


def alias_map(blob):
    result = {}
    for number, line in enumerate(blob.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        qid, aliases = row["Q_id"], row["aliases"]
        if not isinstance(qid, str) or not isinstance(aliases, list) or any(not isinstance(a, str) for a in aliases):
            raise ValueError(f"Invalid alias record on line {number}")
        if qid in result and result[qid] != aliases:
            raise ValueError(f"Conflicting aliases for {qid}")
        result[qid] = aliases
    return result


def build(items, aliases):
    paragraphs, queries, gold, ids = {}, [], [], set()
    missing_alias_ids = set()
    repeated_context_rows = 0
    queries_with_repeated_titles = 0
    unmapped_supporting_facts = []
    supporting_fact_count = 0
    for item in items:
        qid = item["_id"]
        if not isinstance(qid, str) or not qid or qid in ids:
            raise ValueError("Missing or duplicate query ID")
        ids.add(qid)
        question, answer, kind = item["question"], item["answer"], item["type"]
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"Empty question: {qid}")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError(f"No labeled answer: {qid}; official test is not supported")
        if kind not in TYPES or len(item["context"]) != 10:
            raise ValueError(f"Unexpected type or context count: {qid}")
        local = {}
        has_repeated_title = False
        for title, sentences in item["context"]:
            if not isinstance(title, str) or not title:
                raise ValueError(f"Invalid context title: {qid}")
            if not isinstance(sentences, list) or any(not isinstance(s, str) for s in sentences):
                raise ValueError(f"Invalid sentences: {qid}")
            if title in paragraphs and paragraphs[title] != sentences:
                raise ValueError(f"Conflicting paragraph for title: {title}")
            if title in local:
                repeated_context_rows += 1
                has_repeated_title = True
            paragraphs[title] = sentences
            local[title] = sentences
        queries_with_repeated_titles += int(has_repeated_title)
        evidence = []
        for title, position in item["supporting_facts"]:
            if title not in local or type(position) is not int or position < 0:
                raise ValueError(f"Invalid supporting fact: {qid}")
            supporting_fact_count += 1
            mapped = position < len(local[title])
            record = {"doc_id": title, "sentence_index": position,
                      "fact": local[title][position] if mapped else None,
                      "mapping_status": "ok" if mapped else "sentence_index_out_of_range"}
            evidence.append(record)
            if not mapped:
                unmapped_supporting_facts.append({"query_id": qid, **record,
                                                 "sentence_count": len(local[title])})
        answer_id = item.get("answer_id")
        if answer_id is not None and not isinstance(answer_id, str):
            raise ValueError(f"Unexpected answer_id shape: {qid}")
        if answer_id and answer_id not in aliases:
            missing_alias_ids.add(answer_id)
        accepted = sorted(set([answer] + aliases.get(answer_id, [])))
        queries.append({"query_id": qid, "question": question, "type": kind})
        gold.append({"query_id": qid, "answer": answer, "answer_id": answer_id,
                     "aliases": accepted, "supporting_facts": item["supporting_facts"],
                     "evidence": evidence, "evidences": item.get("evidences", []),
                     "evidences_id": item.get("evidences_id", [])})
    docs, minirag_ids = [], set()
    for title, sentences in sorted(paragraphs.items()):
        original = title + "\n" + " ".join(sentences)
        text = original.strip().replace("\x00", "")
        # Explicitly record any cleaning rather than silently change the protocol.
        if text != original:
            raise ValueError(f"Document requires text normalization; review title: {title}")
        mid = "doc-" + hashlib.md5(text.encode("utf-8")).hexdigest()
        if mid in minirag_ids:
            raise ValueError("Two documents have the same MiniRAG document ID")
        minirag_ids.add(mid)
        docs.append({"doc_id": title, "minirag_doc_id": mid, "title": title,
                     "text": text, "sentences": sentences})
    queries.sort(key=lambda r: r["query_id"])
    gold.sort(key=lambda r: r["query_id"])
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["Question", "Gold Answer", "Type", "query_id"])
    for q, g in zip(queries, gold):
        assert q["query_id"] == g["query_id"]
        writer.writerow([q["question"], g["answer"], q["type"], q["query_id"]])
    outputs = {"docs.jsonl": jsonl(docs), "queries.jsonl": jsonl(queries),
               "gold.jsonl": jsonl(gold), "questions.csv": buf.getvalue().encode("utf-8")}
    counts = {"docs": len(docs), "queries": len(queries),
              "repeated_context_rows": repeated_context_rows,
              "queries_with_repeated_titles": queries_with_repeated_titles,
              "supporting_facts": supporting_fact_count,
              "unmapped_supporting_facts": len(unmapped_supporting_facts),
              "queries_with_unmapped_supporting_facts": len({r["query_id"] for r in unmapped_supporting_facts}),
              "queries_by_type": dict(sorted(Counter(q["type"] for q in queries).items())),
              "answer_ids_missing_alias_record": len(missing_alias_ids),
              "missing_alias_ids": sorted(missing_alias_ids)}
    return outputs, counts, sorted(unmapped_supporting_facts, key=lambda r: (r["query_id"], r["doc_id"], r["sentence_index"]))


def self_test():
    context = [[f"Title-{i}", [f"Sentence {i}.", "Second sentence."]] for i in range(10)]
    rows = [{"_id": "q2", "question": "Who?", "answer": "Małgorzata",
             "answer_id": "Q1", "type": "compositional", "context": context,
             "supporting_facts": [["Title-0", 1]], "evidences": []},
            {"_id": "q1", "question": "When?", "answer": "1516", "answer_id": None,
             "type": "inference", "context": context, "supporting_facts": [["Title-1", 0]]}]
    aliases = alias_map(b'{"Q_id":"Q1","aliases":["Malgorzata"],"demonyms":[]}\n')
    outputs, counts, issues = build(rows, aliases)
    assert issues == []
    assert counts["docs"] == 10 and counts["queries"] == 2
    assert outputs == build(list(reversed(rows)), aliases)[0]
    assert all(set(r) == {"query_id", "question", "type"}
               for r in map(json.loads, outputs["queries.jsonl"].splitlines()))
    assert all(set(r) == {"doc_id", "minirag_doc_id", "title", "text", "sentences"}
               for r in map(json.loads, outputs["docs.jsonl"].splitlines()))
    assert json.loads(outputs["gold.jsonl"].splitlines()[1])["aliases"] == ["Malgorzata", "Małgorzata"]
    parsed = list(csv.DictReader(io.StringIO(outputs["questions.csv"].decode("utf-8"))))
    assert [r["query_id"] for r in parsed] == ["q1", "q2"]
    repeated = copy.deepcopy(rows)
    repeated[0]["context"] = copy.deepcopy(repeated[0]["context"])
    repeated[0]["context"][9] = copy.deepcopy(repeated[0]["context"][0])
    repeated_outputs, repeated_counts, _ = build(repeated, aliases)
    assert repeated_counts["queries"] == 2 and repeated_counts["docs"] == 10
    assert repeated_counts["repeated_context_rows"] == 1
    assert repeated_counts["queries_with_repeated_titles"] == 1
    assert repeated_outputs == outputs
    out_of_range = copy.deepcopy(rows)
    out_of_range[0]["supporting_facts"] = [["Title-0", 99]]
    flagged_outputs, flagged_counts, flagged_issues = build(out_of_range, aliases)
    assert flagged_counts["queries"] == 2 and flagged_counts["unmapped_supporting_facts"] == 1
    assert flagged_issues[0]["fact"] is None
    flagged_gold = json.loads(flagged_outputs["gold.jsonl"].splitlines()[1])
    assert flagged_gold["supporting_facts"] == [["Title-0", 99]]
    assert flagged_gold["evidence"][0]["mapping_status"] == "sentence_index_out_of_range"
    bad_cases = []
    bad = copy.deepcopy(rows); bad[1]["_id"] = "q2"; bad_cases.append(bad)
    bad = copy.deepcopy(rows)
    bad[1]["context"] = copy.deepcopy(bad[1]["context"])
    bad[1]["context"][0][1][0] = "Conflict"
    bad_cases.append(bad)
    bad = copy.deepcopy(repeated)
    bad[0]["context"][9][1][0] = "Conflicting duplicate within one query"
    bad_cases.append(bad)
    bad = copy.deepcopy(rows); bad[0]["supporting_facts"] = [["Missing-title", 0]]; bad_cases.append(bad)
    bad = copy.deepcopy(rows); bad[0]["answer"] = ""; bad_cases.append(bad)
    for bad in bad_cases:
        try:
            build(bad, aliases)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid fixture was accepted")
    print("SELF-TEST OK: deterministic output, Unicode, aliases, IDs, CSV, no gold fields in queries/docs, invalid-input rejection")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--raw", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--check", action="store_true", help="Recompute outputs and verify; write nothing")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.raw is None or args.out is None:
        parser.error("Supply --raw and --out, or use --self-test")
    raw, out = args.raw.resolve(), args.out.resolve()
    if out == raw or raw in out.parents or "indexes" in out.parts:
        parser.error("Output must be separate from raw data and indexes")
    blobs = {name: (raw / name).read_bytes() for name in PINS}
    for name, blob in blobs.items():
        if digest(blob) != PINS[name]:
            raise ValueError(f"Source checksum mismatch: {name}")
    outputs, counts, issues = build(json.loads(blobs["dev.json"]), alias_map(blobs["id_aliases.json"]))
    if counts["queries"] != 12576:
        raise ValueError("Unexpected official dev count")
    manifest = {"dataset": "2WikiMultiHopQA", "format_version": 2,
                "duplicate_context_policy": "identical title and sentence list share one document; conflicting content raises an error; keep every query",
                "unmapped_evidence_policy": "preserve original supporting_facts; fact=null and explicit mapping_status for out-of-range sentence indices; do not guess or exclude queries",
                "data_issues": issues,
                "status": "normalized_candidates_not_indexing_corpus", "source_split": "official_dev",
                "benchmark_design": "group_proposed_conversion_not_exact_paper_reproduction",
                "text_format": "title + LF + sentences joined by single space; no Unicode normalization",
                "corpus_selection": None, "split": None, "counts": counts,
                "inputs": PINS, "script_sha256": digest(Path(__file__).read_bytes()),
                "outputs": {n: {"sha256": digest(b), "bytes": len(b)} for n, b in sorted(outputs.items())}}
    outputs["manifest.json"] = json_bytes(manifest)
    missing = [n for n in outputs if not (out / n).exists()]
    differing = [n for n, b in outputs.items() if (out / n).exists() and (out / n).read_bytes() != b]
    if args.check:
        if missing or differing:
            raise SystemExit(f"CHECK FAILED: missing={missing}, differing={differing}")
        print("CHECK OK: all five files match recomputed bytes and source checksums")
        return
    if differing:
        raise SystemExit(f"Refusing to overwrite different existing files: {differing}")
    out.mkdir(parents=True, exist_ok=True)
    for name in missing:
        (out / name).write_bytes(outputs[name])
    print(json.dumps({"status": manifest["status"], "counts": counts, "output": str(out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
