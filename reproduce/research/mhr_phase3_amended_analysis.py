"""Audit a versioned three-slot structured rejudge, then use frozen statistics.

The V1 audit is unchanged for every original valid slot. The amended cohort
auditor validates raw JSON, dispatch ledger, prompt/model and original hashes;
it never feeds a normalized string to V1 as if that string were an API reply.
"""
import argparse
import collections
import copy
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from reproduce.research.mhr_phase3 import analysis as frozen
from reproduce.research.mhr_phase3.common import now, read_json, sha
from reproduce.research.recover_mhr_phase3_windows import write_status
from reproduce.research import mhr_phase3_structured_rejudge as rejudge


def merge_votes(latest, valid, questions, identity):
    expected = {(q, p) for q in questions for p in (1, 2, 3)}
    if set(latest) != expected:
        raise ValueError("Original slot coverage differs")
    missing = {key for key, row in latest.items() if row.get("status") != "ok"}
    allowed = {(identity["query_id"], p) for p in (1, 2, 3)}
    if missing != allowed or set(valid) != {1, 2, 3}:
        raise ValueError("Attempt to amend an already valid or unregistered slot")
    merged = dict(latest)
    for p, event in valid.items():
        label = rejudge.parse_response(event.get("raw"))
        if event.get("response_model") != identity["model"] or event.get("finish_reason") != "stop" or label is None:
            raise ValueError("Invalid structured replacement response")
        traces = event.get("requests", [])
        if len(traces) != 1 or not traces[0].get("ok") or traces[0].get("prompt_sha256") != identity["prompt_sha256"]:
            raise ValueError("Missing native request receipt or changed prompt")
        if traces[0].get("response_text") != event["raw"]:
            raise ValueError("Structured raw/HTTP receipt mismatch")
        merged[(identity["query_id"], p)] = {"query_id": identity["query_id"], "pass": p,
            "status": "ok", "label": label, "type": questions[identity["query_id"]]["Type"],
            "evaluation_version": identity["evaluation_version"],
            "attempts": [{"ok": True, "raw": event["raw"], "label": label, "requests": traces,
                          "response_format_sha256": rejudge.digest(identity["response_format"])}]}
    return merged


def amended_auditor(args, identity, state, events, original_audit):
    def audit(repo, folder, questions, qpath, judge):
        if folder.name != "C1_s101":
            return original_audit(repo, folder, questions, qpath, judge)
        directory = folder / "judge"; manifest = read_json(directory / "manifest.json")
        expected = {"questions_sha256": sha(qpath), "answers_sha256": sha(folder / "answers.csv"),
            "judge_model": identity["model"], "passes": 3, "seed": 13, "invalid_tries": 3,
            "answer_column": "minirag", "label_contract": list(rejudge.LABELS),
            "prompt_sha256": identity["prompt_template_sha256"]}
        if any(manifest.get(k) != value for k, value in expected.items()):
            raise ValueError("Original amended-cohort manifest changed")
        journal = list(frozen.records(directory / "judge.jsonl"))
        latest = {(r["query_id"], r["pass"]): r for r in journal}
        for row in latest.values():
            if row.get("status") == "ok":
                if row.get("label") not in rejudge.LABELS or judge.parse_label(row["attempts"][-1].get("raw")) != row["label"]:
                    raise ValueError("Original V1 valid vote failed its frozen parser")
        old_csv = frozen.unique(frozen.read_csv(directory / "per_question.csv"))
        if set(old_csv) != set(questions):
            raise ValueError("Original CSV coverage changed")
        for q, row in old_csv.items():
            old = [latest[(q, p)] for p in (1, 2, 3)]
            done = all(r["status"] == "ok" for r in old)
            labels = [r["label"] or r["status"] for r in old]
            if ([row[f"pass{p}"] for p in (1, 2, 3)] != labels or row["Type"] != questions[q]["Type"]
                    or row["majority"] != (judge.majority(labels) if done else "incomplete")):
                raise ValueError("Original CSV/journal mismatch")
        merged = merge_votes(latest, state["valid"], questions, identity)
        rows = {q: {"query_id": q, "Type": questions[q]["Type"],
                   **{f"pass{p}": merged[(q, p)]["label"] for p in (1, 2, 3)},
                   "majority": judge.majority([merged[(q, p)]["label"] for p in (1, 2, 3)])} for q in questions}
        frozen.csv_out(args.amendment / "amended_C1_s101_per_question.csv", list(rows.values()))
        # Include every new HTTP attempt, not only the three accepted responses.
        new_records = []
        for event in events:
            if event["event"] != "response":
                continue
            label = rejudge.parse_response(event.get("raw")) if event.get("ok") else None
            new_records.append({"query_id": identity["query_id"], "pass": event["pass"],
                "status": "ok" if label else "judge_failed", "label": label, "type": identity["type"],
                "attempts": [{"ok": event.get("ok"), "raw": event.get("raw"), "label": label,
                              "requests": event.get("requests", [])}]})
        hashes = {p.name: sha(p) for p in directory.iterdir() if p.name in ("manifest.json", "per_question.csv", "judge.jsonl")}
        hashes.update({"amendment/" + name: sha(args.amendment / name)
                       for name in ("AMENDMENT.json", "events.jsonl", "NEW_VALID_VOTES.json")})
        return rows, merged, journal + new_records, hashes
    return audit


def sensitivity(result, joined):
    from math import comb
    rows = [r for r in joined if int(r["seed"]) == 101]
    a = {r["query_id"]: r for r in rows if r["config"] == "C0"}
    b = {r["query_id"]: r for r in rows if r["config"] == "C1"}
    outcomes = []
    def pvalue(up, down):
        n = up + down
        return min(1.0, 2 * sum(comb(n, k) for k in range(min(up, down) + 1)) / 2 ** n) if n else 1.0
    for hypothetical in (*rejudge.LABELS, "no_majority"):
        for kind in ("all", "null"):
            ids = [q for q in a if kind == "all" or a[q]["Type"] == kind]
            for label in ("accurate", "error"):
                af = [a[q]["majority"] == label for q in ids]
                bf = [(hypothetical if q == "mhr-1114" else b[q]["majority"]) == label for q in ids]
                up = sum(not x and y for x, y in zip(af, bf)); down = sum(x and not y for x, y in zip(af, bf))
                outcomes.append({"hypothetical_C1_s101_mhr1114_majority": hypothetical, "group": kind,
                    "metric": label, "n": len(ids), "C1_minus_C0_pp": 100 * (sum(bf) - sum(af)) / len(ids),
                    "up": up, "down": down, "exact_two_sided_mcnemar_p": pvalue(up, down)})
    return {"status": "hypothetical_sensitivity_not_substitute_labels", "affected_query": "mhr-1114",
            "affected_seed": 101, "scenarios": outcomes,
            "max_accuracy_shift_pp": 100 / 2156, "max_null_error_shift_pp": 100 / 254}


def exact_effect_displays(result):
    """Display the paired effect from counts, avoiding double rounding rates.

    Frozen McNemar p-values and bootstrap samples/intervals are untouched.
    Preserve the legacy display difference explicitly for reproducibility.
    """
    for block in result['seeds'].values():
        for comparison in block['paired_C1_vs_C0'].values():
            p = comparison['primary_accurate']
            p['diff_from_rounded_rates_pp'] = p['diff']
            p['diff_exact_pp'] = 100 * (p['up'] - p['down']) / comparison['n']
            p['diff'] = round(p['diff_exact_pp'], 2)


def extra_csvs(out, result):
    quality = []; paired = []; recall = []; efficiency = []
    for seed, block in result["seeds"].items():
        for cfg, groups in block["quality"].items():
            for kind, g in groups.items():
                quality.append({"seed": seed, "config": cfg, "group": kind, "n": g["n"], **g["majority"],
                    "accuracy_judge_mean": g["judge_mean_sd"]["accurate"]["mean"],
                    "accuracy_judge_sd": g["judge_mean_sd"]["accurate"]["sd"]})
                r = block["evidence_recall"][cfg][kind]
                recall.append({"seed": seed, "config": cfg, "group": kind,
                    **{key:r.get(key) for key in ('n','n_facts','hit_facts','micro_fact_recall_pct',
                        'macro_fact_recall_pct','all_evidence_pct','note')}})
        for kind, p in block["paired_C1_vs_C0"].items():
            a, e = p["primary_accurate"], p["secondary_error"]
            paired.append({"seed": seed, "group": kind, "n": p["n"], "accuracy_diff_pp": a["diff"],
                "accuracy_diff_exact_pp": a['diff_exact_pp'],
                "up": a["up"], "down": a["down"], "p_accuracy": a["p"], "ci95_low": a["ci95"][0],
                "ci95_high": a["ci95"][1], "error_diff_pp": e["err_b"] - e["err_a"], "p_error": e["p"]})
        for cfg, phases in result["efficiency"][seed].items():
            if cfg == "shared_keywords":
                phases = {"keywords": phases}
            for phase, counts in phases.items():
                if not isinstance(counts, dict):
                    continue
                efficiency.append({"seed": seed, "config": cfg, "phase": phase,
                    "http_attempts": counts.get("attempts"), "http_success": counts.get("successful_http"),
                    "http_errors": counts.get("http_errors"),
                    "prompt_tokens_known_sum": counts.get("prompt_tokens", {}).get("known_sum"),
                    "completion_tokens_known_sum": counts.get("completion_tokens", {}).get("known_sum"),
                    "http_latency_sum_seconds_not_wall": counts.get("latency_s", {}).get("known_sum")})
    for name, rows in (("quality_metrics.csv", quality), ("paired_comparisons.csv", paired),
                       ("evidence_recall.csv", recall), ("efficiency.csv", efficiency)):
        frozen.csv_out(out / name, rows)


def analyze(args):
    baseargs = argparse.Namespace(workspace=args.workspace, repo=args.repo, run_root=args.run_root, out=args.amendment)
    identity, prompt, proof = rejudge.prepare(baseargs)
    events = rejudge.journal(args.amendment / "events.jsonl")
    state = rejudge.ledger_state(events, rejudge.digest(identity))
    if set(state["valid"]) != {1, 2, 3}:
        raise ValueError("Three new valid structured votes required before analysis")
    original = frozen.audit_judge
    try:
        frozen.audit_judge = amended_auditor(args, identity, state, events, original)
        result = frozen.analyze(args.repo, args.run_root, args.out, dev_dir=args.run_root / "frozen_dev_reports")
    finally:
        frozen.audit_judge = original
    result["evaluation_version"] = identity["evaluation_version"]
    result["test_scope"] = "C0_C1_test_with_user_authorized_posthoc_output_format_amendment"
    result["original_V1"] = {"status": "incomplete", "valid_votes": 38805, "target_votes": 38808,
                             "all_original_journals_unchanged": True}
    result["amendment"] = {"path": str(args.amendment), "identity": identity,
        "new_valid_votes": 3, "http_reservations": state["reserved_total"],
        "ledger_sha256": sha(args.amendment / "events.jsonl"), "accepted_labels": {str(p): e["label"] for p, e in state["valid"].items()},
        "analysis_adapter_sha256": sha(__file__), "posthoc": True}
    result["registered_decisions"]["applied_to_amended_evaluation"] = True
    exact_effect_displays(result)
    result["measurement_limits"] = [
        "Ba phiếu C1_s101/mhr-1114 được chấm lại bằng cùng Gemini và rubric, với JSON schema theo amendment được user duyệt sau test. V1 strict gốc vẫn thiếu3phiếu; không gọi bản có amendment là V1 nguyên gốc hoàn tất.",
        "Gemini latest là alias có thể đổi revision; chưa có nhãn người độc lập kiểm chuẩn, đặc biệt rubric Null còn hạn chế.",
        "C0 là baseline nhóm đã sửa, không phải tái tạo nguyên bản paper. Xếp hạng graph của C0 vẫn có dense-chunk bonus, không phải strict graph-only.",
        "C2/C3 chỉ chạy dev một seed. Test này chỉ so C0/B2, chưa đo đóng góp từng kênh hoặc toàn bộ graph trên MultiHop.",
        "Evidence Recall đo Sources thực sự đưa vào context, không đo độ trung thành lời giải hay toàn bộ thông tin Entities.",
        "Dev/test dùng chung corpus. Đây không phải phép kiểm tổng quát hoá sang các tài liệu hoàn toàn chưa thấy.",
        "Thời gian context dùng chung prefix không phải latency retrieval độc lập từng cấu hình. Tổng latency HTTP không phải wall-time hay tiền GPU.",
        "Chưa có billing cloud thực để xác nhận chi phí cuối. Cap8h là cumulative client Qwen-stage wall, không phải billing. Không có lần mua credits hoặc nâng paid tier trong luồng này."
    ]
    joined = frozen.read_csv(args.out / "test_per_question.csv")
    sens = sensitivity(result, joined)
    result["format_amendment_sensitivity"] = sens
    write_status(args.out / "FORMAT_AMENDMENT_SENSITIVITY.json", sens)
    extra_csvs(args.out, result)
    coverage = [{"seed": s, "config": c, "queries": 2156, "required_votes": 6468,
                 "original_valid_votes": proof["by_cohort"][f"{c}_s{s}"],
                 "new_structured_votes": 3 if (s,c)==(101,'C1') else 0, "amended_valid_votes":6468}
                for s in (101,202,303) for c in ('C0','C1')]
    frozen.csv_out(args.out / "coverage.csv", coverage)
    write_status(args.out / "TEST_RESULTS.json", result)
    frozen.render_report(args.out / "MULTIHOP_RAG_REPORT.md", result)
    report = (args.out / "MULTIHOP_RAG_REPORT.md").read_text(encoding='utf-8')
    disclosure = """\n## Phiên bản đánh giá và xử lý vận hành\n\nBản này dùng **Gemini V1 + amendment A1 chấm lại3slot có JSON schema**. Giữ nguyên12.936đáp án và38.805phiếu V1 hợp lệ. Ba phiếu mới thuộc C1/B2, seed101, câu mhr-1114, pass1/2/3, được gọi mới bằng cùng model/rubric/input; không lấy lại nhãn từ phản hồi cũ. V1 strict nguyên gốc vẫn38.805/38.808; bản có amendment đủ38.808/38.808phiếu.\n\nNgười dùng trực tiếp duyệt chấm lại3slot ngày30/10/2026. Giới hạn6HTTP calls, tối đa2mỗi slot, lấy phiếu đúng schema đầu tiên, không chọn theo nhãn. Ledger ghi dispatch trước gọi và fsync từng phản hồi; lưu riêng toàn bộ raw/receipt/hash. Structured output bảo đảm hợp đồng định dạng được kiểm, không phải bằng chứng nhãn đúng về ngữ nghĩa.\n\nSự cố vận hành: worker CPU gặp WinError5 khi thay STATUS.json ngày28/10; khôi phục tối đa5lần chỉ đúng lỗi đó và giữ prefix. Fair queue được đổi sang ưu tiên cohort chưa chấm trước retry; payload/phương pháp không đổi. Ngày29/10 tiến trình bị gián đoạn chưa rõ nguyên nhân, khôi phục14:24UTC+7 với78prefix journal nguyên vẹn. Ngày30/10 queue kết thúc needs_adjudication vì3slot hết32vòng; không reset budget gốc. Đây là sự cố và thay đổi vận hành/đánh giá được công khai, không phải đóng góp phương pháp retrieval.\n\nThống kê dùng query ghép cặp, exact McNemar hai phía và bootstrap10.000mẫu, seed13, riêng mỗi seed sinh. Không gộp6.468query-seed thành6.468câu độc lập. RQ5 là error trên254Null; các phân tích loại câu khác là phụ/thăm dò. SD judge và SD giữa seed sinh được báo riêng.\n\n"""
    heading, rest = report.split('\n',1)
    report = heading + disclosure + rest
    report += "\n## Độ nhạy với trường hợp chấm lại\n\nMột query ở seed101 có thể làm accuracy thay đổi tối đa0,04638điểm% hoặc error trên254Null tối đa0,39370điểm%. FORMAT_AMENDMENT_SENSITIVITY.json liệt kê cả4khả năng đa số (accurate/error/neither/no_majority) và exact McNemar tương ứng; đây là giả định độ nhạy, không gán chúng thành nhãn thật.\n"
    (args.out / "MULTIHOP_RAG_REPORT.md").write_text(report,encoding='utf-8')
    rejudge.check_frozen(baseargs, proof)
    write_status(args.out / "ANALYSIS_COMPLETED.json", {"status": "completed_amended_evaluation", "at": now(),
        "valid_votes": 38808, "original_V1_valid_votes": 38805, "new_structured_votes": 3,
        "original_source_and_journals_unchanged": True, "evaluation_version": identity["evaluation_version"],
        "artifacts": {p.name: sha(p) for p in args.out.iterdir() if p.is_file() and p.name!='ANALYSIS_COMPLETED.json'}})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','repo','run-root','amendment','out'):
        p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args(); analyze(args)
    print(json.dumps({'status':'completed_amended_evaluation','out':str(args.out),'valid_votes':38808}))


if __name__=='__main__':main()
