# Environment Guide — MiniRAG + Gemini

> T1 environment guide. Verified on **Windows 10 x64 / PowerShell 5.1** at
> commit `21dc08e` on `tai/phase1-environment`, checked
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
| `py -0p` | CPython 3.14, 3.13 and 3.11 available |
| Selected Python | CPython 3.13.5, 64-bit |
| Repository interpreter | `./.venv/Scripts/python.exe` |
| pip | 26.2.1 |
| Project package | `minirag-hku 0.0.2` editable |

The bare `python` command on the verified machine resolves to MinGW Python
3.9.13. Do not use it for this project, and do not use global `pip`; always use
the repository interpreter explicitly.

The `.venv` was recreated with CPython 3.13.5 to match the reported baseline
runtime. The previous Python 3.11 environment was moved outside this checkout
as a local backup. The old broken environment remains in
`.venv_broken_backup/`; `venv/` was not modified.

## Windows PowerShell setup

Run these commands from the repository root. They do not require activation or
an execution-policy change.

```powershell
# Only create .venv when it does not already exist; do not delete/overwrite it.
if (!(Test-Path .\.venv\Scripts\python.exe)) {
    py -3.13 -m venv .venv
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

`pyproject.toml` declares Python `>=3.9`; the checked environment uses
CPython 3.13.5 to match the reported baseline runtime. `setup.py` reads
`requirements.txt`, but the PEP 517 project
metadata does not expose a `[project].dependencies` list; therefore the direct
runtime packages above are installed explicitly rather than assuming that
`pip install -e .` alone covers them.

## macOS/Linux (not verified in T1)

The equivalent command shape is below. It has not been executed on this
checkout or on a macOS/Linux machine.

```bash
# Run from the repository root; do not overwrite an existing .venv.
test -x .venv/bin/python || python3.13 -m venv .venv
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
| `numpy` | 2.5.3 | Core arrays, graph/vector storage, Gemini backend |
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
| `openai` | 3.10.0 | Gemini OpenAI-compatible endpoint |
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
| `.venv/Scripts/python.exe --version` and pip metadata | PASS | CPython 3.13.5 / pip 26.2.1 |
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

## T1 status

T1 is **verified on this Windows machine only**. The guide and package/import
evidence are complete for this checkout. T1 is not a three-machine completion:
the other two machines still need to reproduce the setup and report their own
`pip check`/interpreter/import results. The baseline index, API configuration,
model weights and pipeline outputs remain intentionally unverified.
