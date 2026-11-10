"""Deduplicate exact (question, gold, answer) triples; use the unchanged judge_run.py."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess

from run import OUT, PY, QUESTIONS, ROOT, SEEDS, complete_answers, crn, rows, sha

SHARED = OUT / "judge_shared"
ARMS = ("L-C0", "L-TC")
MODELS = ("qwen", "phi")


def mapping_for(answer_sets):
    """Stable first-occurrence IDs, preserving exact text including whitespace."""
    unique, mapping = {}, []
    for model, seed, arm, question_rows, answer_rows in answer_sets:
        if len(question_rows) != len(answer_rows):
            raise ValueError("answer count differs")
        for q, a in zip(question_rows, answer_rows):
            if (q["Question"], q["Gold Answer"]) != (a["Question"], a["Gold Answer"]):
                raise ValueError(f"answers not aligned: {model} s{seed} {arm}")
            triple = (q["Question"], q["Gold Answer"], a["minirag"])
            if triple not in unique:
                unique[triple] = f"u{len(unique):05d}"
            mapping.append({"model": model, "seed": seed, "arm": arm, "query_id": q["query_id"],
                            "unique_id": unique[triple], "Type": q["Type"]})
    return unique, mapping


def output_dir(model, *, include_raw_lt=False, only_changed=False):
    base = OUT / ("judge_preview" if only_changed else "judge_shared") / model
    return base / "with_raw_lt" if include_raw_lt else base


def answer_sets(model, *, include_raw_lt=False, only_changed=False):
    q = rows(QUESTIONS)
    sets, hashes = [], {}
    for seed in (SEEDS[:1] if only_changed else SEEDS):
        crn(model, seed)
        changed = set(json.loads((OUT / model / f"gate_s{seed}.json").read_text(encoding="utf-8"))["context_changed"])
        for arm in (*ARMS, *(("L-T",) if include_raw_lt else ())):
            path = OUT / model / f"{arm}_s{seed}" / "answers.csv"
            a, _ = complete_answers(model, seed, arm, q)
            pairs = [(question, answer) for question, answer in zip(q, a)
                     if not only_changed or question["query_id"] in changed]
            sets.append((model, seed, arm, [x[0] for x in pairs], [x[1] for x in pairs]))
            hashes[f"{model}/{arm}_s{seed}"] = sha(path)
    return sets, hashes


def write_once(path, data):
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"frozen judge input changed: {path}")
    else:
        path.write_bytes(data)


def csv_bytes(header, records):
    import io
    f = io.StringIO(newline="")
    w = csv.writer(f, lineterminator="\n")
    w.writerow(header)
    w.writerows(records)
    return f.getvalue().encode("utf-8")


def prepare(model, *, include_raw_lt=False, only_changed=False):
    if model == "all":
        return {m: prepare(m, include_raw_lt=include_raw_lt, only_changed=only_changed) for m in MODELS}
    sets, hashes = answer_sets(model, include_raw_lt=include_raw_lt, only_changed=only_changed)
    unique, mapping = mapping_for(sets)
    shared = output_dir(model, include_raw_lt=include_raw_lt, only_changed=only_changed)
    shared.mkdir(parents=True, exist_ok=True)
    questions = [[uid, q, gold, "Shared"] for (q, gold, _), uid in unique.items()]
    answers = [[q, gold, pred] for q, gold, pred in unique]
    write_once(shared / "questions.csv", csv_bytes(["query_id", "Question", "Gold Answer", "Type"], questions))
    write_once(shared / "answers.csv", csv_bytes(["Question", "Gold Answer", "minirag"], answers))
    manifest = {"protocol": "gemini-3.5-flash-lite / prompt V1 / 3 passes / seed 13 / strict labels",
                "model": model, "preview": only_changed, "include_raw_lt": include_raw_lt,
                "answer_sha256": hashes, "n_original": len(mapping), "n_unique": len(unique),
                "calls_without_sharing": 3 * len(mapping), "calls_with_sharing": 3 * len(unique),
                "calls_saved": 3 * (len(mapping) - len(unique)), "mapping": mapping}
    write_once(shared / "mapping.json", (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode())
    print(json.dumps({k: v for k, v in manifest.items() if k != "mapping" and k != "answer_sha256"}, indent=2))
    return manifest


def run_judge(model, *, include_raw_lt=False, only_changed=False):
    if model == "all":
        for m in MODELS:
            run_judge(m, include_raw_lt=include_raw_lt, only_changed=only_changed)
        return
    prepare(model, include_raw_lt=include_raw_lt, only_changed=only_changed)
    shared = output_dir(model, include_raw_lt=include_raw_lt, only_changed=only_changed)
    env = os.environ.copy()
    # The worktree has no .env. Read the existing parent file without modifying it.
    from dotenv import dotenv_values
    for key, val in dotenv_values(Path(r"E:\Project\MiniRAG\.env")).items():
        if val is not None:
            env.setdefault(key, val)
    if not any(k.startswith("GEMINI_API_KEY") and v for k, v in env.items()):
        raise ValueError("Gemini judge key missing")
    judge_dir = shared / "judge"
    args = [str(PY), "reproduce/research/judge_run.py", "--questions", str(shared / "questions.csv"),
            "--answers", str(shared / "answers.csv"), "--run-dir", str(judge_dir),
            "--judgemodel", "gemini-3.5-flash-lite", "--passes", "3", "--seed", "13",
            "--invalid-tries", "3", "--abstain-after", "3"]
    if (judge_dir / "manifest.json").exists():
        args.append("--resume")
    subprocess.run(args, cwd=ROOT, env=env, check=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("prepare", "run"))
    p.add_argument("--model", choices=(*MODELS, "all"), required=True)
    p.add_argument("--include-raw-lt", action="store_true")
    p.add_argument("--only-changed", action="store_true")
    a = p.parse_args()
    if a.action == "prepare":
        prepare(a.model, include_raw_lt=a.include_raw_lt, only_changed=a.only_changed)
    else:
        run_judge(a.model, include_raw_lt=a.include_raw_lt, only_changed=a.only_changed)


if __name__ == "__main__":
    main()
