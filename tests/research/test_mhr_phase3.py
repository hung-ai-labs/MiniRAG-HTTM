"""Scientific equivalence and orchestration guards; fake LLM and local tiny index."""
import asyncio
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import csv
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from reproduce.research.mhr_phase3.common import DEFAULT_REPO, alive, load_repo, read_json, read_jsonl, run_lock, sha, write_json
from reproduce.research.mhr_phase3.shared_context import SharedContext, build_offline, paired_query, stable_log

pq = load_repo(DEFAULT_REPO)
spec = importlib.util.spec_from_file_location("original_phase_fixture", DEFAULT_REPO / "tests/research/test_phased_qa.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class SharedEquivalenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            fixture.PhasedEquivalenceTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixture.PhasedEquivalenceTests.tearDownClass()

    def execute(self, no_edges=False):
        async def scenario(folder):
            from minirag.base import QueryParam
            import minirag.operate as operate
            work = folder / "index"
            pq.snapshot(work, fixture.PhasedEquivalenceTests.index)
            rag = fixture.rag_at(work, fixture.QueryLLM())
            kw = folder / "keywords.jsonl"
            pq.apply_env("C0", 101, kw_cache=kw)
            await pq.keyword_phase(rag, fixture.ROWS, kw)
            rag.llm_model_func = lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM call"))
            if no_edges:
                async def empty(*args, **kwargs):
                    return []
                rag.relationships_vdb.query = empty
            expected = {}
            for config in ("C0", "C1"):
                log = folder / f"old_{config}.jsonl"
                pq.apply_env(config, 101, kw_cache=kw, cache_only=True, context_log=log)
                expected[config] = [await rag.aquery(r["Question"], param=QueryParam(mode="mini", only_need_context=True))
                                    for r in fixture.ROWS]
            adapter = SharedContext(operate)
            with adapter.installed():
                for i, row in enumerate(fixture.ROWS):
                    got, elapsed = await paired_query(rag, row, 101, kw, folder / "new", pq, adapter)
                    for config in ("C0", "C1"):
                        self.assertEqual(got[config]["context"], expected[config][i])
                        self.assertEqual(got[config]["status"], "no_context" if no_edges else "ok")
            self.assertEqual(adapter.prefix_calls, len(fixture.ROWS))
            self.assertEqual(adapter.reuses, len(fixture.ROWS))
            self.assertIs(operate._build_mini_query_context, adapter.original)
            for config in ("C0", "C1"):
                old_logs = read_jsonl(folder / f"old_{config}.jsonl", "query")
                new_logs = read_jsonl(folder / f"new/{config}_s101/context.jsonl", "query")
                self.assertEqual({q: stable_log(v) for q, v in old_logs.items()},
                                 {q: stable_log(v) for q, v in new_logs.items()})
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
            asyncio.run(scenario(Path(tmp)))

    def test_c0_c1_context_and_full_canonical_log_equal(self):
        self.execute()

    def test_no_edges_preserves_both_early_exits(self):
        self.execute(no_edges=True)

    def test_adapter_restored_after_exception(self):
        import minirag.operate as operate
        adapter = SharedContext(operate)
        with self.assertRaisesRegex(RuntimeError, "sentinel"):
            with adapter.installed():
                raise RuntimeError("sentinel")
        self.assertIs(operate._build_mini_query_context, adapter.original)

    def test_nested_adapter_rejected(self):
        import minirag.operate as operate
        a, b = SharedContext(operate), SharedContext(operate)
        with a.installed():
            with self.assertRaisesRegex(RuntimeError, "Another context"):
                with b.installed():
                    pass

    def test_unsupported_rerank_fails_before_prefix(self):
        import minirag.operate as operate
        a = SharedContext(operate)
        with patch.dict(os.environ, {"MINIRAG_RERANK": "ce1"}):
            with self.assertRaisesRegex(RuntimeError, "Unsupported experimental"):
                asyncio.run(a.call())


class LockTests(unittest.TestCase):
    def test_current_pid_is_alive_without_signal(self):
        self.assertTrue(alive(os.getpid()))

    def test_live_owner_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            with run_lock(tmp):
                with self.assertRaisesRegex(RuntimeError, "live PID"):
                    with run_lock(tmp):
                        pass
            self.assertFalse((Path(tmp) / "RUNNING.lock").exists())


class PipelineGuards(unittest.TestCase):
    def test_offline_builder_needs_no_keys_and_installs_rejecting_llm(self):
        import gemini_common
        resolver = gemini_common._resolve_api_keys
        def factory(snapshot, llm_max_async):
            self.assertEqual(gemini_common._resolve_api_keys(), [])
            return SimpleNamespace(llm_model_func=None)
        with patch.dict(os.environ, {}, clear=True):
            rag = build_offline(SimpleNamespace(build=factory), Path("unused"))
            with self.assertRaisesRegex(RuntimeError, "never call an LLM"):
                asyncio.run(rag.llm_model_func("forbidden"))
        self.assertIs(gemini_common._resolve_api_keys, resolver)

    def test_subset_cannot_unlock_test(self):
        from reproduce.research.mhr_phase3.pipeline import verify_validation
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.json"
            write_json(report, {"status": "verified", "validation_scope": "subset",
                                "completed_queries": 6, "total_queries": 6,
                                "logical_answer_contexts": 12, "mismatches": [], "llm_calls": 0})
            with self.assertRaisesRegex(ValueError, "Full dev400"):
                verify_validation(DEFAULT_REPO, report)

    def test_repository_drift_rejected_after_full_validation(self):
        from reproduce.research.mhr_phase3.pipeline import verify_validation
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.json"
            write_json(report, {"status": "verified", "validation_scope": "all_dev400",
                                "completed_queries": 400, "total_queries": 400,
                                "logical_answer_contexts": 800, "mismatches": [], "llm_calls": 0,
                                "identity": {"source_hashes": {"operate": "old"}}})
            with patch("reproduce.research.mhr_phase3.pipeline.source_hashes", return_value={"operate": "new"}):
                with self.assertRaisesRegex(ValueError, "Repository source changed"):
                    verify_validation(DEFAULT_REPO, report)

    def test_plan_does_not_call_models_or_open_test(self):
        from reproduce.research.mhr_phase3 import pipeline
        with patch("reproduce.research.mhr_phase3.pipeline.verify_validation", side_effect=FileNotFoundError), \
             patch("reproduce.research.mhr_phase3.pipeline.source_hashes", return_value={"source": "hash"}), \
             patch("reproduce.research.mhr_phase3.pipeline.child", side_effect=AssertionError("must not run a child")):
            plan = pipeline.plan(DEFAULT_REPO, Path("absent.json"))
        self.assertFalse(plan["test_opened_by_plan"])
        self.assertEqual(plan["llm_calls_by_plan"], 0)
        self.assertEqual(plan["valid_judge_votes"], 2156 * 2 * 3 * 3)
        self.assertEqual(plan["judge_passes"], 3)
        self.assertEqual(plan["seeds"], [101, 202, 303])

    def test_optimization_does_not_hide_semantic_log_differences(self):
        self.assertEqual(stable_log({"chunk_ids": ["a", "b"], "retrieval_ms": 1}),
                         stable_log({"chunk_ids": ["a", "b"], "retrieval_ms": 100}))
        self.assertNotEqual(stable_log({"chunk_ids": ["a", "b"]}),
                            stable_log({"chunk_ids": ["b", "a"]}))

    def test_judge_consumer_order_independent_passes_and_resume(self):
        from reproduce.research.mhr_phase3 import judge_worker
        async def scenario(root):
            questions = root / "test_internal.csv"
            with questions.open("w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(["query_id", "Question", "Gold Answer", "Type"])
                w.writerows([["synthetic1", "Synthetic question A?", "A", "inference"],
                             ["synthetic2", "Synthetic question B?", "B", "comparison"]])
            write_json(root / "RUN_MANIFEST.json", {"seeds": [101, 202, 303], "configs": ["C0", "C1"],
                       "judge_model": "gemini-flash-lite-latest", "judge_passes": 3,
                       "judge_concurrency": 4, "invalid_tries": 3, "outer_resume_limit": 2,
                       "valid_judge_votes": 36})
            for seed in (101, 202, 303):
                ready = {"questions_sha256": sha(questions), "answers": {}}
                for config in ("C0", "C1"):
                    folder = root / "qa" / f"s{seed}" / f"{config}_s{seed}"
                    folder.mkdir(parents=True)
                    with (folder / "answers.csv").open("w", encoding="utf-8", newline="") as f:
                        w = csv.writer(f)
                        w.writerow(["Question", "Gold Answer", "minirag"])
                        w.writerows([["Synthetic question A?", "A", f"marker_{seed}_{config}"],
                                     ["Synthetic question B?", "B", f"marker_{seed}_{config}"]])
                    ready["answers"][config] = sha(folder / "answers.csv")
                write_json(root / f"READY_s{seed}.json", ready)
            calls = []
            async def complete(model, prompt):
                self.assertEqual(model, "gemini-flash-lite-latest")
                calls.append(prompt)
                return "accurate"
            with patch("dotenv.load_dotenv", return_value=False), \
                 patch("minirag.llm.gemini.gemini_complete_if_cache", side_effect=complete), \
                 patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
                await judge_worker.consume(SimpleNamespace(repo=DEFAULT_REPO, run_root=root))
                self.assertEqual(len(calls), 36)
                for i, (seed, config) in enumerate((s, c) for s in (101, 202, 303) for c in ("C0", "C1")):
                    self.assertTrue(all(f"marker_{seed}_{config}" in p for p in calls[i*6:(i+1)*6]))
                await judge_worker.consume(SimpleNamespace(repo=DEFAULT_REPO, run_root=root))
                self.assertEqual(len(calls), 36, "Valid journal entries must not be judged twice")
            self.assertEqual(read_json(root / "JUDGE_STATUS.json")["valid_votes"], 36)
        with tempfile.TemporaryDirectory() as tmp:
            asyncio.run(scenario(Path(tmp)))


if __name__ == "__main__":
    unittest.main()
