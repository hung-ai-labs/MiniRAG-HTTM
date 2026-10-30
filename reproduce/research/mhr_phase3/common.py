"""Local files and process locks. This module never imports an API client."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone

DEFAULT_REPO = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = DEFAULT_REPO / "runs/multihop_rag/phase3_acceleration"


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path, key="query_id"):
    result = {}
    if Path(path).exists():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                result[record[key]] = record
    return result


def alive(pid):
    """Do not use os.kill(pid, 0) on Windows: it can terminate a process."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return ctypes.get_last_error() == 5  # inaccessible is not evidence of a dead owner
        try:
            code = wintypes.DWORD()
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


@contextlib.contextmanager
def run_lock(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / "RUNNING.lock"
    if lock.exists():
        owner = read_json(lock)
        if alive(owner["pid"]):
            raise RuntimeError(f"Run already owned by live PID {owner['pid']}")
        lock.rename(directory / f"RUNNING.stale.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}.json")
    with lock.open("x", encoding="utf-8") as handle:
        json.dump({"pid": os.getpid(), "at": now()}, handle)
    try:
        yield
    finally:
        if lock.exists() and read_json(lock).get("pid") == os.getpid():
            lock.unlink()


def load_repo(repo):
    """Avoid writing pyc files in the read-only repository."""
    import importlib.util
    sys.dont_write_bytecode = True
    repo = Path(repo).resolve()
    for path in (repo, repo / "reproduce", repo / "reproduce/research"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    spec = importlib.util.spec_from_file_location("phase3_original_phased_qa", repo / "reproduce/research/phased_qa.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_hashes(repo):
    repo = Path(repo)
    names = ["minirag/operate.py", "minirag/minirag.py", "minirag/base.py", "minirag/prompt.py",
             "minirag/kg/networkx_impl.py", "minirag/kg/nano_vector_db_impl.py", "minirag/bm25.py",
             "minirag/llm/gemini.py", "reproduce/research/phased_qa.py", "reproduce/research/judge_run.py",
             "reproduce/research/qa_run.py", "reproduce/gemini_common.py", "reproduce/Step_2_evaluate.py"]
    return {name: sha(repo / name) for name in names}


def runtime_identity():
    import importlib.metadata
    packages = {}
    for name in ("numpy", "networkx", "torch", "sentence-transformers", "transformers", "tiktoken",
                 "nano-vectordb", "openai", "json-repair"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {"python": sys.version, "packages": packages}
