"""Offline context gates and guarded reuse of the Phi phased QA pipeline.

Nothing in this module calls a service until the explicit smoke/answers commands.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
# The context gate imports this worktree's minirag (temporal parser); the script runs from reproduce/graph_repair/acc.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PY = Path(r"E:\Project\MiniRAG\.venv\Scripts\python.exe")
QUESTIONS = ROOT / "dataset/LiHua-World/splits/nondev435.csv"
OUT = ROOT / "runs/lihua_world/temporal_acc"
SOURCE = {
    "qwen": (Path(r"E:\Project\MiniRAG\runs\lihua_world\flow_v1"),
             Path(r"E:\Project\MiniRAG\LiHua-World-qwen-modal"), "L-C0R", "serving_qwen_modal.json", 3),
    "phi": (Path(r"E:\Project\MiniRAG\.worktrees\lihua-phi-rope\runs\lihua_world\phi_rope"),
            Path(r"E:\Project\MiniRAG\.worktrees\lihua-phi-rope\indexes\lihua_world-phi-rope-modal"),
            "L-C0", "serving_phi_rope_modal.json", 6),
}
SEEDS = (101, 202, 303)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rows(path):
    with Path(path).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def complete_answers(model, seed, arm, questions=None):
    """Read a completed generation without touching its files."""
    questions = questions or rows(QUESTIONS)
    folder = OUT / model / f"{arm}_s{seed}"
    csv_path, jsonl_path = folder / "answers.csv", folder / "answers.jsonl"
    answers, records = rows(csv_path), jsonl(jsonl_path)
    ids = [q["query_id"] for q in questions]
    if len(answers) != 435 or len(records) != 435 or set(records) != set(ids):
        raise ValueError(f"incomplete answers or query IDs: {folder}")
    for q, a in zip(questions, answers):
        if (q["Question"], q["Gold Answer"]) != (a["Question"], a["Gold Answer"]):
            raise ValueError(f"answers not aligned: {folder} {q['query_id']}")
        if records[q["query_id"]]["answer"] != a["minirag"]:
            raise ValueError(f"CSV/JSONL answer mismatch: {folder} {q['query_id']}")
    return answers, records


def crn(model, seed):
    """Construct L-TC from the registered context gate and completed answers."""
    questions = rows(QUESTIONS)
    ids = [q["query_id"] for q in questions]
    gate_path = OUT / model / f"gate_s{seed}.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    changed = gate.get("context_changed")
    if gate.get("model") != model or gate.get("seed") != seed or gate.get("baseline_identical") != 435 \
            or not isinstance(changed, list) or len(changed) != len(set(changed)) or not set(changed) <= set(ids):
        raise ValueError(f"invalid 435/435 context gate: {gate_path}")
    c0, c0_records = complete_answers(model, seed, "L-C0", questions)
    lt, lt_records = complete_answers(model, seed, "L-T", questions)
    selected = [lt[i] if qid in set(changed) else c0[i] for i, qid in enumerate(ids)]
    selected_records = [lt_records[qid] if qid in set(changed) else c0_records[qid] for qid in ids]
    dest = OUT / model / f"L-TC_s{seed}"
    dest.mkdir(parents=True, exist_ok=True)
    import io
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=list(c0[0]))
    writer.writeheader()
    writer.writerows(selected)
    contents = {
        "answers.csv": buf.getvalue().encode("utf-8"),
        "answers.jsonl": "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in selected_records).encode("utf-8"),
    }
    inputs = {f"{arm}/{name}": sha(OUT / model / f"{arm}_s{seed}" / name)
              for arm in ("L-C0", "L-T") for name in ("answers.csv", "answers.jsonl")}
    manifest = {"model": model, "seed": seed, "gate_sha256": sha(gate_path),
                "input_sha256": inputs, "from_c0": 435 - len(changed), "from_lt": len(changed)}
    contents["crn_manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    for name, data in contents.items():
        path = dest / name
        if path.exists() and path.read_bytes() != data:
            raise ValueError(f"existing CRN output differs: {path}")
    for name, data in contents.items():
        path = dest / name
        if not path.exists():
            path.write_bytes(data)
    return manifest


def jsonl(path):
    with Path(path).open(encoding="utf-8") as f:
        data = [json.loads(s) for s in f if s.strip()]
    if len(data) != len({r["query_id"] for r in data}):
        raise ValueError(f"duplicate query_id in {path}")
    return {r["query_id"]: r for r in data}


def env_for(arm):
    return {"PYTHONHASHSEED": "13", "PYTHONUTF8": "1", "MINIRAG_TEMPORAL": "1" if arm == "L-T" else "0",
            "MINIRAG_TEMPORAL_EXPAND": "1", "MINIRAG_TEMPORAL_H": "0",
            "MINIRAG_PATH_PRUNE": "", "MINIRAG_PATH_SCORE": "", "MINIRAG_PATH_SCORE_FLOW": "0",
            "MINIRAG_PATH_SELECT": "", "MINIRAG_FLOW_SPEC": "", "MINIRAG_FLOW_NORM": "",
            "MINIRAG_PAPER_MODE": "0", "MINIRAG_EDGE_SCORE": "", "MINIRAG_DIAG_LOG": "",
            "MINIRAG_DIAG_PATH_SCORE": "", "MINIRAG_RERANK": "", "MINIRAG_MAX_TOKEN_TEXT_UNIT": ""}


def check_source(model):
    source, index, base, serving, workers = SOURCE[model]
    q = rows(QUESTIONS)
    assert len(q) == 435 and len({r["query_id"] for r in q}) == 435
    assert sha(QUESTIONS) == "72da5461b5d2ea6c4b63ad21d12fadd6152d2d3d2ad1c6b44f881baf74951013"
    if not index.is_dir():
        raise FileNotFoundError(index)
    for seed in SEEDS:
        note = json.loads((source / f"{base}_s{seed}" / "run_note.json").read_text(encoding="utf-8"))
        assert note["questions_sha256"] == sha(QUESTIONS)
        assert note["python_hash_seed"] == 13
        assert note["environment"]["MINIRAG_ANSWER_TYPE_FIX"] == "1"
        assert note["environment"]["MINIRAG_PATH2CHUNK_FIX"] == "0"
        assert note["environment"]["MINIRAG_TRUNCATE_SOURCES"] == "1"
        assert note["kw_cache_sha256"] == sha(source / f"kw_s{seed}.jsonl")
        if note.get("serving_sha256"):
            assert note["serving_sha256"] == sha(ROOT / "reproduce/research" / serving)
        if "index_manifest_sha256" in note["index_fingerprint"]:
            assert sha(index / "index_manifest.json") == note["index_fingerprint"]["index_manifest_sha256"]
        elif seed == SEEDS[0]:
            sys.path.insert(0, str(ROOT / "reproduce/research"))
            import qa_run
            assert qa_run.index_hash(index) == note["index_fingerprint"]["index_files_sha256"]
        assert len(jsonl(source / f"{base}_s{seed}" / "contexts.jsonl")) == 435
        assert len(jsonl(source / f"kw_s{seed}.jsonl")) == 435
    return source, index, base, ROOT / "reproduce/research" / serving, workers


def corpus_years(index):
    docs = json.loads((index / "kv_store_full_docs.json").read_text(encoding="utf-8"))
    return {int(m[1]) for row in docs.values()
            if (m := re.match(r"^Time:\s*(\d{4})\d{4}(?:_|\b)", row.get("content", "")))}


def prepare(model):
    source, _, _, _, _ = check_source(model)
    dest = OUT / model
    dest.mkdir(parents=True, exist_ok=True)
    for seed in SEEDS:
        src = source / f"kw_s{seed}.jsonl"
        dst = dest / src.name
        if dst.exists():
            if sha(dst) != sha(src):
                raise ValueError(f"frozen keyword cache differs: {dst}")
        else:
            shutil.copyfile(src, dst)
    return dest


def context_gate(model, seed, *, require_temporal=True):
    from minirag.temporal import parse_query

    source, index, base, _, _ = check_source(model)
    q = rows(QUESTIONS)
    frozen = jsonl(source / f"{base}_s{seed}" / "contexts.jsonl")
    c0 = jsonl(OUT / model / f"L-C0_s{seed}" / "contexts.jsonl")
    if set(c0) != set(frozen):
        raise ValueError(f"{model} s{seed}: C0 question IDs differ")
    bad = [r["query_id"] for r in q if c0[r["query_id"]]["context"] != frozen[r["query_id"]]["context"]
           or c0[r["query_id"]]["status"] != frozen[r["query_id"]]["status"]]
    if bad:
        raise ValueError(f"{model} s{seed}: C0 differs from frozen baseline for {len(bad)} IDs: {bad[:12]}")
    if not require_temporal:
        return {"baseline_identical": 435}
    lt = jsonl(OUT / model / f"L-T_s{seed}" / "contexts.jsonl")
    if set(lt) != set(frozen):
        raise ValueError(f"{model} s{seed}: L-T question IDs differ")
    years = corpus_years(index)
    fires = [r["query_id"] for r in q if parse_query(r["Question"], years)]
    changed = [r["query_id"] for r in q if lt[r["query_id"]]["context"] != c0[r["query_id"]]["context"]
               or lt[r["query_id"]]["status"] != c0[r["query_id"]]["status"]]
    outside = set(changed) - set(fires)
    if outside:
        raise ValueError(f"L-T changes non-temporal questions: {sorted(outside)}")
    report = {"model": model, "seed": seed, "baseline_identical": 435, "parser_fires": fires,
              "context_changed": changed, "unchanged_without_anchor": 435 - len(fires)}
    path = OUT / model / f"gate_s{seed}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def bind_deployment(model, url, serving, *, write=False):
    if not url or not url.startswith("https://"):
        raise ValueError("pass deployed HTTPS URL with --url")
    path = OUT / model / "deployment.json"
    identity = {"url_sha256": hashlib.sha256(url.encode()).hexdigest(), "serving_sha256": sha(serving)}
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != identity:
        raise ValueError(f"{model}: deployment URL or serving config changed within session")
    if write and not path.exists():
        path.write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")


def slm_key():
    if os.environ.get("MINIRAG_SLM_KEY"):
        return os.environ["MINIRAG_SLM_KEY"]
    from dotenv import dotenv_values
    return dotenv_values(Path(r"E:\Project\MiniRAG\.env")).get("MINIRAG_SLM_KEY")


def command(model, phase, seed=None, arm=None, url=None):
    url = url or os.environ.get("MINIRAG_SLM_URL")
    _, index, _, serving, workers = check_source(model)
    prepare(model)
    dest = OUT / model
    if phase == "contexts":
        if arm not in ("L-C0", "L-T"):
            raise ValueError("arm required")
        if arm == "L-T":
            context_gate(model, seed, require_temporal=False)
    elif phase in ("smoke", "answers"):
        for s in SEEDS:
            context_gate(model, s)
        if not slm_key():
            raise ValueError("MINIRAG_SLM_KEY missing")
        bind_deployment(model, url, serving)
        if phase == "answers":
            if not (dest / "deployment.json").exists():
                raise ValueError("G1 deployment binding missing")
            smoke = dest / "g1_smoke.json"
            if not smoke.exists() or not all(json.loads(smoke.read_text(encoding="utf-8"))["checks"].values()):
                raise ValueError("G1 smoke gate missing or failed")
    else:
        raise ValueError(phase)
    from dotenv import dotenv_values
    env = os.environ.copy()
    for key, value in dotenv_values(Path(r"E:\Project\MiniRAG\.env")).items():
        if value is not None and key != "MINIRAG_SLM_URL":
            env.setdefault(key, value)
    env |= env_for(arm)
    if phase in ("smoke", "answers"):
        env["MINIRAG_SLM_KEY"] = slm_key()
    if url:
        env["MINIRAG_SLM_URL"] = url
    if phase == "smoke":
        subprocess.run([str(PY), "reproduce/research/slm_smoke.py", "--serving", str(serving),
                        "--out", str(dest / "g1_smoke.json")], cwd=ROOT, env=env, check=True)
        bind_deployment(model, url, serving, write=True)
        return
    args = [str(PY), "reproduce/research/phased_qa.py", phase, "--config", arm,
            "--questions", str(QUESTIONS), "--seed", str(seed), "--out", str(dest),
            "--serving", str(serving)]
    if phase == "contexts":
        args += ["--index", str(index), "--workers", str(workers)]
    subprocess.run(args, cwd=ROOT, env=env, check=True)
    if phase == "contexts":
        print(context_gate(model, seed, require_temporal=arm == "L-T"))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=("prepare", "contexts", "gate", "smoke", "answers", "crn"))
    p.add_argument("--model", choices=SOURCE, required=True)
    p.add_argument("--seed", type=int, choices=SEEDS)
    p.add_argument("--arm", choices=("L-C0", "L-T"))
    p.add_argument("--url")
    a = p.parse_args()
    if a.phase == "prepare":
        print(prepare(a.model))
    elif a.phase == "crn":
        if a.seed is None:
            p.error("--seed required")
        print(json.dumps(crn(a.model, a.seed), indent=2))
    elif a.phase == "gate":
        for s in (a.seed,) if a.seed else SEEDS:
            print(context_gate(a.model, s))
    elif a.phase == "smoke":
        command(a.model, a.phase, url=a.url)
    else:
        if a.seed is None or a.arm is None:
            p.error("--seed and --arm required")
        command(a.model, a.phase, a.seed, a.arm, a.url)


if __name__ == "__main__":
    main()
