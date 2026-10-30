"""Offline audit, registered statistics and final report after all test runs.

No API clients are called here. Incomplete votes or mismatched inputs refuse
analysis rather than changing the denominator. Test contents are read only by
this explicitly invoked post-run command.
"""
import argparse
import ast
import collections
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import statistics

from .common import DEFAULT_REPO, load_repo, now, read_json, read_jsonl, sha, source_hashes, write_json

LABELS = ("accurate", "error", "neither")
SEEDS = (101, 202, 303)
CONFIGS = ("C0", "C1")


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def unique(rows, key="query_id"):
    result = {}
    for row in rows:
        if row[key] in result:
            raise ValueError("Duplicate " + key)
        result[row[key]] = row
    return result


def records(path):
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def load_module(repo, filename, name):
    spec = importlib.util.spec_from_file_location(name, repo / "reproduce/research" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def audit_judge(repo, folder, questions, qpath, judge):
    directory = folder / "judge"
    manifest = read_json(directory / "manifest.json")
    tree = ast.parse((repo / "reproduce/Step_2_evaluate.py").read_text(encoding="utf-8"))
    prompt = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == "JUDGE_PROMPT" for t in n.targets))
    expected = {"questions_sha256": sha(qpath), "answers_sha256": sha(folder / "answers.csv"),
                "judge_model": "gemini-flash-lite-latest", "passes": 3, "seed": 13, "invalid_tries": 3,
                "answer_column": "minirag", "label_contract": list(LABELS),
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()}
    if any(manifest.get(k) != v for k, v in expected.items()):
        raise ValueError("Judge identity mismatch: " + str(directory))
    journal = list(records(directory / "judge.jsonl"))
    latest = {(r["query_id"], r["pass"]): r for r in journal}
    if set(latest) != {(q, p) for q in questions for p in (1, 2, 3)}:
        raise ValueError("Incomplete or unexpected judge coverage")
    for row in latest.values():
        if row.get("status") != "ok" or row.get("label") not in LABELS:
            raise ValueError("Incomplete judge verdict")
        last = row["attempts"][-1]
        if judge.parse_label(last.get("raw")) != row["label"]:
            raise ValueError("Raw verdict/parser mismatch")
    per_question = unique(read_csv(directory / "per_question.csv"))
    if set(per_question) != set(questions):
        raise ValueError("Judge CSV coverage mismatch")
    for q, row in per_question.items():
        labels = [latest[(q, p)]["label"] for p in (1, 2, 3)]
        if (row["Type"] != questions[q]["Type"] or row["majority"] != judge.majority(labels)
                or [row[f"pass{p}"] for p in (1, 2, 3)] != labels):
            raise ValueError("Judge CSV/journal mismatch")
    summary = read_json(directory / "summary.json")
    if summary.get("status") != "completed" or summary.get("n_questions") != len(questions):
        raise ValueError("Invalid judge summary")
    return per_question, latest, journal, {p.name: sha(p) for p in directory.iterdir()
                                         if p.name in ("manifest.json", "summary.json", "per_question.csv", "judge.jsonl")}


def source_ids(context, chunk_text):
    if context is None:
        return []
    match = re.search(r"-----Sources-----\s*```csv\s*\n(.*?)\n```", context, re.S)
    if not match:
        raise ValueError("Missing Sources section")
    rows = list(csv.reader(io.StringIO(match.group(1))))
    if not rows or rows[0] != ["id", "content"]:
        raise ValueError("Unexpected Sources schema")
    ids = []
    for row in rows[1:]:
        if len(row) != 2:
            raise ValueError("Unexpected Sources row")
        matches = chunk_text.get(row[1], [])
        if len(matches) != 1:
            raise ValueError("Source not uniquely found in frozen index")
        ids.append(matches[0])
    return ids


def recall_summary(rows):
    rows = [r for r in rows if r["n_facts"]]
    if not rows:
        return {"n": 0, "micro_fact_recall_pct": None, "macro_fact_recall_pct": None,
                "all_evidence_pct": None, "note": "Null has no evidence; recall undefined"}
    return {"n": len(rows), "n_facts": sum(r["n_facts"] for r in rows),
            "hit_facts": sum(r["hit_facts"] for r in rows),
            "micro_fact_recall_pct": 100 * sum(r["hit_facts"] for r in rows) / sum(r["n_facts"] for r in rows),
            "macro_fact_recall_pct": 100 * statistics.mean(r["hit_facts"] / r["n_facts"] for r in rows),
            "all_evidence_pct": 100 * sum(r["hit_facts"] == r["n_facts"] for r in rows) / len(rows)}


def distribution(rows, latest, early_ids):
    n = len(rows)
    passes = [{label: 100 * sum(latest[(q, p)]["label"] == label for q in rows) / n for label in LABELS}
              for p in (1, 2, 3)]
    return {"n": n, "early_exit": len(set(rows) & early_ids),
            "majority": {label: 100 * sum(r["majority"] == label for r in rows.values()) / n
                         for label in (*LABELS, "no_majority")},
            "per_pass": passes,
            "judge_mean_sd": {label: {"mean": statistics.mean(p[label] for p in passes),
                                      "sd": statistics.stdev(p[label] for p in passes)} for label in LABELS}}


def request_summary(requests):
    requests = list(requests)
    ok = [r for r in requests if r.get("ok")]
    out = {"attempts": len(requests), "http_errors": len(requests) - len(ok),
           "successful_http": len(ok), "finish_reasons": dict(collections.Counter(r.get("finish_reason") for r in ok))}
    out["response_models"] = dict(collections.Counter(r.get("response_model") or "unavailable" for r in ok))
    for field in ("prompt_tokens", "completion_tokens", "latency_s"):
        values = [r[field] for r in ok if isinstance(r.get(field), (int, float))]
        out[field] = {"known_sum": sum(values) if values else None, "observed_requests": len(values),
                      "missing_requests": len(ok) - len(values)}
    out["latency_note"] = "Sum of HTTP latencies is not wall time or GPU billing."
    return out


def check_models(requests, expected):
    if any(r.get("ok") and r.get("response_model") and r["response_model"] != expected for r in requests):
        raise ValueError("Unexpected response model in request trace")


def csv_out(path, rows):
    with Path(path).open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def analyze(repo, run_root, out, expected_n=2156, expected_null=254, dev_dir=None):
    repo, run_root, out = Path(repo), Path(run_root), Path(out)
    load_repo(repo)
    from minirag.prompt import PROMPTS
    judge = load_module(repo, "judge_run.py", "phase3_analysis_judge")
    compare = load_module(repo, "compare_mhr.py", "phase3_analysis_compare")
    manifest = read_json(run_root / "RUN_MANIFEST.json")
    if manifest["configs"] != list(CONFIGS) or manifest["seeds"] != list(SEEDS):
        raise ValueError("Unregistered test configuration/seed set")
    if manifest["source_hashes"] != source_hashes(repo):
        raise ValueError("Source changed since test start")
    qpath = run_root / "test_internal.csv"
    questions = unique(read_csv(qpath))
    if len(questions) != expected_n or sum(q["Type"] == "null" for q in questions.values()) != expected_null:
        raise ValueError("Wrong test or Null count")
    if read_json(run_root / "TEST_INPUT.json")["sha256"] != sha(qpath):
        raise ValueError("Frozen test input changed")
    index = Path(manifest["index_path"])
    from .validate import index_check
    if index_check(index) != manifest["index_manifest_sha256"]:
        raise ValueError("Frozen index changed")
    chunks = read_json(index / "kv_store_text_chunks.json")
    chunk_text = collections.defaultdict(list)
    for cid, chunk in chunks.items():
        chunk_text[chunk["content"]].append(cid)
    gold = unique(r for r in records(repo / "dataset/MultiHop-RAG/processed/gold_chunks.jsonl") if r["query_id"] in questions)
    if set(gold) != set(questions):
        raise ValueError("Missing evidence mapping for test")
    result = {"status": "completed", "at": now(), "test_n": len(questions), "valid_votes": 0,
              "seeds": {}, "efficiency": {}, "provenance": {"questions_sha256": sha(qpath),
              "run_manifest_sha256": sha(run_root / "RUN_MANIFEST.json"), "index_manifest_sha256": index_check(index),
              "analysis_code_sha256": sha(__file__),
              "source_hashes": source_hashes(repo)}, "test_scope": "confirmatory_C0_C1_only"}
    joined, retrieval = [], []
    for seed in SEEDS:
        judged, summaries = {}, {}
        result["efficiency"][str(seed)] = {}
        seed_dir = run_root / "qa" / f"s{seed}"
        kw = seed_dir / "requests.jsonl"
        keyword_requests = list(records(kw)) if kw.exists() else []
        check_models(keyword_requests, "Qwen/Qwen2.5-3B-Instruct")
        result["efficiency"][str(seed)]["shared_keywords"] = request_summary(keyword_requests) if kw.exists() else {"status": "unavailable"}
        for config in CONFIGS:
            folder = seed_dir / f"{config}_s{seed}"
            rows, latest, journal, hashes = audit_judge(repo, folder, questions, qpath, judge)
            judged[config] = rows
            answers = unique(records(folder / "answers.jsonl"))
            contexts = unique(records(folder / "contexts.jsonl"))
            if set(answers) != set(questions) or set(contexts) != set(questions):
                raise ValueError("QA coverage mismatch")
            exported = read_csv(folder / "answers.csv")
            if len(exported) != len(questions):
                raise ValueError("Answer export incomplete")
            for q, a in zip(questions.values(), exported):
                if (a["Question"] != q["Question"] or a["Gold Answer"] != q["Gold Answer"]
                        or a["minirag"] != answers[q["query_id"]]["answer"]):
                    raise ValueError("Answer CSV/journal alignment mismatch")
            logs = {(r["query"], r["context_sha256"]): r for r in records(folder / "context.jsonl")}
            early_ids = {q for q, a in answers.items() if a["answer"] == PROMPTS["fail_response"]}
            groups = {"all": rows} | {t: {q: r for q, r in rows.items() if r["Type"] == t}
                                      for t in sorted({r["Type"] for r in rows.values()})}
            summaries[config] = {name: distribution(group, latest, early_ids) for name, group in groups.items()}
            for qid, question in questions.items():
                context = contexts[qid]
                ids = source_ids(context["context"], chunk_text) if context["status"] == "ok" else []
                if context["status"] == "ok":
                    chash = hashlib.sha256(context["context"].encode()).hexdigest()
                    log = logs.get((question["Question"], chash))
                    if log is None or log["chunk_ids"] != ids:
                        raise ValueError("Context log IDs/hash do not match actual Sources")
                facts = gold[qid]["evidence"]
                hits = 0
                for fact in facts:
                    candidates = set(fact["chunk_ids"])
                    if not candidates or fact["located"] not in ("inside", "spans"):
                        raise ValueError("Invalid gold evidence mapping")
                    hits += int(candidates <= set(ids) if fact["located"] == "spans" else bool(candidates & set(ids)))
                retrieval.append({"seed": seed, "config": config, "query_id": qid, "Type": question["Type"],
                                  "n_facts": len(facts), "hit_facts": hits, "n_sources": len(ids),
                                  "context_status": context["status"]})
                joined.append({"seed": seed, "config": config, "query_id": qid, "Type": question["Type"],
                               "pass1": rows[qid]["pass1"], "pass2": rows[qid]["pass2"], "pass3": rows[qid]["pass3"],
                               "majority": rows[qid]["majority"], "early_exit": qid in early_ids})
            req_path = folder / "requests.jsonl"
            generation_requests = list(records(req_path)) if req_path.exists() else []
            judge_requests = [r for entry in journal for a in entry["attempts"] for r in a.get("requests", [])]
            check_models(generation_requests, "Qwen/Qwen2.5-3B-Instruct")
            check_models(judge_requests, "gemini-flash-lite-latest")
            result["efficiency"][str(seed)][config] = {
                "generation": request_summary(generation_requests) if req_path.exists() else {"status": "unavailable"},
                "judge": request_summary(judge_requests),
                "context_timing_note": "Shared prefix; per-config context times are not standalone retrieval latency."}
            result["provenance"][f"{config}_s{seed}"] = {"judge": hashes,
                "qa": {name: sha(folder / name) for name in ("answers.csv", "answers.jsonl", "contexts.jsonl", "context.jsonl")}}
            result["valid_votes"] += len(latest)
        comparisons = {"all": compare.compare(judged["C0"], judged["C1"])}
        comparisons.update({t: compare.compare(judged["C0"], judged["C1"], [t])
                            for t in sorted({q["Type"] for q in questions.values()})})
        recall = {c: {name: recall_summary([r for r in retrieval if r["seed"] == seed and r["config"] == c
                                          and (name == "all" or r["Type"] == name)])
                      for name in summaries[c]} for c in CONFIGS}
        result["seeds"][str(seed)] = {"quality": summaries, "paired_C1_vs_C0": comparisons, "evidence_recall": recall}
    if result["valid_votes"] != expected_n * len(CONFIGS) * len(SEEDS) * 3:
        raise ValueError("Wrong final valid vote total")
    primary = [result["seeds"][str(s)]["paired_C1_vs_C0"]["all"]["primary_accurate"] for s in SEEDS]
    nulls = [result["seeds"][str(s)]["paired_C1_vs_C0"]["null"]["secondary_error"] for s in SEEDS]
    result["registered_decisions"] = {
        "RQ2_improvement_confirmed": all(p["diff"] > 0 and p["p"] < 0.05 for p in primary),
        "RQ2_noninferiority_minus3_confirmed": all(p["noninferior_at_-3"] for p in primary),
        "RQ5_null_error_increase_confirmed": all(p["err_b"] > p["err_a"] and p["p"] < 0.05 for p in nulls),
        "rule": "Separate exact McNemar per seed; all three in the predicted direction with p<0.05. RQ5 is secondary, unadjusted.",
        "not_confirmed_does_not_mean_no_effect": True}
    result["generation_variability"] = {c: {label: {
        "mean": statistics.mean(result["seeds"][str(s)]["quality"][c]["all"]["majority"][label] for s in SEEDS),
        "sd": statistics.stdev(result["seeds"][str(s)]["quality"][c]["all"]["majority"][label] for s in SEEDS)}
        for label in (*LABELS, "no_majority")} for c in CONFIGS}
    budget_file = run_root / "GPU_STAGE_BUDGET.json"
    result["execution_measurements"] = {"qwen_stage_budget": read_json(budget_file) if budget_file.exists() else None,
        "note": "Qwen stage wall time includes local setup/cold starts and excludes server idle after each stage; it is not billed GPU time."}
    result["dev_exploratory"] = {}
    if dev_dir:
        for name in ("dev_results.json", "C1_vs_C0.json", "C1_vs_C2.json", "C2_vs_C0.json"):
            p = Path(dev_dir) / name
            result["dev_exploratory"][name] = {"sha256": sha(p), "result": read_json(p)}
    result["measurement_limits"] = ["Gemini latest alias can drift; human judge validation deferred.",
        "C0 is the repaired baseline; the paper is a reference with a different judge.",
        "C2/C3 ablations are dev-only; no C2 test or C_orig was added.",
        "Evidence Recall measures actual Sources, not explanation faithfulness.",
        "Worker/HTTP times and token counts do not measure provider billing; actual cost unavailable without billing.",
        "Shared corpus between dev/test, missing article headers in later chunks and index truncation/loop artifacts remain limitations."]
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "TEST_RESULTS.json", result)
    csv_out(out / "test_per_question.csv", joined)
    csv_out(out / "test_retrieval.csv", retrieval)
    render_report(out / "MULTIHOP_RAG_REPORT.md", result)
    write_json(out / "ANALYSIS_COMPLETED.json", {"status": "completed", "at": now(), "valid_votes": result["valid_votes"],
        "artifacts": {p.name: sha(p) for p in out.iterdir() if p.is_file() and p.name != "ANALYSIS_COMPLETED.json"}})
    return result


def render_report(path, data):
    lines = ["# Kết quả MultiHop RAG Phase 3", "", f"Test {data['test_n']} câu; C0/C1; ba seed sinh; ba phiếu Gemini/đáp án.", "",
             "| Seed | Cấu hình | Accuracy đa số | Error | Neither | Không đa số | Accuracy mean ± SD judge |", "|---|---|---:|---:|---:|---:|---:|"]
    for seed, block in data["seeds"].items():
        for c in CONFIGS:
            g = block["quality"][c]["all"]
            m, j = g["majority"], g["judge_mean_sd"]["accurate"]
            lines.append(f"| {seed} | {c} | {m['accurate']:.2f} | {m['error']:.2f} | {m['neither']:.2f} | {m['no_majority']:.2f} | {j['mean']:.2f} ± {j['sd']:.2f} |")
    lines += ["", "| Seed | C1−C0 (điểm %) | Cặp lên/xuống | Exact p | CI95 ghép cặp |", "|---|---:|---:|---:|---|"]
    for seed, block in data["seeds"].items():
        p = block["paired_C1_vs_C0"]["all"]["primary_accurate"]
        lines.append(f"| {seed} | {p['diff']:+.2f} | {p['up']}/{p['down']} | {p['p']:.6g} | {p['ci95']} |")
    lines += ["", "## Kết quả theo loại câu", "", "| Seed | Cấu hình | Loại | N | Accuracy | Error | Neither | Không đa số |", "|---|---|---|---:|---:|---:|---:|---:|"]
    for seed, block in data["seeds"].items():
        for c in CONFIGS:
            for kind, group in block["quality"][c].items():
                if kind == "all":
                    continue
                m = group["majority"]
                lines.append(f"| {seed} | {c} | {kind} | {group['n']} | {m['accurate']:.2f} | {m['error']:.2f} | {m['neither']:.2f} | {m['no_majority']:.2f} |")
    lines += ["", "## Error trên Null", "", "Phép thử phụ RQ5; các phép so khác theo loại câu là mô tả/thăm dò.", "",
              "| Seed | N Null | Error C0 | Error C1 | Cặp giảm/tăng error | Exact p |", "|---|---:|---:|---:|---:|---:|"]
    for seed, block in data["seeds"].items():
        n = block["paired_C1_vs_C0"]["null"]
        e = n["secondary_error"]
        lines.append(f"| {seed} | {n['n']} | {e['err_a']:.2f} | {e['err_b']:.2f} | {e['fewer_errors']}/{e['more_errors']} | {e['p']:.6g} |")
    lines += ["", "## Evidence Recall trên Sources", "", "Loại Null không có evidence nên recall là N/A.", "",
              "| Seed | Cấu hình | N có evidence | Micro fact recall | Macro fact recall | Đủ toàn bộ evidence |", "|---|---|---:|---:|---:|---:|"]
    for seed, block in data["seeds"].items():
        for c in CONFIGS:
            r = block["evidence_recall"][c]["all"]
            lines.append(f"| {seed} | {c} | {r['n']} | {r['micro_fact_recall_pct']:.2f} | {r['macro_fact_recall_pct']:.2f} | {r['all_evidence_pct']:.2f} |")
    lines += ["", "## Biến động giữa seed sinh", "", "SD này được tính trên accuracy/error đa số của ba seed, riêng với SD judge ở bảng đầu.", "",
              "| Cấu hình | Accuracy mean ± SD sinh | Error mean ± SD sinh |", "|---|---:|---:|"]
    for c, values in data["generation_variability"].items():
        a, e = values["accurate"], values["error"]
        lines.append(f"| {c} | {a['mean']:.2f} ± {a['sd']:.2f} | {e['mean']:.2f} ± {e['sd']:.2f} |")
    lines += ["", "## Request và độ bao phủ", "", f"Đã kiểm {data['valid_votes']} phiếu cuối hợp lệ. Phiếu lỗi được lưu trong journal nhưng không gán thành nhãn.", "",
              "| Seed | Cấu hình | HTTP sinh / lỗi | HTTP judge / lỗi |", "|---|---|---:|---:|"]
    for seed, block in data["efficiency"].items():
        for c in CONFIGS:
            g, j = block[c]["generation"], block[c]["judge"]
            lines.append(f"| {seed} | {c} | {g.get('attempts', 'N/A')} / {g.get('http_errors', 'N/A')} | {j['attempts']} / {j['http_errors']} |")
    if data["dev_exploratory"]:
        lines += ["", "## Ablation dev một seed", "", "| Phép so | Hiệu số accuracy | Exact p | Vai trò |", "|---|---:|---:|---|"]
        for filename in ("C1_vs_C0.json", "C1_vs_C2.json", "C2_vs_C0.json"):
            entry = data["dev_exploratory"][filename]["result"]
            p = entry["overall"]["primary_accurate"]
            lines.append(f"| {entry['b']} vs {entry['a']} | {p['diff']:+.2f} | {p['p']:.6g} | Thăm dò dev |")
    decision = data["registered_decisions"]
    lines += ["", "RQ2: " + ("Xác nhận cải thiện theo tiêu chí ba seed đã đăng ký." if decision["RQ2_improvement_confirmed"] else "Chưa xác nhận cải thiện theo tiêu chí ba seed đã đăng ký; không suy ra hiệu ứng bằng không."),
              "", "RQ5: " + ("Xác nhận error Null tăng theo tiêu chí đã đăng ký." if decision["RQ5_null_error_increase_confirmed"] else "Chưa xác nhận error Null tăng theo tiêu chí đã đăng ký; không suy ra không có rủi ro."),
              "", "Bảng theo bốn loại câu, Null, Evidence Recall micro/macro/đủ toàn bộ facts, SD giữa seed và số đo request/token được lưu trong TEST_RESULTS.json. test_per_question.csv và test_retrieval.csv giữ dữ liệu để tái tính.",
              "", "Ablation C1/C2 và C2/C0 thuộc dev một seed; kết quả test chỉ xác nhận C1/C0. Các file dev đính kèm giữ nguyên hash và vai trò thăm dò.", "", "## Giới hạn", ""]
    lines += ["- " + text for text in data["measurement_limits"]]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    p.add_argument("--run-root", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--dev-report-dir", type=Path)
    args = p.parse_args()
    analyze(args.repo, args.run_root, args.out, dev_dir=args.dev_report_dir)


if __name__ == "__main__":
    main()
