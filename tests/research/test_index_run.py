"""Offline tests for index_run.py: guards, request tracing, and kill-then-resume
on a real MiniRAG instance with a fake LLM and fake embeddings."""

import argparse
import asyncio
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("index_run", ROOT / "reproduce/research/index_run.py")
ir = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ir)
import llm_trace  # noqa: E402  (index_run put reproduce/research on sys.path)


def doc(name):
    text = f"Title: {name}\nSource: Wire\nPublished: May 1, 2023 (2023-05-01T00:00:00+00:00)\n" \
           f"Category: business\n\nENT_{name} announced a merger with PARTNER_{name}."
    return {"doc_id": f"https://example.com/{name}", "minirag_doc_id": ir.hashlib.md5(text.encode()).hexdigest(),
            "text": text}


DOCS = [doc(n) for n in ("A", "B", "C")]
for d in DOCS:
    d["minirag_doc_id"] = "doc-" + d["minirag_doc_id"]


class FakeLLM:
    def __init__(self, fail_on=None):
        self.fail_on, self.extracted = fail_on, []

    async def __call__(self, prompt, system_prompt=None, history_messages=[], **kwargs):
        if history_messages:  # gleaning turn
            return "<|COMPLETE|>"
        name = re.search(r"ENT_(\w)", prompt).group(1)
        self.extracted.append(name)
        if name == self.fail_on:
            raise RuntimeError("killed mid-batch")
        return (f'("entity"<|>"ENT_{name}"<|>"ORGANIZATION"<|>"Company {name}")##'
                f'("entity"<|>"PARTNER_{name}"<|>"ORGANIZATION"<|>"Partner of {name}")##'
                f'("relationship"<|>"ENT_{name}"<|>"PARTNER_{name}"<|>"merger"<|>"merger"<|>5)<|COMPLETE|>')


def factory(llm):
    from minirag import MiniRAG
    from minirag.utils import EmbeddingFunc

    async def embed(texts):
        return np.array([[float((hash(t) >> s) & 255) + 1 for s in range(0, 64, 8)] for t in texts])

    return lambda workdir: MiniRAG(working_dir=workdir, llm_model_func=llm, llm_model_max_async=4,
                                   embedding_func=EmbeddingFunc(embedding_dim=8, max_token_size=1000, func=embed))


def identity(chunks):
    return {"docs_jsonl_sha256": "x", "selected_doc_ids_sha256": "y", "settings": {"s": 1},
            "source_sha256": "z", "expected": {"chunks": len(chunks)}}


def run_index(workdir, llm, resume=False, ident=None):
    chunks = ir.chunk_map(DOCS, ir.index_settings())
    args = argparse.Namespace(workingdir=workdir, resume=resume, batch_docs=1)
    with contextlib.redirect_stdout(io.StringIO()):
        return asyncio.run(ir.run_index(args, DOCS, factory(llm), ident or identity(chunks), chunks)), chunks


class GuardTests(unittest.TestCase):
    def test_workingdir_must_be_a_new_multihop_index_dir(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp) / "indexes"
            root.mkdir()
            for bad in (Path(tmp) / "LiHua-World-qwen-modal", root / "LiHua-World-x", root / "other"):
                with self.assertRaisesRegex(ValueError, "direct child"):
                    ir.check_workingdir(bad, False, root)
            ok = root / "multihop_rag-qwen-pilot30"
            self.assertEqual(ir.check_workingdir(ok, False, root), ok.resolve())
            ok.mkdir()
            with self.assertRaisesRegex(ValueError, "already exists"):
                ir.check_workingdir(ok, False, root)
            with self.assertRaisesRegex(ValueError, "Nothing to resume"):
                ir.check_workingdir(ok, True, root)
            # Another dataset gets its own prefix and cannot reach MultiHop's directories.
            self.assertEqual(ir.check_workingdir(root / "2wiki-qwen-pool500", False, root, prefix="2wiki-"),
                             (root / "2wiki-qwen-pool500").resolve())
            with self.assertRaisesRegex(ValueError, "direct child"):
                ir.check_workingdir(root / "multihop_rag-x", False, root, prefix="2wiki-")

    def test_refuses_gemini_as_indexer(self):
        gemini = "https://generativelanguage.googleapis.com/v1beta/openai/"
        for env, model in (({"GEMINI_API_BASE": gemini}, "minirag-slm"), ({}, "minirag-slm"),
                           ({"GEMINI_API_BASE": "https://x.modal.run/v1"}, "gemini-flash-lite-latest")):
            with patch.dict(os.environ, env, clear=False):
                if "GEMINI_API_BASE" not in env:
                    os.environ.pop("GEMINI_API_BASE", None)
                with self.assertRaises(ir.WrongBackend):
                    ir.require_slm_backend(model)
        with patch.dict(os.environ, {"GEMINI_API_BASE": "https://x.modal.run/v1"}):
            ir.require_slm_backend("minirag-slm")

    def test_pilot_selection_is_seeded_and_keeps_file_order(self):
        docs = [{"doc_id": f"u{i:03d}"} for i in range(100)]
        a = ir.select_docs(docs, "pilot", 30, 13)
        self.assertEqual(a, ir.select_docs(docs, "pilot", 30, 13))
        self.assertEqual(a, sorted(a, key=lambda d: d["doc_id"]))
        self.assertEqual(len(a), 30)

    def test_reconcile_drops_chunks_of_unfinished_batches(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            chunks = {"chunk-a": ("doc-A", "x"), "chunk-c": ("doc-C", "y")}
            (Path(tmp) / "extracted_chunks.json").write_text(json.dumps(["chunk-a", "chunk-c"]))
            status = {"doc-A": {"status": "processed"}, "doc-C": {"status": "processed"}}
            (Path(tmp) / "kv_store_doc_status.json").write_text(json.dumps(status))
            self.assertEqual(ir.reconcile_checkpoint(tmp, chunks, {"doc-A"}), (1, 1))
            self.assertEqual(json.loads((Path(tmp) / "extracted_chunks.json").read_text()), ["chunk-a"])
            self.assertEqual(list(json.loads((Path(tmp) / "kv_store_doc_status.json").read_text())), ["doc-A"])

    def test_annotator_finds_phase_and_chunk(self):
        annotate = ir.annotator({"chunk-1": ("doc-A", "alpha body"), "chunk-2": ("doc-B", "beta body")})
        first = [{"role": "user", "content": "extract from: beta body"}]
        self.assertEqual(annotate(first), {"phase": "extract", "chunk_id": "chunk-2"})
        glean = first + [{"role": "assistant", "content": "..."}, {"role": "user", "content": "MANY missed"}]
        self.assertEqual(annotate(glean), {"phase": "glean", "chunk_id": "chunk-2"})
        # A tail chunk inside the previous chunk's overlap: the longer chunk is the one asked about.
        annotate = ir.annotator({"chunk-full": ("doc-A", "alpha body tail"), "chunk-tail": ("doc-A", "body tail")})
        self.assertEqual(annotate([{"role": "user", "content": "x alpha body tail"}])["chunk_id"], "chunk-full")
        self.assertEqual(annotate([{"role": "user", "content": "x body tail"}])["chunk_id"], "chunk-tail")


class TraceTests(unittest.TestCase):
    def test_records_response_metadata_without_secrets(self):
        from minirag.llm import gemini

        async def create(**kwargs):
            return SimpleNamespace(model="minirag-slm", usage=SimpleNamespace(prompt_tokens=5, completion_tokens=7),
                                   choices=[SimpleNamespace(finish_reason="length",
                                                            message=SimpleNamespace(content="out"))])

        fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        original = gemini._client
        try:
            gemini._client = lambda key, base_url=None: fake_client
            llm_trace.install()
            records = []

            async def go():
                with llm_trace.trace(records.append, lambda m: {"phase": "extract"}):
                    await gemini._client("SECRET-KEY").chat.completions.create(
                        model="minirag-slm", messages=[{"role": "user", "content": "hi"}], max_tokens=1024)

            asyncio.run(go())
        finally:
            gemini._client = original
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertEqual((r["finish_reason"], r["max_tokens"], r["response_model"], r["completion_tokens"],
                          r["response_text"], r["phase"]), ("length", 1024, "minirag-slm", 7, "out", "extract"))
        self.assertNotIn("SECRET-KEY", json.dumps(r))


class ResumeTests(unittest.TestCase):
    def test_kill_then_resume_never_reextracts_finished_batches(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            workdir = Path(tmp) / "multihop_rag-test"
            killed = FakeLLM(fail_on="C")
            with self.assertRaises(RuntimeError):
                run_index(workdir, killed)
            self.assertEqual(killed.extracted, ["A", "B", "C"])
            manifest = json.loads((workdir / "index_manifest.json").read_text())
            self.assertEqual(manifest["status"], "partial")

            resumed = FakeLLM()
            code, chunks = run_index(workdir, resumed, resume=True)
            self.assertEqual(code, 0)
            self.assertEqual(resumed.extracted, ["C"])
            manifest = json.loads((workdir / "index_manifest.json").read_text())
            self.assertEqual(manifest["status"], "completed")
            self.assertTrue(all(manifest["verification"].values()), manifest["verification"])
            self.assertEqual((manifest["counts"]["docs"], manifest["counts"]["chunks"], manifest["counts"]["nodes"]),
                             (3, len(chunks), 6))

    def test_resume_refuses_a_changed_identity(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            workdir = Path(tmp) / "multihop_rag-test"
            run_index(workdir, FakeLLM())
            chunks = ir.chunk_map(DOCS, ir.index_settings())
            with self.assertRaisesRegex(ValueError, "refusing to resume"):
                run_index(workdir, FakeLLM(), resume=True, ident=identity(chunks) | {"source_sha256": "changed"})


if __name__ == "__main__":
    unittest.main()
