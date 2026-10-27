"""Phases A-C must send the same LLM calls and return the same answers as
MiniRAG's own rag.aquery, on a real MiniRAG index (fake LLM, fake embeddings)."""

import asyncio
import argparse
import contextlib
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import subprocess
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "reproduce"))
spec = importlib.util.spec_from_file_location("phased_qa", ROOT / "reproduce/research/phased_qa.py")
pq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pq)

NAMES = ("A", "B", "C")
TEXTS = [f"Title: Deal {n}\nSource: Wire\n\nENT_{n} announced a merger with PARTNER_{n} in May." for n in NAMES]
ROWS = [{"query_id": f"mhr-000{i}", "Question": q, "Gold Answer": "Yes", "Type": "inference"}
        for i, q in enumerate(["Who merged with ENT_A?", "Did PARTNER_B announce a merger?", "What did ENT_C do?"])]


async def extract_llm(prompt, system_prompt=None, history_messages=[], **kwargs):
    if history_messages:
        return "<|COMPLETE|>"
    n = next(n for n in NAMES if f"ENT_{n}" in prompt)
    return (f'("entity"<|>"ENT_{n}"<|>"ORGANIZATION"<|>"Company {n}")##'
            f'("entity"<|>"PARTNER_{n}"<|>"ORGANIZATION"<|>"Partner of {n}")##'
            f'("relationship"<|>"ENT_{n}"<|>"PARTNER_{n}"<|>"merger"<|>"merger"<|>5)<|COMPLETE|>')


class QueryLLM:
    """Keyword prompts get a fixed parse; answer calls are recorded and echoed as a hash."""

    def __init__(self):
        self.calls = []

    async def __call__(self, prompt, system_prompt=None, history_messages=[], **kwargs):
        self.calls.append((prompt, system_prompt))
        if system_prompt is None:
            name = next((n for n in NAMES if f"_{n}" in prompt.split("Query:")[-1]), "A")
            return json.dumps({"answer_type_keywords": ["ORGANIZATION"],
                               "entities_from_query": [f"ENT_{name}", f"PARTNER_{name}"]})
        return "ANSWER " + hashlib.sha256((prompt + system_prompt).encode()).hexdigest()[:12]


async def embed(texts):
    # Letter counts: similar strings get similar vectors, so retrieval finds something.
    out = []
    for t in texts:
        v = np.array([t.upper().count(ch) for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ_"], dtype=float) + 0.01
        out.append(v / np.linalg.norm(v))
    return np.array(out)


def rag_at(workdir, llm):
    from minirag import MiniRAG
    from minirag.utils import EmbeddingFunc
    Path(workdir).mkdir(parents=True, exist_ok=True)
    return MiniRAG(working_dir=str(workdir), llm_model_func=llm, llm_model_max_async=4,
                   embedding_func=EmbeddingFunc(embedding_dim=27, max_token_size=1000, func=embed))


class PhasedEquivalenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.index = Path(cls.tmp.name) / "index"
        with contextlib.redirect_stdout(io.StringIO()):
            asyncio.run(rag_at(cls.index, extract_llm).ainsert(TEXTS))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def check(self, config):
        from minirag.base import QueryParam

        mode = pq.MODE[config]
        work = Path(self.tmp.name) / config
        with patch.dict(os.environ, {}, clear=False), contextlib.redirect_stdout(io.StringIO()):
            # Reference: MiniRAG's own path (keyword cache in write mode, as amendment S2 runs it).
            pq.apply_env(config, 101, kw_cache=work / "ref_kw.jsonl" if mode == "mini" else None)
            ref_llm = QueryLLM()
            ref_rag = rag_at(pq.snapshot(work / "ref", self.index), ref_llm)
            ref_answers = [asyncio.run(ref_rag.aquery(r["Question"], param=QueryParam(mode=mode))) for r in ROWS]

            phased_llm = QueryLLM()
            kw = work / "kw.jsonl"
            if mode == "mini":
                pq.apply_env(config, 101, kw_cache=kw)
                asyncio.run(pq.keyword_phase(rag_at(pq.snapshot(work / "a", self.index), phased_llm), ROWS, kw))
            pq.apply_env(config, 101, kw_cache=kw if mode == "mini" else None, cache_only=True)
            asyncio.run(pq.context_phase(rag_at(pq.snapshot(work / "b", self.index), phased_llm), ROWS, mode,
                                         work / "contexts.jsonl"))
            contexts = pq.read_jsonl(work / "contexts.jsonl")
            answer_rag = rag_at(work / "c", phased_llm)
            asyncio.run(pq.answer_phase(answer_rag.llm_model_func, ROWS, contexts, mode, work / "answers.jsonl",
                                        QueryParam().response_type))
        got = pq.read_jsonl(work / "answers.jsonl")
        self.assertEqual([got[r["query_id"]]["answer"] for r in ROWS], ref_answers)
        self.assertEqual(sorted(phased_llm.calls, key=repr), sorted(ref_llm.calls, key=repr))
        self.assertTrue(any(c["status"] == "ok" for c in contexts.values()), "fixture must retrieve something")
        with open(work / "answers.csv", newline="", encoding="utf-8") as f:
            self.assertEqual([r["minirag"] for r in csv.DictReader(f)], ref_answers)
        return ref_llm.calls

    def test_mini_C0_matches_minirag(self):
        calls = self.check("C0")
        self.assertTrue(any(system for _, system in calls))  # answer calls happened

    def test_mini_C1_fusion_matches_minirag(self):
        self.check("C1")

    def test_naive_C3_matches_minirag(self):
        self.check("C3")

    def test_original_minirag_C_orig_matches_minirag(self):
        self.check("C_orig")

    def test_run_note_environment_is_what_apply_env_sets(self):
        self.assertEqual(pq.config_env("C1")["MINIRAG_CHUNK_FUSION"], "vector_bm25")
        self.assertEqual((pq.config_env("C_orig")["MINIRAG_ANSWER_TYPE_FIX"],
                          pq.config_env("C_orig")["MINIRAG_TRUNCATE_SOURCES"]), ("0", "0"))
        self.assertEqual(pq.config_env("C0")["MINIRAG_TRUNCATE_SOURCES"], "1")
        with patch.dict(os.environ, {}, clear=False):
            pq.apply_env("C_orig", 101)
            self.assertEqual({k: os.environ.get(k, "") for k in pq.config_env("C_orig")}, pq.config_env("C_orig"))
            pq.apply_env("C0", 101)  # switching back must restore the fixes
            self.assertEqual({k: os.environ.get(k, "") for k in pq.config_env("C0")}, pq.config_env("C0"))

    def test_context_overflow_is_recorded_not_fatal_and_other_errors_still_fail(self):
        import httpx
        import openai

        def error(message):
            return openai.BadRequestError(message, response=httpx.Response(
                400, request=httpx.Request("POST", "http://x")), body=None)

        async def overflow(prompt, system_prompt=None, **kwargs):
            raise error("This model's maximum context length is 32768 tokens. However, you requested 40000")

        async def other(prompt, system_prompt=None, **kwargs):
            raise error("invalid temperature")

        contexts = {r["query_id"]: {"status": "ok", "context": "ctx"} for r in ROWS}
        work = Path(self.tmp.name) / "overflow"
        work.mkdir()
        asyncio.run(pq.answer_phase(overflow, ROWS, contexts, "mini", work / "answers.jsonl", "x"))
        got = pq.read_jsonl(work / "answers.jsonl")
        self.assertEqual({(g["answer"], g["context_status"]) for g in got.values()}, {("", "context_overflow")})
        with self.assertRaises(openai.BadRequestError):
            asyncio.run(pq.answer_phase(other, ROWS, contexts, "mini", work / "other.jsonl", "x"))

    def test_context_phase_never_calls_the_llm(self):
        from minirag.base import QueryParam

        work = Path(self.tmp.name) / "forbid"
        with patch.dict(os.environ, {}, clear=False), contextlib.redirect_stdout(io.StringIO()):
            pq.apply_env("C0", 101, kw_cache=work / "empty_kw.jsonl", cache_only=True)
            rag = rag_at(pq.snapshot(work / "b", self.index), QueryLLM())
            with self.assertRaises(RuntimeError):  # keyword output missing -> refuse, never call
                asyncio.run(pq.context_phase(rag, ROWS[:1], "mini", work / "contexts.jsonl"))
        self.assertIs(rag.llm_model_func, pq._forbidden_llm)
        del QueryParam


class SharedRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        index, out = root / "2wiki-index", root / "run"
        index.mkdir(); out.mkdir()
        (index / "kv_store_text_chunks.json").write_text("{}")
        (index / "graph_chunk_entity_relation.graphml").write_text("fixture")
        protocol, serving, questions = root / "2wiki.md", root / "serving.json", root / "questions.csv"
        protocol.write_text("2Wiki reviewed conditions")
        serving.write_text(json.dumps({"model_revision": "a" * 40, "vllm_version": "0.11.0",
                                      "gpu": "A10G", "dtype": "bfloat16", "max_model_len": 32768,
                                      "sampling": {"temperature": 0.7}}))
        questions.write_text("query_id,Question,Gold Answer\n2wiki-1,Who?,Alice\n")
        self.args = argparse.Namespace(index=index, out=out, dataset_id="2wiki", seed=101,
                                       questions=questions, registration=protocol, serving_config=serving,
                                       llm_max_async=4)
        env = patch.dict(os.environ, {"GEMINI_API_BASE": "https://fixture.invalid/v1",
                                     "GEMINI_API_KEY_ONLY": "never-log-this-secret"})
        env.start(); self.addCleanup(env.stop)
        configure = patch.object(pq, "use_slm")
        configure.start(); self.addCleanup(configure.stop)

    def test_resume_records_dataset_without_endpoint_or_key_and_rejects_changed_inputs(self):
        pq.ensure_run_identity(self.args)
        pq.ensure_run_identity(self.args)
        raw = (self.args.out / "run_manifest.json").read_text()
        self.assertEqual(json.loads(raw)["dataset_id"], "2wiki")
        self.assertNotIn("fixture.invalid", raw)
        self.assertNotIn("never-log-this-secret", raw)
        self.args.questions.write_text("query_id,Question,Gold Answer\n2wiki-2,When?,Today\n")
        with self.assertRaisesRegex(ValueError, "changed"):
            pq.ensure_run_identity(self.args)

    def test_refuses_old_outputs_and_overlapping_index_paths(self):
        (self.args.out / "kw_s101.jsonl").write_text("{}")
        with self.assertRaisesRegex(ValueError, "no run manifest"):
            pq.ensure_run_identity(self.args)
        self.args.out = self.args.index / "nested"
        self.args.out.mkdir()
        with self.assertRaisesRegex(ValueError, "contain each other"):
            pq.ensure_run_identity(self.args)

    def test_refuses_a_declared_local_quantized_index(self):
        (self.args.index / "index_manifest.json").write_text(json.dumps({"quantization": "Q4_K_M"}))
        with self.assertRaisesRegex(ValueError, "Local Q4 index"):
            pq.ensure_run_identity(self.args)

    def test_changed_context_or_keyword_cache_cannot_resume_a_phase(self):
        manifest = self.args.out / "answer_manifest.json"
        pq.ensure_phase_identity(manifest, {"contexts_sha256": "original"})
        pq.ensure_phase_identity(manifest, {"contexts_sha256": "original"})
        with self.assertRaisesRegex(ValueError, "Phase input changed"):
            pq.ensure_phase_identity(manifest, {"contexts_sha256": "changed"})

    def test_plan_is_offline_and_passes_2wiki_paths_to_every_phase(self):
        command = [sys.executable, str(ROOT / "reproduce/research/run_phased_qa.py"),
                   "--dataset-id", "2wiki", "--index", str(self.args.index),
                   "--questions", str(self.args.questions), "--registration", str(self.args.registration),
                   "--serving-config", str(self.args.serving_config), "--out", str(self.args.out),
                   "--seed", "101", "--configs", "C0", "C1", "--llm-max-async", "4"]
        completed = subprocess.run(command, capture_output=True, text=True, check=True)
        result = json.loads(completed.stdout)
        self.assertFalse(result["execute"])
        self.assertEqual(len(result["commands"]), 5)
        for cmd in result["commands"]:
            self.assertEqual(cmd[cmd.index("--index") + 1], str(self.args.index.resolve()))
            self.assertEqual(cmd[cmd.index("--registration") + 1], str(self.args.registration.resolve()))
        self.assertEqual(list(self.args.out.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
