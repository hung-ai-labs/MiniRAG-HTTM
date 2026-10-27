# Parallel QA on an existing index

This opt-in runner does not index documents or judge answers. The legacy
`Step_1_QA.py` remains unchanged. Use a prepared CSV with `Question` and
`Gold Answer` headers; dataset conversion is a separate step.

## One Modal A10G

Keep the existing vLLM server: one A10G, `max_containers=1`,
`@modal.concurrent(max_inputs=32)`. In the shell that runs QA, set
`MINIRAG_SLM_URL` and `MINIRAG_SLM_KEY` from your existing deployment.
Do not place keys in commands committed to Git or in run artifacts.

From the repository root, using the project's Python environment:

```text
python reproduce/research/qa_run.py --questions <prepared.csv> --workingdir <existing-index> --run-dir <new-run-directory> --concurrency 4 --llm-max-async 4
```

The default query and LLM concurrency are **4**, a conservative starting preset,
not a measured GPU capacity guarantee. The shared `build_rag()` default remains
8 for legacy scripts. The default backend is `modal`, model alias `minirag-slm` (the existing
Qwen2.5-3B deployment). Modal settings are established once before importing
the backend. Only this runner's Modal process uses the high RPM/TPM settings
already used in `slm_env.sh modal`. Gemini processes and quotas are unchanged.
`MINIRAG_MAX_TOKENS` defaults to 1024 if not already set; sampling and retrieval
are otherwise inherited unchanged. `--backend configured` instead uses the
existing environment (set `--model` explicitly for Gemini or another model).

Concurrency does not imply identical stochastic answers. Keep the model
revision, serving configuration, request seed/sampling and input set constant.
The request content is unchanged by the runner. A new run does not set a
generation seed; it preserves an existing `MINIRAG_SLM_SEED` if present.
If using the screening keyword cache, it must already be complete and frozen
(`MINIRAG_KW_CACHE_ONLY=1`). Otherwise leave `MINIRAG_KW_CACHE` unset. The runner
rejects mutable parser caches to keep resume identities stable.

### Memory estimate and experimental validity

The official Qwen2.5-3B config has 36 layers, 2 KV heads and a 128-dimensional
head. Assuming BF16 KV cache, per-token storage is
`2 (K,V) * 36 * 2 * 128 * 2 bytes = 36 KiB`.
At a full 32,768-token resident sequence (input plus generated tokens), KV
storage alone is approximately 4.5 GiB for 4 requests, 9 GiB for 8 and 18 GiB
for 16. Weights, activations, CUDA graphs and allocator overhead are additional.
vLLM's cache pool, scheduling and prefix sharing affect actual allocation, so
these are demand estimates, not observed VRAM usage. Four is the conservative
initial preset on A10G 24 GB; test eight separately, and treat sixteen as a
stress configuration rather than the default.

References:
- https://huggingface.co/Qwen/Qwen2.5-3B-Instruct/blob/main/config.json
- https://docs.vllm.ai/en/v0.11.0/usage/reproducibility.html
- https://docs.vllm.ai/en/v0.11.0/configuration/optimization.html

vLLM 0.11.0 explicitly does **not** promise reproducibility with online
`vllm serve`, even with a seed. Matching fake-fixture requests does not prove
identical real model outputs. For quality comparisons, fix concurrency across
every method, run methods separately on an isolated endpoint and use the
project's repeated-generation/judging protocol. Compare single-query latency
at concurrency one; report saturated throughput separately. Do not mix loaded
latency with the serial baseline. No adaptive concurrency or sampling changes
are made during a run. A run resumed at a different concurrency is recorded as
such and should not be used as one homogeneous performance measurement.

`--serving-config <json>` optionally records the actual pinned model revision,
vLLM version, GPU, dtype, max_model_len and sampling settings. These fields are
required for a live benchmark, together with a fixed `MINIRAG_SLM_SEED` in the
calling shell. Supply the real deployment settings (do not guess them). The
declaration is recorded in the manifest; it does not remotely verify or modify
the deployment. Resume rejects a changed declaration.

## Checkpoints and index protection

Each run requires a fresh directory. A data-equivalent `index_snapshot/` is
copied there once because MiniRAG writes cache files into its working directory.
The original index is never passed to MiniRAG for writing. The snapshot reuses
the existing graph and vectors; it does not call an indexing LLM.

`manifest.json` identifies the CSV bytes, selected row count, generation and
retrieval settings, relevant source code and source index contents. Index logs
and the LLM response cache are excluded from the data fingerprint. API keys and
endpoint URLs are not stored. Model revision/serving configuration must still
be recorded externally; this runner cannot attest to a remote deployment.

`generation.jsonl` durably records each completed attempt through one writer.
Row positions are IDs, so duplicate question text is safe. Failures contain
status and exception type, never a synthetic `Error` answer or raw SDK messages.
An OS lock prevents two processes from writing the same run directory.

Repeat the original command with `--resume` and the same run directory after
interruption. Only successful row IDs are skipped. Concurrency may change on
resume; input, index and scientific settings may not. A torn final JSONL line
is repaired; corrupt complete lines are rejected. Runs without a valid manifest
and index snapshot are setup failures: start a new directory.

Only a fully successful run exports `answers.csv`, ordered like the input,
with `Question,Gold Answer,minirag` columns for `Step_2_evaluate.py`.
Partial runs exit nonzero and have no answer CSV to accidentally judge.

## Benchmark preparation (does not call Modal)

```text
python reproduce/research/benchmark_qa.py --questions <prepared-dev.csv> --workingdir <existing-index> --run-dir <new-benchmark-directory>
```

This prints three commands for the same first 100 rows, with both query and LLM
concurrency set to 1, 2 and 4. Use `--levels 1 4 8 16` to explicitly prepare the
original extended sweep. It fixes the Python hash seed consistently
(13 unless already supplied) so set iteration order does not change between
processes. It preserves generation seeds and other settings. Each level starts
a fresh process, one RAG and one event loop. Run commands with another preset
hash seed if that is the established experimental protocol.

Adding `--execute --serving-config <actual-serving.json>` actually runs the
selected levels sequentially and incurs Modal/API usage (including five warmup
questions per level). Set the same request seed before execution. The benchmark
stops on a failed level. Use an isolated endpoint and keep
the source index unchanged. Choose the prepared development input deliberately;
the tool does not decide experimental splits or inspect internal-test labels.

Each level warms up with five unscored QA calls, then measures the same 100
rows. Change `--warmup` explicitly if the protocol requires another count.
Each `metrics.json` separately records total wall time, setup, warmup and
measured query-phase time, process CPU
time, success/error counts and questions per minute. Checkpoints record queue
wait, query wall time, individual LLM call wall times and the remaining non-LLM
wall time. LLM time includes its limiter/network/server wait; non-LLM time
includes retrieval, embedding and local work, not an isolated CPU profile.
Overlapping per-query times must not be added to estimate billed GPU hours.
`benchmark.json` collects the summaries. Additional cold starts can affect levels;
correlate these metrics with Modal GPU utilization/billing before selecting a
configuration or quoting a speedup. No speedup or cost reduction is guaranteed.

## Offline tests

```text
python -B -m unittest discover -s tests/research -p "test_qa_parallel.py" -v
```

The tests use standard-library fakes and extract the actual limiter and query
function without importing heavyweight model dependencies. No network or API
keys are required. Real GPU benchmarking is deliberately separate.
