"""The three LiHua ablation v2 switches on a real MiniRAG index (fake LLM, fake embeddings):
MINIRAG_CHUNK_FUSION=bm25, MINIRAG_DROP_ENTITIES=1, MINIRAG_NO_GRAPH=1."""

import asyncio
import contextlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

NAMES = "ABCDEFGH"
TOPICS = ["solar panels", "river ferry", "chess club", "bakery oven", "violin lessons", "garden fence",
          "bike repair", "tax forms"]
TEXTS = [f"Title: Note {n}\n\nENT_{n} talked with PARTNER_{n} about the {t}. ENT_{n} said the {t} needs work."
         for n, t in zip(NAMES, TOPICS)]
QUESTIONS = ["What did ENT_A say about solar panels?", "Who discussed the chess club with ENT_C?",
             "What needs work according to ENT_F?", "Did PARTNER_H mention tax forms?"]
SHARED = {"MINIRAG_ANSWER_TYPE_FIX": "1", "MINIRAG_PATH2CHUNK_FIX": "0", "MINIRAG_CHUNK_CUT": ""}


async def extract_llm(prompt, system_prompt=None, history_messages=[], **kwargs):
    if history_messages:
        return "<|COMPLETE|>"
    n = re.search(r"ENT_(\w)", prompt).group(1)
    return (f'("entity"<|>"ENT_{n}"<|>"PERSON"<|>"Person {n}")##'
            f'("entity"<|>"PARTNER_{n}"<|>"PERSON"<|>"Partner of {n}")##'
            f'("relationship"<|>"ENT_{n}"<|>"PARTNER_{n}"<|>"talked"<|>"talk"<|>5)<|COMPLETE|>')


class QueryLLM:
    def __init__(self):
        self.calls = []

    async def __call__(self, prompt, system_prompt=None, history_messages=[], **kwargs):
        self.calls.append(prompt)
        name = (re.findall(r"_(\w)\b", prompt.split("Query:")[-1]) or ["A"])[0]
        return json.dumps({"answer_type_keywords": ["PERSON"], "entities_from_query": [f"ENT_{name}"]})


async def embed(texts):
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


def split(context):
    entities, sources = context.split("-----Sources-----")
    return entities, sources


class SwitchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        index = Path(cls.tmp.name) / "index"
        with contextlib.redirect_stdout(io.StringIO()):
            asyncio.run(rag_at(index, extract_llm).ainsert(TEXTS))
        cls.index = index

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def contexts(self, env, llm=None):
        """Context and context-log record per question under one switch setting."""
        from minirag.base import QueryParam

        log = Path(self.tmp.name) / f"log_{abs(hash(json.dumps(env, sort_keys=True)))}.jsonl"
        log.unlink(missing_ok=True)
        full = SHARED | {"MINIRAG_CHUNK_FUSION": "", "MINIRAG_DROP_ENTITIES": "", "MINIRAG_NO_GRAPH": "",
                         "MINIRAG_CONTEXT_LOG": str(log)} | env
        with patch.dict(os.environ, full), contextlib.redirect_stdout(io.StringIO()):
            rag = rag_at(self.index, llm or QueryLLM())
            out = [asyncio.run(rag.aquery(q, param=QueryParam(mode="mini", only_need_context=True, top_k=6)))
                   for q in QUESTIONS]
        records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
        return out, {r["query"]: r for r in records}

    def test_bm25_ranks_sources_by_bm25_alone(self):
        from minirag import operate

        ctx, log = self.contexts({"MINIRAG_CHUNK_FUSION": "bm25"})
        rag = rag_at(self.index, QueryLLM())
        for q in QUESTIONS:
            expected = operate._bm25_index(rag.text_chunks).rank(q, 3)
            self.assertEqual(log[q]["ranked_ids"], expected)
            self.assertEqual(log[q]["bm25_ids"], expected)
        # It is a real change of ranking on this fixture, not a coincidence of a tiny index.
        _, vec = self.contexts({"MINIRAG_CHUNK_FUSION": "vector"})
        self.assertNotEqual([log[q]["ranked_ids"] for q in QUESTIONS], [vec[q]["ranked_ids"] for q in QUESTIONS])

    def test_drop_entities_keeps_sources_byte_identical_to_b2(self):
        b2, _ = self.contexts({"MINIRAG_CHUNK_FUSION": "vector_bm25"})
        noent, _ = self.contexts({"MINIRAG_CHUNK_FUSION": "vector_bm25", "MINIRAG_DROP_ENTITIES": "1"})
        checked = 0
        for full, dropped in zip(b2, noent):
            self.assertEqual(full is None, dropped is None)  # early exit unchanged
            if full is None:
                continue
            self.assertEqual(split(full)[1], split(dropped)[1])
            self.assertIn("entity,score,description", split(dropped)[0])
            self.assertNotIn("ENT_", split(dropped)[0])
            self.assertIn("ENT_", split(full)[0])
            checked += 1
        self.assertGreater(checked, 0)

    def test_no_graph_matches_b2_sources_without_parser_or_graph(self):
        b2, _ = self.contexts({"MINIRAG_CHUNK_FUSION": "vector_bm25"})
        llm = QueryLLM()
        nograph, log = self.contexts({"MINIRAG_NO_GRAPH": "1"}, llm)
        self.assertEqual(llm.calls, [])  # no keyword parser call
        checked = 0
        for q, full, ng in zip(QUESTIONS, b2, nograph):
            self.assertIsNotNone(ng)  # never exits early on the graph
            self.assertEqual(log[q]["fusion"], "no_graph")
            self.assertEqual(log[q]["graph_ids"], [])
            self.assertNotIn("ENT_", split(ng)[0].split("```csv")[1])
            if full is not None:
                self.assertEqual(split(full)[1], split(ng)[1])
                checked += 1
        self.assertGreater(checked, 0)

    def test_defaults_and_unknown_values(self):
        unset, _ = self.contexts({})
        empty, _ = self.contexts({"MINIRAG_DROP_ENTITIES": "", "MINIRAG_NO_GRAPH": ""})
        self.assertEqual(unset, empty)
        with self.assertRaises(ValueError):
            self.contexts({"MINIRAG_CHUNK_FUSION": "bm25_only"})


if __name__ == "__main__":
    unittest.main()
