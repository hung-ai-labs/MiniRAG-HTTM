"""Offline tests for the MultiHop-RAG preparation step: format, IDs, refusals."""

import contextlib
import csv
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "prepare_multihop_rag", ROOT / "reproduce/research/prepare_multihop_rag.py")
prep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prep)

ARTICLE = {"title": "A title ", "author": None, "source": "TechCrunch",
           "published_at": "2023-10-07T14:05:00+00:00", "category": "business",
           "url": "https://example.com/a", "body": "  Body text.\x00 \n"}
OTHER = dict(ARTICLE, url="https://example.com/b", author="Jane Roe", body="Other body.")
QUERY = {"query": "What did TechCrunch report?", "answer": "Yes",
         "question_type": "inference_query",
         "evidence_list": [{"url": "https://example.com/a", "fact": "f", "title": "A title"}]}
NULL_QUERY = {"query": "Unanswerable?", "answer": "Insufficient information.",
              "question_type": "null_query", "evidence_list": []}


def write_raw(directory, corpus, queries):
    (directory / "corpus.json").write_text(json.dumps(corpus), encoding="utf-8")
    (directory / "MultiHopRAG.json").write_text(json.dumps(queries), encoding="utf-8")


def run(*argv):
    with contextlib.redirect_stdout(io.StringIO()):
        return prep.main([*argv, "--no-pin"])


class FormatTests(unittest.TestCase):
    def test_header_carries_outlet_and_date_and_skips_missing_author(self):
        text = prep.doc_text(ARTICLE)
        self.assertEqual(text, "Title: A title\nSource: TechCrunch\n"
                         "Published: October 7, 2023 (2023-10-07T14:05:00+00:00)\n"
                         "Category: business\n\nBody text.")
        self.assertIn("Author: Jane Roe\n", prep.doc_text(OTHER))

    def test_doc_id_matches_what_minirag_insert_assigns(self):
        try:
            from minirag.utils import clean_text, compute_mdhash_id
        except ImportError as exc:  # pragma: no cover - depends on the venv
            self.skipTest(f"minirag not importable: {exc}")
        text = prep.doc_text(ARTICLE)
        self.assertEqual(prep.minirag_doc_id(text), compute_mdhash_id(clean_text(text), prefix="doc-"))

    def test_queries_hold_no_answers_and_gold_maps_evidence_to_doc_ids(self):
        out = prep.build([ARTICLE, OTHER], [QUERY, NULL_QUERY])
        queries = [json.loads(line) for line in out["queries.jsonl"].decode().splitlines()]
        gold = [json.loads(line) for line in out["gold.jsonl"].decode().splitlines()]
        self.assertEqual(queries[0], {"query_id": "mhr-0000", "question": QUERY["query"], "type": "inference"})
        self.assertEqual(gold[0]["evidence"], [{"doc_id": "https://example.com/a", "fact": "f"}])
        self.assertEqual((queries[1]["type"], gold[1]["evidence"]), ("null", []))

    def test_rejects_inputs_that_would_break_joins(self):
        cases = {
            "duplicate url": ([ARTICLE, ARTICLE], [QUERY]),
            "evidence url not in corpus": ([OTHER], [QUERY]),
            "duplicate question text": ([ARTICLE], [QUERY, QUERY]),
            "unknown question_type": ([ARTICLE], [dict(QUERY, question_type="summary_query")]),
        }
        for message, (corpus, queries) in cases.items():
            with self.subTest(message), self.assertRaisesRegex(ValueError, message):
                prep.build(corpus, queries)


class ConsumerContractTests(unittest.TestCase):
    def test_questions_csv_is_read_by_qa_run_and_the_judge_type_lookup(self):
        blob = prep.build([ARTICLE, OTHER], [QUERY, NULL_QUERY])["questions.csv"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "questions.csv"
            path.write_bytes(blob)
            qa_spec = importlib.util.spec_from_file_location("qa_run_c", ROOT / "reproduce/research/qa_run.py")
            qa = importlib.util.module_from_spec(qa_spec)
            qa_spec.loader.exec_module(qa)
            rows = qa.load_questions(path)
            # Same lookup Step_2_evaluate builds from --queryset.
            with open(path, newline="", encoding="utf-8") as f:
                label_of_type = {r["Question"]: r.get("Type", "?") for r in csv.DictReader(f)}
        self.assertEqual([(r["question"], r["gold"]) for r in rows],
                         [(QUERY["query"], "Yes"), (NULL_QUERY["query"], "Insufficient information.")])
        self.assertEqual(label_of_type[QUERY["query"]], "inference")


class CliTests(unittest.TestCase):
    def test_write_is_deterministic_lf_and_check_detects_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, out = Path(tmp) / "raw", Path(tmp) / "out"
            raw.mkdir()
            write_raw(raw, [ARTICLE, OTHER], [QUERY, NULL_QUERY])
            self.assertEqual(run("--raw", str(raw), "--out", str(out)), 0)
            first = {p.name: p.read_bytes() for p in out.iterdir()}
            self.assertFalse(any(b"\r" in blob for blob in first.values()))
            self.assertEqual(run("--raw", str(raw), "--out", str(out), "--check"), 0)

            write_raw(raw, [ARTICLE, dict(OTHER, body="Edited body.")], [QUERY, NULL_QUERY])
            self.assertEqual(run("--raw", str(raw), "--out", str(out), "--check"), 1)
            self.assertEqual(run("--raw", str(raw), "--out", str(out)), 1)  # refuses
            self.assertEqual({p.name: p.read_bytes() for p in out.iterdir()}, first)
            self.assertEqual(run("--raw", str(raw), "--out", str(out), "--force"), 0)
            self.assertNotEqual((out / "docs.jsonl").read_bytes(), first["docs.jsonl"])

    def test_pinned_hashes_reject_changed_raw_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_raw(Path(tmp), [ARTICLE], [QUERY])
            with self.assertRaisesRegex(ValueError, "pinned"):
                prep.generate(Path(tmp))


if __name__ == "__main__":
    unittest.main()
