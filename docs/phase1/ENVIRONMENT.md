# Environment Guide — MiniRAG + Gemini

> T1 environment guide. Verified on **Windows 10 x64 / PowerShell 5.1** at
> commit `5fc3fd98c2b8581aadd2c9c7e71621c7268f74c9` on `dev`, checked
> 2026-09-09. This document records package/import checks only; it does not
> claim that the baseline index or Gemini pipeline has been run on this
> checkout.

## Scope

The verified scope is:

- Gemini generation and judge through the OpenAI-compatible backend;
- local `sentence-transformers/all-MiniLM-L6-v2` embedding;
- MiniRAG's default JSON/KV, NanoVectorDB and NetworkX storage;
- the reproduce scripts' import dependencies.

RAGAS is a separate evaluation stack and is intentionally not installed here.
Indexing, QA, judge, RAGAS, benchmark commands and model-weight downloads were
not run during T1.

## Verified machine and interpreter

| Item | Verified value |
|---|---|
| OS | Windows 10, build `10.0.26200.0`, 64-bit |
| Shell | Windows PowerShell `5.1.26100.9168` |
| `py -0p` | CPython 3.14 and CPython 3.11 available |
| Selected Python | CPython 3.11.9, 64-bit |
| Repository interpreter | `./.venv/Scripts/python.exe` |
| pip | 26.2.1 |
| Project package | `minirag-hku 0.0.2` editable |

The bare `python` command on the verified machine resolves to MinGW Python
3.9.13. Do not use it for this project, and do not use global `pip`; always use
the repository interpreter explicitly.

The existing `.venv` was retained. The old broken environment remains in
`.venv_broken_backup/`; `venv/` was not modified.

## Windows PowerShell setup

Run these commands from the repository root. They do not require activation or
an execution-policy change.

> **The working directory is not a convenience here, it is a requirement.**
> `reproduce/` has no `__init__.py`, so Python resolves it as an implicit
> namespace package from the current directory. Running the third import check
> from anywhere else fails with
> `ModuleNotFoundError: No module named 'reproduce'`, which looks like a broken
> install but is not one.

```powershell
# Only create .venv when it does not already exist; do not delete/overwrite it.
if (!(Test-Path .\.venv\Scripts\python.exe)) {
    py -3.11 -m venv .venv
}

$Py = ".\.venv\Scripts\python.exe"
& $Py --version
& $Py -m pip --version

& $Py -m pip install --upgrade pip setuptools wheel
& $Py -m pip install -e .

# Direct dependencies used by the Gemini/local-embedding/default-storage path.
& $Py -m pip install nano-vectordb pandas openai torch transformers sentence-transformers

& $Py -m pip check
```

`pyproject.toml` declares Python `>=3.9`, while the checked environment uses
3.11.9 because it is the available standard Windows CPython selected for the
binary/ML packages. `setup.py` reads `requirements.txt`, but the PEP 517 project
metadata does not expose a `[project].dependencies` list; therefore the direct
runtime packages above are installed explicitly rather than assuming that
`pip install -e .` alone covers them.

### Confirming the editable install took effect

`import minirag` must print a path inside **this checkout**, not inside
`site-packages`:

```
.../MiniRAG-HTTM/minirag/__init__.py     <- correct
.../site-packages/minirag/__init__.py    <- wrong
```

A `site-packages` path means a released `minirag-hku` wheel is shadowing the
checkout, so local edits to `minirag/` have no effect — a failure that stays
silent until someone spends an afternoon wondering why a change does nothing.
Fix it with `pip uninstall minirag-hku` followed by `pip install -e .`.

## macOS/Linux (not verified in T1)

The equivalent command shape is below. It has not been executed on this
checkout or on a macOS/Linux machine.

```bash
# Run from the repository root; do not overwrite an existing .venv.
test -x .venv/bin/python || python3.11 -m venv .venv
PY=.venv/bin/python
"$PY" --version
"$PY" -m pip --version
"$PY" -m pip install --upgrade pip setuptools wheel
"$PY" -m pip install -e .
"$PY" -m pip install nano-vectordb pandas openai torch transformers sentence-transformers
"$PY" -m pip check
```

## Dependency status from source and metadata

### Installed and verified

| Package | Version | Why it is in scope |
|---|---:|---|
| `minirag-hku` | 0.0.2 | Editable checkout package |
| `numpy` | 2.4.6 | Core arrays, graph/vector storage, Gemini backend |
| `networkx` | 3.6.1 | Default graph storage |
| `nano-vectordb` | 0.0.4.3 | Default `NanoVectorDBStorage` |
| `pydantic` | 2.13.5 | Core/API data structures |
| `httpx` | 0.28.1 | OpenAI-compatible client transport |
| `tiktoken` | 0.14.0 | Chunking/token budgeting |
| `json-repair` | 0.63.4 | LLM extraction/query JSON parsing |
| `python-dotenv` | 1.2.3 | `.env` loading without exposing values |
| `pipmaster` | 1.1.13 | Existing source's optional dependency checks |
| `nltk` | 3.10.3 | Similarity/metrics utilities |
| `rouge` | 1.0.1 | Utility metrics |
| `scikit-learn` | 1.9.0 | Utility text similarity |
| `openai` | 3.9.0 | Gemini OpenAI-compatible endpoint |
| `torch` | 2.14.0+cpu | Local embedding runtime |
| `transformers` | 5.16.1 | Local tokenizer/model classes |
| `sentence-transformers` | 6.0.1 | Local embedding package |
| `pandas` | 3.0.5 | `run_eval_demo.py` result/CSV handling |

Other verified core versions include `tenacity 9.1.4`, `tqdm 4.70.0`, and
`xxhash 4.0.1`.

### Declared but outside the verified Gemini path

`requirements.txt` also declares `accelerate`, `aiofiles`, `aiohttp`,
`configparser`, `graspologic`, `PyPDF2`, `python-docx`, and `python-pptx`.
They were not installed in this T1 environment because they belong to optional
HF device mapping, alternate LLM backends, API/document parsing, or optional
graph helpers rather than the verified Gemini + local embedding + default
storage path. Install them only when using those features.

### RAGAS intentionally deferred

The following are **not installed**:

- `ragas>=0.4,<0.5`;
- `datasets`;
- `langchain-community<0.4`.

`reproduce/Step_4_ragas.py` imports these directly. A future evaluation setup
must install them as a separate, explicitly requested stack; their absence is
not a failure of the core/Gemini import check.

## Key and model boundaries

No `.env` file and no matching Gemini/OpenAI key variable names were present
during the audit. No key values were printed or written. The source accepts
placeholders such as the following, but do not commit real values:

```text
GEMINI_API_KEY_1=<your-key>
GEMINI_API_KEY_2=<your-key>
GEMINI_API_BASE=https://generativelanguage.googleapis.com/v1beta/openai/
```

`reproduce/gemini_common.py:90-106` calls
`AutoTokenizer.from_pretrained`/`AutoModel.from_pretrained` when `build_rag()`
is executed with local embeddings. That call was deliberately **not** made in
T1, so no embedding weights were downloaded and local embedding is only
package-ready, not model-cache-verified.

The frozen baseline expects `./LiHua-World-gemini`, but that index directory is
not present in this checkout. Missing ignored artifacts are not treated as an
installation failure.

## Verification record

| Check | Result | Limit |
|---|---|---|
| `py -0p` and interpreter selection | PASS | Windows machine only |
| `.venv/Scripts/python.exe --version` and pip metadata | PASS | CPython 3.11.9 / pip 26.2.1 |
| `pip check` | PASS: no broken requirements | Does not prove pipeline behavior |
| `import minirag` | PASS; loaded from `minirag/__init__.py` in this checkout | Import only |
| Gemini backend import | PASS; loaded from `minirag/llm/gemini.py` | No key resolution/request |
| HF interface import | PASS; loaded from `minirag/llm/hf.py` | No model initialization |
| `nano_vectordb`, `pandas` imports | PASS from `.venv` | No storage/model construction |
| `from reproduce.gemini_common import get_args` | PASS from this checkout | `build_rag()` not called |
| Gemini API call | NOT RUN | No key configured; outside T1 |
| Model-weight download | NOT RUN | No `from_pretrained()` call |
| Indexing / QA / judge / benchmark | NOT RUN | Explicit T1 boundary |
| RAGAS | NOT RUN | Stack intentionally deferred |

## Commands for the next verified check

```powershell
$Py = ".\.venv\Scripts\python.exe"
& $Py -m pip check
& $Py -c "import minirag; print(minirag.__file__)"
& $Py -c "from minirag.llm.gemini import gemini_complete; print('Gemini backend import OK')"
& $Py -c "from reproduce.gemini_common import get_args; print('reproduce common import OK')"
```

These commands are import/metadata checks only. Do not call `build_rag()`,
instantiate `MiniRAG`, run `Step_0`–`Step_5`, `run_eval_demo.py`, a shell
wrapper, server, or benchmark as part of T1.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'reproduce'` | Not in the repository root | `cd` to the repository root and rerun |
| `import minirag` resolves to `site-packages` | A released wheel shadows the checkout | `pip uninstall minirag-hku`, then `pip install -e .` |
| `py: command not found` (Windows) | Python Launcher missing | Install CPython from python.org with "Add python.exe to PATH" |
| `python3.13: command not found` (macOS) | Interpreter not installed | `brew install python@3.13` |
| `pip check` reports a conflict | Package versions diverged | Post the full output to the team; do not uninstall packages alone |
| `torch` download is very large | Default wheel bundles GPU runtime | Expected. For a CPU-only wheel: `pip install torch --index-url https://download.pytorch.org/whl/cpu` |

## Beyond T1: what reproducibility still needs

T1 proves the code **imports**. It does not yet prove the team can **reproduce
the numbers**. Four gaps remain open.

### Environments have already diverged

Comparing this Windows machine against the machine that produced the frozen
baseline (`accuracy 57.33 ± 1.53`):

| Package | Baseline machine | This machine |
|---|---:|---:|
| Python | 3.13.5 | 3.11.9 |
| **`openai`** | **1.109.1** | **3.9.0** |
| **`tenacity`** | **8.5.0** | **9.1.4** |
| `numpy` | 2.5.2 | 2.4.6 |

`openai` differs by two major versions and `tenacity` by one. Both are direct
dependencies of `minirag/llm/gemini.py` — `AsyncOpenAI` and the retry
decorators. Two machines running the same command can therefore behave
differently, and the difference would be indistinguishable from a change in the
system under test.

### Closed

1. ✅ **Versions are pinned.** `requirements.lock.txt` records the exact 119
   packages of the machine that produced the baseline, on Python 3.13.5.
   Install it with `pip install -r requirements.lock.txt` when the goal is to
   reproduce the baseline rather than to develop.
2. ✅ **The frozen evaluation files are committed.** `logs/devset.csv` (the 200
   questions), `logs/baseline442_devset.csv` (the baseline answers) and
   `logs/baseline442_devset_judged.csv` (the 600 verdicts) are now tracked, with
   line endings pinned in `.gitattributes` — the resume and join logic in
   `Step_1_QA` / `Step_2_evaluate` matches on the exact question string, so a
   CRLF round-trip on a Windows checkout would silently break it.

   This makes the baseline independently checkable **without spending any
   quota on QA**: re-judging the committed answers costs 600 judge calls and
   must land within the noise floor of `57.33 ± 1.53`.

   ```bash
   python reproduce/Step_2_evaluate.py --inputpath ./logs/baseline442_devset.csv --repeats 3
   ```

### Still open

3. **The baseline index is not shared.** `./LiHua-World-gemini/` (15 MB) is
   ignored. Re-indexing produces a *different* graph because the extraction LLM
   is not deterministic, so the frozen baseline would no longer be comparable.
   Distributing the directory is preferable to each member rebuilding it.
4. **`baseline.yaml` does not record a Python version.** Once the team settles
   on one interpreter, it belongs in the frozen config.

## T1 status

T1 is **verified on this Windows machine only**. The guide and package/import
evidence are complete for this checkout. T1 is not a three-machine completion:
the other two machines still need to reproduce the setup and report their own
`pip check`/interpreter/import results. The baseline index, API configuration,
model weights and pipeline outputs remain intentionally unverified.
