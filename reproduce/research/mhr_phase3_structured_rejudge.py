"""Bounded, authorized JSON rejudge of the three terminal Phase3 slots.

The frozen V1 source, manifests, QA and journals are read-only. New HTTP
responses and dispatch reservations live in a separate fsynced amendment ledger.
No original raw reply is reparsed into a replacement label.
"""
import argparse
import ast
import asyncio
import collections
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from reproduce.research.mhr_phase3.common import alive, load_repo, now, read_json, run_lock, sha, source_hashes
from reproduce.research.recover_mhr_phase3_windows import write_status

LABELS = ("accurate", "error", "neither")
TARGETS = {(101, "C1", "mhr-1114", p) for p in (1, 2, 3)}
FORMAT = {"type": "json_schema", "json_schema": {
    "name": "phase3_judge_label", "strict": True,
    "schema": {"type": "object", "properties": {"label": {"type": "string", "enum": list(LABELS)}},
               "required": ["label"], "additionalProperties": False}}}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def parse_response(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    try:
        obj = json.loads(raw, object_pairs_hook=pairs)
    except (ValueError, TypeError):
        return None
    return obj["label"] if isinstance(obj, dict) and set(obj) == {"label"} and obj["label"] in LABELS else None


def journal(path):
    if not Path(path).exists():
        return []
    raw = Path(path).read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise ValueError("Amendment ledger has a torn tail; preserve it for explicit recovery")
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def append_event(path, record):
    with Path(path).open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def ledger_state(events, identity):
    intents = {}; responses = {}; valid = {}
    for event in events:
        if event.get("identity_sha256") != identity:
            raise ValueError("Amendment ledger identity changed")
        p, attempt = event["pass"], event["attempt"]
        if p not in (1, 2, 3) or attempt not in (1, 2):
            raise ValueError("Unregistered slot/attempt")
        key = (p, attempt)
        if event["event"] == "dispatch_reserved":
            if key in intents or p in valid:
                raise ValueError("Duplicate dispatch or rejudge of an already valid slot")
            intents[key] = event
        elif event["event"] == "response":
            if key not in intents or key in responses:
                raise ValueError("Response without unique reservation")
            responses[key] = event
            label = parse_response(event.get("raw")) if event.get("ok") and event.get("finish_reason") == "stop" else None
            if label is not None:
                valid.setdefault(p, event | {"label": label})
        else:
            raise ValueError("Unknown ledger event")
    if len(intents) > 6:
        raise ValueError("Global HTTP budget exceeded")
    return {"valid": valid, "used": collections.Counter(p for p, _ in intents),
            "reserved_total": len(intents), "unresolved_dispatches": sorted(set(intents) - set(responses))}


def literal_prompt(repo):
    tree = ast.parse((repo / "reproduce/Step_2_evaluate.py").read_text(encoding="utf-8"))
    return next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "JUDGE_PROMPT" for t in n.targets))


def check_frozen(args, proof):
    validation = read_json(args.workspace / "outputs/phase3_acceleration/JUDGE_QUEUE_VALIDATION.json")
    manifest = read_json(args.run_root / "RUN_MANIFEST.json")
    if sha(args.run_root / "RUN_MANIFEST.json") != validation["original_manifest_sha256"]:
        raise ValueError("Original run manifest changed")
    package = Path(__file__).parent / "mhr_phase3"
    if any(sha(package / name) != value for name, value in validation["frozen_package_hashes"].items()):
        raise ValueError("Frozen seven-file package changed")
    if source_hashes(args.repo) != manifest["source_hashes"]:
        raise ValueError("Frozen source repo changed")
    if sha(args.run_root / "test_internal.csv") != read_json(args.run_root / "TEST_INPUT.json")["sha256"]:
        raise ValueError("Frozen test input changed")
    for seed in manifest["seeds"]:
        ready = read_json(args.run_root / f"READY_s{seed}.json")
        if ready["questions_sha256"] != sha(args.run_root / "test_internal.csv"):
            raise ValueError("READY test identity changed")
        for cfg in manifest["configs"]:
            if sha(args.run_root / "qa" / f"s{seed}" / f"{cfg}_s{seed}" / "answers.csv") != ready["answers"][cfg]:
                raise ValueError("QA answer changed")
    for item in proof["journal_full_prefixes"].values():
        p = args.workspace / item["path"]
        if p.stat().st_size != item["bytes"] or sha(p) != item["sha256"]:
            raise ValueError("Original judge journal changed")
    for folder in (args.run_root, args.run_root / "judge_consumer"):
        lock = folder / "RUNNING.lock"
        if lock.exists() and alive(read_json(lock)["pid"]):
            raise ValueError("Original production owner is alive")
    pending = read_json(args.run_root / "PENDING_JUDGE_SLOTS.json")["pending_ready_slots"]
    if {(s["seed"], s["config"], s["query_id"], s["pass"]) for s in pending} != TARGETS or len(pending) != 3:
        raise ValueError("Only the three user-authorized slots may be rejudged")
    if any(s["status"] != "parse_failed" or s["recorded_cycles"] != 32 for s in pending):
        raise ValueError("Original terminal retry state changed")
    return manifest


def prepare(args):
    proof_path = args.workspace / "outputs/phase3_acceleration/JUDGE_PENDING_DECISION_20261030.json"
    proof = read_json(proof_path)
    manifest = check_frozen(args, proof)
    folder = args.run_root / "qa/s101/C1_s101"
    with (args.run_root / "test_internal.csv").open(encoding="utf-8-sig", newline="") as f:
        questions = list(csv.DictReader(f))
    with (folder / "answers.csv").open(encoding="utf-8-sig", newline="") as f:
        answers = list(csv.DictReader(f))
    i = next(i for i, q in enumerate(questions) if q["query_id"] == "mhr-1114")
    q, answer = questions[i], answers[i]
    if q["Question"] != answer["Question"] or q["Gold Answer"] != answer["Gold Answer"]:
        raise ValueError("Question/answer alignment changed")
    template = literal_prompt(args.repo)
    prompt = template.format(question=q["Question"], gold=q["Gold Answer"], pred=answer["minirag"])
    message_sha = hashlib.sha256(repr([{"role": "user", "content": prompt}]).encode()).hexdigest()
    original = [r for r in journal(folder / "judge/judge.jsonl") if r["query_id"] == q["query_id"]]
    traces = [t for r in original for a in r["attempts"] for t in a.get("requests", []) if t.get("ok")]
    if not traces or any(t.get("prompt_sha256") != message_sha or t.get("max_tokens") is not None
                         or t.get("seed") is not None for t in traces):
        raise ValueError("Original prompt or sampling-option identity differs")
    identity = {"evaluation_version": "Gemini-V1-plus-A1-structured-rejudge", "model": manifest["judge_model"],
                "source_manifest_sha256": sha(args.run_root / "RUN_MANIFEST.json"),
                "proof_sha256": sha(proof_path), "script_sha256": sha(__file__),
                "prompt_template_sha256": hashlib.sha256(template.encode()).hexdigest(),
                "prompt_sha256": message_sha, "response_format": FORMAT, "passes": [1, 2, 3],
                "query_id": q["query_id"], "seed": 101, "config": "C1", "type": q["Type"],
                "max_http_per_slot": 2, "max_http_total": 6, "sampling": "provider defaults, as in original traces",
                "authorization_vi": "ừm chấm lại 3 slot gemini nhé",
                "original_38805_valid_votes_unchanged": True,
                "first_valid_schema_response_per_slot": True,
                "old_freeform_replies_not_reinterpreted": True,
                "scope": "post-hoc output-format and bounded retry amendment; original rubric/input/model unchanged"}
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "AMENDMENT.json"
    if path.exists():
        if read_json(path)["identity"] != identity:
            raise ValueError("Amendment identity mismatch; do not reset budget")
    else:
        write_status(path, {"at": now(), "identity": identity, "identity_sha256": digest(identity)})
        write_status(args.out / "INPUT.json", {"question": q["Question"], "gold": q["Gold Answer"],
                                               "pred": answer["minirag"], "formatted_prompt": prompt})
    if read_json(args.out / "INPUT.json")["formatted_prompt"] != prompt:
        raise ValueError("Stored amendment prompt changed")
    return identity, prompt, proof


class Backend:
    def __init__(self, repo):
        load_repo(repo)
        from dotenv import load_dotenv
        load_dotenv(repo / ".env")  # Normal existing runtime authentication; never printed or copied.
        from minirag.llm import gemini
        import llm_trace
        if urlparse(os.environ.get("GEMINI_API_BASE", gemini.GEMINI_BASE_URL)).hostname != "generativelanguage.googleapis.com":
            raise ValueError("Refuse non-Gemini endpoint")
        llm_trace.install()
        self.gemini, self.trace = gemini, llm_trace

    async def complete(self, model, prompt):
        g = self.gemini; pool = g._get_pool("chat")
        key = await pool.acquire(g._estimate_tokens(prompt) + 1000)
        traces = []
        try:
            with self.trace.trace(traces.append):
                response = await g._client(key).chat.completions.create(
                    model=model, messages=[{"role": "user", "content": prompt}], response_format=FORMAT, timeout=90)
        except Exception as exc:
            name = type(exc).__name__
            if name == "RateLimitError":
                pool.penalize(key)
            elif name in ("AuthenticationError", "PermissionDeniedError"):
                pool.disable(key)
            return {"ok": False, "error_type": name, "http_status": getattr(exc, "status_code", None), "requests": traces}
        pool.succeeded(key)
        choice = (response.choices or [None])[0]
        return {"ok": True, "raw": getattr(getattr(choice, "message", None), "content", None),
                "finish_reason": getattr(choice, "finish_reason", None), "response_model": response.model,
                "requests": traces}


async def execute_slots(out, identity, prompt, backend):
    identity_sha = digest(identity); ledger = out / "events.jsonl"
    for p in identity["passes"]:
        state = ledger_state(journal(ledger), identity_sha)
        if p in state["valid"]:
            continue
        for attempt in range(state["used"][p] + 1, 3):
            append_event(ledger, {"at": now(), "event": "dispatch_reserved", "pass": p, "attempt": attempt,
                                  "identity_sha256": identity_sha})
            response = await backend.complete(identity["model"], prompt)
            if response.get("ok") and response.get("response_model") != identity["model"]:
                response |= {"ok": False, "error_type": "ResponseModelMismatch"}
            append_event(ledger, {"at": now(), "event": "response", "pass": p, "attempt": attempt,
                                  "identity_sha256": identity_sha, **response})
            state = ledger_state(journal(ledger), identity_sha)
            write_status(out / "STATUS.json", {"at": now(), "status": "running", "valid_new_votes": len(state["valid"]),
                                                "http_reservations": state["reserved_total"]})
            if p in state["valid"]:
                break
            if response.get("http_status") == 400 or response.get("error_type") == "ResponseModelMismatch":
                break  # Unsupported schema is not permission to change model/format silently.
            await asyncio.sleep(2)
        if p not in state["valid"]:
            write_status(out / "STATUS.json", {"at": now(), "status": "needs_attention", "missing_pass": p,
                                                "valid_new_votes": len(state["valid"]), "http_reservations": state["reserved_total"]})
            return 2
    state = ledger_state(journal(ledger), identity_sha)
    write_status(out / "NEW_VALID_VOTES.json", {"at": now(), "identity_sha256": identity_sha,
                 "votes": [{"query_id": identity["query_id"], "pass": p, "seed": identity["seed"],
                            "config": identity["config"], **event} for p, event in sorted(state["valid"].items())]})
    write_status(out / "STATUS.json", {"at": now(), "status": "completed", "valid_new_votes": 3,
                                      "http_reservations": state["reserved_total"], "original_valid_votes": 38805,
                                      "amended_valid_votes": 38808, "original_V1_remains_incomplete": True})
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("workspace", "repo", "run-root", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--execute", action="store_true")
    args = p.parse_args()
    identity, prompt, proof = prepare(args)
    if not args.execute:
        print(json.dumps({"status": "prepared", "identity_sha256": digest(identity), "http_budget": 6}))
        return 0
    with run_lock(args.out):
        code = asyncio.run(execute_slots(args.out, identity, prompt, Backend(args.repo)))
        check_frozen(args, proof)
    print(json.dumps(read_json(args.out / "STATUS.json"), ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
