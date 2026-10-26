"""Phases A-C must send the same LLM calls and return the same answers as
MiniRAG's own rag.aquery, on a real MiniRAG index (fake LLM, fake embeddings)."""

import asyncio
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


if __name__ == "__main__":
    unittest.main()
