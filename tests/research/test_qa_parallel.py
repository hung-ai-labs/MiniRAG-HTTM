"""Offline concurrency, resume and real query-prompt contract tests."""

import ast
import asyncio
from contextlib import redirect_stdout
from dataclasses import make_dataclass
import csv
import importlib.util
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from functools import wraps

ROOT = Path(__file__).resolve().parents[2]
# Allows testing a staged patch against the original query implementation.
SOURCE = Path(os.environ.get("MINIRAG_TEST_SOURCE_ROOT", str(ROOT)))
spec = importlib.util.spec_from_file_location("qa_run_tested", ROOT / "reproduce/research/qa_run.py")
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)


def actual_function(path, name, namespace):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    node = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[name]


limiter = actual_function(ROOT / "minirag/utils.py", "limit_async_func_call", {"asyncio": asyncio, "wraps": wraps})


async def context_fixture(*args):
    await asyncio.sleep(0)
    return "Fixed context: " + args[2]


async def keyword_fixture(func, prompt):
    return await func(prompt)


mini_query = actual_function(SOURCE / "minirag/operate.py", "minirag_query", {
    "Union": object, "BaseGraphStorage": object, "BaseVectorStorage": object,
    "BaseKVStorage": dict, "TextChunkSchema": str, "QueryParam": object,
    "os": os, "json": json, "json_repair": json,
    "PROMPTS": runpy.run_path(str(SOURCE / "minirag/prompt.py"))["PROMPTS"],
    "_keyword_llm": keyword_fixture, "_build_mini_query_context": context_fixture,
})


class FakeRag:
    def __init__(self, fail=(), blocking=False, limit=8):
        self.fail = set(fail)
        self.blocking = blocking
        self.active = 0
        self.peak = 0
        self.requests = []
        self.questions = []
        self.entered = asyncio.Event()
        self.force_out_of_order = False
        self.q1_finished = asyncio.Event()
        self.llm_model_func = limiter(limit)(self.complete)

    async def complete(self, prompt, **kwargs):
        self.requests.append({"prompt": prompt, "kwargs": kwargs})
        await asyncio.sleep(0.001)
        if kwargs.get("system_prompt"):
            return "Answer: " + prompt + "\n"
        return json.dumps({"answer_type_keywords": ["person"], "entities_from_query": ["Alice"]})

    async def aquery(self, question, param):
        self.active += 1
        self.peak = max(self.peak, self.active)
        self.questions.append(question)
        self.entered.set()
        try:
            if self.blocking:
                await asyncio.Event().wait()
            if question == "q0" and self.force_out_of_order:
                await self.q1_finished.wait()
            await asyncio.sleep(0.015 if question == "q0" else 0.001)
            if question in self.fail:
                raise RuntimeError("secret-token-must-not-be-recorded")
            graph = SimpleNamespace(get_types=self.get_types)
            return await mini_query(question, graph, None, None, None, None, None, None, param,
                                    {"llm_model_func": self.llm_model_func})
        finally:
            if question == "q1":
                self.q1_finished.set()
            self.active -= 1

    async def get_types(self):
        return ["person", "place"], None


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.index = self.base / "source-index"
        self.index.mkdir()
        (self.index / "fixture.json").write_text('{"graph": "frozen"}', encoding="utf-8")
        self.csv = self.base / "questions.csv"
        self.write_rows([("q0", "a"), ("q1", "b"), ("duplicate", "c"), ("duplicate", "d")])
        self.args = SimpleNamespace(questions=self.csv, workingdir=self.index, run_dir=self.base / "run",
                                    limit=None, concurrency=8, llm_max_async=8, resume=False)
        self.param = SimpleNamespace(mode="mini", only_need_context=False, response_type="Multiple Paragraphs")
        self.config = {"model": "fixture-qwen", "query_param": {"mode": "mini"}}
        self.rag = FakeRag()
        self.factories = 0
        self.snapshot = None

    def write_rows(self, rows):
        with self.csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Question", "Gold Answer"])
            writer.writerows(rows)

    def factory(self, snapshot):
        asyncio.get_running_loop()
        self.factories += 1
        self.snapshot = snapshot
        return self.rag

    async def run_qa(self):
        return await qa.run_qa(self.args, self.factory, self.param, self.config)

    def records(self):
        return [json.loads(line) for line in (self.args.run_dir / "generation.jsonl").read_text().splitlines()]

    async def test_bounded_out_of_order_duplicates_and_ordered_export(self):
        self.args.concurrency = 2
        self.rag.force_out_of_order = True
        source_before = qa.index_hash(self.index)
        metrics = await self.run_qa()
        self.assertEqual(self.factories, 1)
        self.assertEqual(self.rag.peak, 2)
        self.assertNotEqual(self.records()[0]["query_id"], 0)
        self.assertEqual({r["query_id"] for r in self.records()}, {0, 1, 2, 3})
        with (self.args.run_dir / "answers.csv").open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual([r["Question"] for r in rows], ["q0", "q1", "duplicate", "duplicate"])
        self.assertEqual([r["Gold Answer"] for r in rows], ["a", "b", "c", "d"])
        self.assertTrue(all("\n" not in r["minirag"] for r in rows))
        self.assertEqual(metrics["n_ok"], 4)
        self.assertGreater(metrics["questions_per_minute"], 0)
        self.assertEqual(qa.index_hash(self.index), source_before)
        self.assertNotEqual(self.snapshot, self.index)
        self.assertTrue(all(len(r["llm_calls"]) == 2 for r in self.records()))

    async def test_real_query_request_content_equal_at_1_and_8(self):
        self.args.concurrency = 1
        await self.run_qa()
        serial = sorted(json.dumps(r, sort_keys=True) for r in self.rag.requests)
        self.args.run_dir = self.base / "parallel"
        self.args.concurrency = 8
        self.rag = FakeRag()
        await self.run_qa()
        parallel = sorted(json.dumps(r, sort_keys=True) for r in self.rag.requests)
        self.assertEqual(serial, parallel)

    async def test_failed_rows_retry_only_and_success_is_not_duplicated(self):
        self.rag = FakeRag(fail={"q1"})
        first = await self.run_qa()
        self.assertEqual(first["status"], "partial")
        self.assertFalse((self.args.run_dir / "answers.csv").exists())
        self.assertNotIn("secret-token", (self.args.run_dir / "generation.jsonl").read_text())
        self.args.resume = True
        self.args.concurrency = 1
        self.rag = FakeRag()
        second = await self.run_qa()
        self.assertEqual(self.rag.questions, ["q1"])
        self.assertEqual(second["n_ok"], 4)
        self.assertEqual([r["attempt"] for r in self.records() if r["query_id"] == 1], [1, 2])
        count = len(self.records())
        self.rag = FakeRag()
        await self.run_qa()
        self.assertEqual(self.rag.questions, [])
        self.assertEqual(len(self.records()), count)

    async def test_cancelled_run_can_resume_and_releases_lock(self):
        self.rag = FakeRag(blocking=True)
        task = asyncio.create_task(self.run_qa())
        await self.rag.entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(self.records())
        self.assertTrue(all(r["status"] == "cancelled" for r in self.records()))
        self.args.resume = True
        self.rag = FakeRag()
        metrics = await self.run_qa()
        self.assertEqual(metrics["n_ok"], 4)

    async def test_resume_rejects_input_config_source_and_snapshot_changes(self):
        await self.run_qa()
        self.args.resume = True
        original = self.csv.read_bytes()
        self.csv.write_bytes(original + b"\n")
        with self.assertRaisesRegex(ValueError, "changed"):
            await self.run_qa()
        self.csv.write_bytes(original)
        self.config["model"] = "different"
        with self.assertRaisesRegex(ValueError, "changed"):
            await self.run_qa()
        self.config["model"] = "fixture-qwen"
        source = self.index / "fixture.json"
        old = source.read_text()
        source.write_text("changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            await self.run_qa()
        source.write_text(old)
        (self.args.run_dir / "index_snapshot/fixture.json").write_text("changed")
        with self.assertRaisesRegex(ValueError, "snapshot changed"):
            await self.run_qa()

    async def test_torn_tail_repaired_but_complete_corruption_rejected(self):
        await self.run_qa()
        path = self.args.run_dir / "generation.jsonl"
        original = path.read_bytes()
        path.write_bytes(original + b'{"query_id":')
        self.args.resume = True
        await self.run_qa()
        self.assertEqual(path.read_bytes(), original)
        path.write_bytes(original + b"bad-json\n")
        with self.assertRaises(json.JSONDecodeError):
            await self.run_qa()

    async def test_existing_directory_and_nested_run_are_rejected(self):
        self.args.run_dir.mkdir()
        with self.assertRaises(FileExistsError):
            await self.run_qa()
        self.args.run_dir = self.index / "run"
        with self.assertRaisesRegex(ValueError, "contain"):
            await self.run_qa()

    async def test_duplicate_success_in_checkpoint_rejected(self):
        await self.run_qa()
        rec = self.records()[0]
        rec["attempt"] += 1
        with (self.args.run_dir / "generation.jsonl").open("a") as f:
            f.write(json.dumps(rec) + "\n")
        self.args.resume = True
        with self.assertRaisesRegex(ValueError, "Duplicate successful"):
            await self.run_qa()

    async def test_checkpoint_disk_failure_stops_remaining_queries(self):
        self.write_rows([(f"q{i}", "gold") for i in range(30)])
        self.args.concurrency = 2
        original_factory = self.factory
        def factory(snapshot):
            rag = original_factory(snapshot)
            # Setup is complete; fail only durability writes for the live queue.
            def full_disk(_):
                raise OSError("disk full")
            self.fsync_patch = patch.object(qa.os, "fsync", full_disk)
            self.fsync_patch.start()
            return rag
        try:
            with self.assertRaises(OSError):
                await qa.run_qa(self.args, factory, self.param, self.config)
        finally:
            self.fsync_patch.stop()
        self.assertLess(len(self.rag.questions), 30)
        self.assertFalse((self.args.run_dir / "answers.csv").exists())

    async def test_warmup_is_separate_from_measured_answers(self):
        self.args.warmup = 2
        result = await self.run_qa()
        self.assertEqual(result["warmup_questions"], 2)
        self.assertEqual(len(self.rag.questions), 6)
        self.assertEqual(len(self.records()), 4)
        self.assertGreater(result["warmup_wall_s"], 0)
        self.assertGreater(result["query_phase_wall_s"], 0)

    async def test_run_lock_blocks_a_second_writer(self):
        await self.run_qa()
        self.args.resume = True
        with qa.run_lock(self.args.run_dir):
            with self.assertRaises(OSError):
                await self.run_qa()


class LimiterTests(unittest.IsolatedAsyncioTestCase):
    async def test_exception_releases_capacity(self):
        @limiter(1)
        async def call(fail=False):
            if fail:
                raise RuntimeError()
            return "ok"
        with self.assertRaises(RuntimeError):
            await call(True)
        self.assertEqual(await asyncio.wait_for(call(), 0.2), "ok")

    async def test_cancellation_releases_capacity(self):
        entered = asyncio.Event()
        @limiter(1)
        async def call(block=False):
            if block:
                entered.set()
                await asyncio.Event().wait()
            return "ok"
        task = asyncio.create_task(call(True))
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(await asyncio.wait_for(call(), 0.2), "ok")

    async def test_cancelled_waiter_does_not_consume_or_release_slot(self):
        gate = asyncio.Event()
        entered = asyncio.Event()
        active = 0
        peak = 0
        @limiter(1)
        async def call():
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            entered.set()
            await gate.wait()
            active -= 1
        holder = asyncio.create_task(call())
        await entered.wait()
        waiter = asyncio.create_task(call())
        await asyncio.sleep(0)
        waiter.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiter
        gate.set()
        await holder
        await asyncio.gather(*(call() for _ in range(10)))
        self.assertEqual(peak, 1)


class SetupTests(unittest.TestCase):
    def test_build_rag_preserves_default_and_accepts_override(self):
        with tempfile.TemporaryDirectory() as directory:
            ns = {"os": os, "_resolve_api_keys": lambda: ["fake"],
                  "EmbeddingFunc": lambda **kw: kw, "DEFAULT_EMBEDDING_DIM": 384,
                  "gemini_embed": None, "gemini_complete": None,
                  "MiniRAG": lambda **kw: kw}
            build = actual_function(ROOT / "reproduce/gemini_common.py", "build_rag", ns)
            args = SimpleNamespace(workingdir=directory, model="fake", embedmodel="remote")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(build(args)["llm_model_max_async"], 8)
                self.assertEqual(build(args, llm_max_async=16)["llm_model_max_async"], 16)
            for invalid in (0, -1, True, 1.5):
                with self.assertRaises(ValueError):
                    build(args, llm_max_async=invalid)

    def test_modal_environment_is_scoped_and_configured_mode_does_not_change_it(self):
        with patch.dict(os.environ, {"MINIRAG_SLM_URL": "https://fixture.modal.run",
                                   "MINIRAG_SLM_KEY": "secret"}, clear=True):
            qa.configure_environment(SimpleNamespace(backend="modal"))
            self.assertEqual(os.environ["GEMINI_API_BASE"], "https://fixture.modal.run/v1")
            self.assertEqual(os.environ["GEMINI_API_KEY_ONLY"], "secret")
            self.assertEqual(os.environ["MINIRAG_MAX_TOKENS"], "1024")
        with patch.dict(os.environ, {"GEMINI_TPM": "3000"}, clear=True):
            qa.configure_environment(SimpleNamespace(backend="configured"))
            self.assertEqual(dict(os.environ), {"GEMINI_TPM": "3000"})

    def test_cli_defaults_and_invalid_limits(self):
        p = qa.parser()
        args = p.parse_args(["--questions", "q.csv", "--workingdir", "index", "--run-dir", "run"])
        self.assertEqual((args.concurrency, args.llm_max_async), (4, 4))
        with redirect_stdout(io.StringIO()), patch("sys.stderr", new=io.StringIO()):
            with self.assertRaises(SystemExit):
                p.parse_args(["--questions", "q.csv", "--workingdir", "index", "--run-dir", "run", "--concurrency", "0"])

    def test_scientific_manifest_excludes_secrets_and_records_serving_setup(self):
        Query = make_dataclass("Query", [("mode", str)])
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "serving.json"
            declared = {"model_revision": "a" * 40, "vllm_version": "0.11.0",
                        "gpu": "A10G", "dtype": "bfloat16", "max_model_len": 32768,
                        "sampling": {"temperature": 0.7}, "api_key": "do-not-store"}
            config.write_text(json.dumps(declared))
            args = SimpleNamespace(model="fixture", embedmodel="local", backend="modal", serving_config=config)
            with patch.dict(os.environ, {"MINIRAG_SLM_KEY": "secret-key",
                                        "MINIRAG_SLM_PASSWORD": "secret-password",
                                        "MINIRAG_SLM_URL": "https://private-endpoint.modal.run",
                                        "GEMINI_API_BASE": "https://private-endpoint.modal.run/v1"}, clear=True):
                result = qa.scientific_settings(args, Query("mini"))
            text = json.dumps(result)
            for secret in ("secret-key", "secret-password", "private-endpoint", "do-not-store"):
                self.assertNotIn(secret, text)
            self.assertEqual(result["serving_config"]["model_revision"], "a" * 40)

    def test_mutable_keyword_cache_is_rejected(self):
        with patch.dict(os.environ, {"MINIRAG_KW_CACHE": "cache.jsonl"}, clear=True):
            with self.assertRaisesRegex(ValueError, "frozen keyword cache"):
                qa.configure_environment(SimpleNamespace(backend="configured"))

    def test_benchmark_preparation_is_offline_and_conservative(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            questions = directory / "q.csv"
            with questions.open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Question", "Gold Answer"])
                writer.writerows([(str(i), "gold") for i in range(100)])
            output = directory / "new-benchmark"
            command = [sys.executable, "-B", str(ROOT / "reproduce/research/benchmark_qa.py"),
                       "--questions", str(questions), "--workingdir", str(directory / "index"),
                       "--run-dir", str(output)]
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            prepared = json.loads(result.stdout)
            self.assertFalse(prepared["execute"])
            self.assertEqual([c[c.index("--concurrency") + 1] for c in prepared["commands"]], ["1", "2", "4"])
            self.assertFalse(output.exists())
            result = subprocess.run(command + ["--levels", "1", "4", "8", "16"], capture_output=True, text=True, check=True)
            self.assertEqual(len(json.loads(result.stdout)["commands"]), 4)
            # Refuse to spend money without declaring the serving setup.
            refused = subprocess.run(command + ["--execute"], capture_output=True, text=True)
            self.assertNotEqual(refused.returncode, 0)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
