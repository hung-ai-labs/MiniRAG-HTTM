"""Kiem thu lop provenance / fail-closed cua report_e1. Chay tren thu muc tam, du lieu tong hop.
Khong doc, khong ghi raw log that; khong chay truy hoi.

    .venv/Scripts/python.exe reproduce/entity_resolution/test_provenance.py
"""

import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (HERE, ROOT, os.path.join(ROOT, "reproduce", "screening")):
    sys.path.insert(0, p)

import report_e1 as R  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), name, detail)
    if not cond:
        fails.append(name)


# ------------------------------------------------------------------ moi truong tong hop
def make_env(tmp, wrong_ids=False, stdout_text=None, report_delay=0.0):
    log_dir = os.path.join(tmp, "logs")
    eval_dir = os.path.join(log_dir, "eval")
    prov = os.path.join(log_dir, "provenance")
    arms = {"control": os.path.join(log_dir, "pair", "control"),
            "treatment": os.path.join(log_dir, "pair", "entres")}
    for d in (eval_dir, prov, *arms.values(), os.path.join(log_dir, "cache")):
        os.makedirs(d, exist_ok=True)
    for d in arms.values():                                    # file index gia, cu hon moc dong bang
        open(os.path.join(d, "graph_chunk_entity_relation.graphml"), "w").write("<g/>")
    freeze = os.path.join(log_dir, "reembed_pair_report.json")
    time.sleep(0.05)
    open(freeze, "w").write("{}")

    src_cache = os.path.join(tmp, "screening_cache.jsonl")
    cache = os.path.join(log_dir, "cache", "kw_cache.jsonl")
    open(src_cache, "w").write('{"prompt_sha256": "x", "result": "{}"}\n')
    shutil.copyfile(src_cache, cache)
    time.sleep(0.05)
    stdout_path = os.path.join(tmp, "process.output")
    open(stdout_path, "w").write("")                          # ctime = luc "khoi chay"
    time.sleep(0.05)

    rows = [{"Question": f"q{i}", "Type": "Single" if i < 159 else "Multi"} for i in range(180)]
    gold = {r["Question"]: ["c1"] for r in rows}
    corpus = {"c1": "alpha", "c2": "beta", "c3": "gamma"}

    data = {}
    for mode, fus in R.MODES.items():
        for arm in R.ARM_NAMES:
            recs = []
            for i, r in enumerate(rows):
                q = f"WRONG{i}" if wrong_ids else r["Question"]
                gids = ["c1", "c2"] if (arm == "treatment" or i % 2 == 0) else ["c2"]
                ranked = gids if mode == "graph" else ["c1", "c3"]
                recs.append({"question": q, "type": r["Type"], "none": False, "graph_ids": gids,
                             "chunk_ids": list(ranked), "ranked_ids": list(ranked), "vector_ids": ["c3"],
                             "fusion": fus, "graph_seeds": 5, "graph_paths": 10, "retrieval_ms": 100.0,
                             "n_chunks": len(ranked), "context_sha256": "x"})
            data[(arm, mode)] = recs
            with open(os.path.join(eval_dir, f"{arm}_{mode}.jsonl"), "w", encoding="utf-8") as f:
                for rec in recs:
                    f.write(json.dumps(rec) + "\n")
    time.sleep(0.05 + report_delay)

    # report kieu runner v1, so lieu tinh dung tu raw log
    checks = [{"name": n, "passed": True, "detail": "0" if "LLM" in n else ""}
              for n in R.runner_v1_expected_names()]
    for mode in R.MODES:
        c, t = data[("control", mode)], data[("treatment", mode)]
        rep = {"mode": mode, "fusion": R.MODES[mode], "arms": arms, "valid": True, "checks": checks,
               "graph_top30": {s: R._v1_paired(c, t, gold, "graph_ids", None if s == "ALL" else s)
                               for s in ("ALL", "Single", "Multi")},
               "final_chunks": {s: R._v1_paired(c, t, gold, "chunk_ids", None if s == "ALL" else s)
                                for s in ("ALL", "Single", "Multi")},
               "workload": {}}
        json.dump(rep, open(os.path.join(log_dir, f"eval_{mode}_report.json"), "w", encoding="utf-8"))
    for name in R.RUNNER_FILES_OTHER:
        open(os.path.join(log_dir, name), "w").write("runner output\n")

    if stdout_text is None:
        stdout_text = "tien kiem PASS\n" + "".join(f"  chay {r} -> x.jsonl\n" for r in R.RUNS)
    open(stdout_path, "w").write(stdout_text)

    ctx = R.Ctx(root=ROOT, log_dir=log_dir, eval_dir=eval_dir, prov_dir=prov, arms=arms,
                cache_path=cache, source_cache_path=src_cache, process_output=stdout_path,
                freeze_report=freeze, launch_source=None, current_runner=None, post_launch_patch=None,
                rows=rows, gold=gold, corpus=corpus,
                type_pools={"control": ['"person"'], "treatment": ['"person"']})
    return ctx


def status_of(checks, prefix):
    return [c.status for c in checks if c.name.startswith(prefix)]


# ================================================================== T1 manifest thieu truong cache
man = {"kind": "e1_retrieval_run_manifest", "schema": 2, "invocation": {}, "llm": {"calls": 0},
       "cache": {"path": "x"}, "runs": {}}
mv = R.validate_manifest(man, None)
check("T1 thieu ca sha256_before/after -> cache_content KHONG PASS",
      mv["cache_content"][0] == R.UNVERIFIED, mv["cache_content"])
check("T1 thieu ca so key truoc/sau (None == None) -> cache_key_count KHONG PASS",
      mv["cache_key_count"][0] == R.UNVERIFIED, mv["cache_key_count"])
man2 = dict(man, cache={"sha256_before": "a", "sha256_after": "b", "unique_keys_before": 200,
                        "unique_keys_after": 200})
mv2 = R.validate_manifest(man2, None)
check("T1 so key bang nhau nhung noi dung khac -> cache_content FAIL, khong bi che boi so key",
      mv2["cache_content"][0] == R.FAIL and mv2["cache_key_count"][0] == R.PASS,
      (mv2["cache_content"], mv2["cache_key_count"]))
check("T1 manifest thieu truong bat buoc -> UNVERIFIED",
      R.validate_manifest({"kind": "e1_retrieval_run_manifest"}, None)["manifest"][0] == R.UNVERIFIED)

# ================================================================== T3 luot dung lai khong mang provenance moi
tmp = tempfile.mkdtemp()
try:
    ctx = make_env(tmp)
    runs = {}
    for run in R.RUNS:
        arm, mode = run.split("/")
        p = os.path.join(ctx.eval_dir, f"{arm}_{mode}.jsonl")
        runs[run] = {"executed_in_this_invocation": True, "started_at": "t", "finished_at": "t", "records": 180,
                     "raw_log_sha256": R.sha256_file(p), "index_sha256_before": {"a": "1"},
                     "index_sha256_after": {"a": "1"}, "env": {"X": "1"},
                     "llm_calls_before": 0, "llm_calls_after": 0}
    runs["control/graph"] = {**runs["control/graph"], "executed_in_this_invocation": False}
    man3 = {"kind": "e1_retrieval_run_manifest", "schema": 2, "invocation": {"argv": "--resume"},
            "llm": {"calls": 0}, "cache": {"sha256_before": "a", "sha256_after": "a",
                                           "unique_keys_before": 1, "unique_keys_after": 1},
            "runs": runs}
    mv3 = R.validate_manifest(man3, ctx)
    check("T3 luot dung lai -> run:control/graph UNVERIFIED (khong muon llm.calls=0 cua invocation moi)",
          mv3["run:control/graph"][0] == R.UNVERIFIED, mv3["run:control/graph"])
    check("T3 luot dung lai -> khong co index/rawlog/llm PASS cho luot do",
          not any(k.endswith("control/graph") and v[0] == R.PASS
                  for k, v in mv3.items() if not k.startswith("run:")), sorted(mv3))
    check("T3 luot dung lai -> config:graph UNVERIFIED (so sanh can env cua ca hai nhanh trong invocation)",
          mv3["config:graph"][0] == R.UNVERIFIED, mv3["config:graph"])
    check("T3 luot chay that van PASS", mv3["run:treatment/graph"][0] == R.PASS)
    check("T3 boolean khong duoc tin: index truoc != sau -> FAIL du khong co truong 'unchanged'",
          R.validate_manifest({**man3, "runs": {**runs, "treatment/rrf": {
              **runs["treatment/rrf"], "index_sha256_after": {"a": "2"}}}}, ctx)
          ["index:treatment/rrf"][0] == R.FAIL)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

tmp = tempfile.mkdtemp()
try:
    ctx = make_env(tmp)
    p = os.path.join(ctx.eval_dir, "control_graph.jsonl")
    reused = R.make_run_record(False, p, 180, env={"X": "1"}, llm_before=0, llm_after=0,
                               index_before={"a": "1"}, index_after={"a": "1"})
    check("T3 make_run_record(dung lai) KHONG chua env/index/llm du nguoi goi truyen vao",
          not any(k in reused for k in ("env", "index_sha256_before", "index_sha256_after",
                                         "llm_calls_before", "llm_calls_after")), sorted(reused))
    ran = R.make_run_record(True, p, 180, "t0", "t1", {"a": "1"}, {"a": "1"}, {"X": "1"}, 0, 0)
    man4 = {"kind": "e1_retrieval_run_manifest", "schema": 2, "invocation": {"argv": "--resume"},
            "llm": {"calls": 0}, "cache": {"sha256_before": "a", "sha256_after": "a",
                                           "unique_keys_before": 1, "unique_keys_after": 1},
            "runs": {r: (reused if r == "control/graph" else ran) for r in R.RUNS}}
    mv4 = R.validate_manifest(man4, ctx)
    check("T3 manifest dung make_run_record: luot dung lai -> UNVERIFIED",
          mv4["run:control/graph"][0] == R.UNVERIFIED, mv4["run:control/graph"])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

tmp = tempfile.mkdtemp()
try:
    so = "tien kiem PASS\n  bo qua control/graph: da co 180 ban ghi (--resume)\n" + \
         "".join(f"  chay {r} -> x\n" for r in R.RUNS if r != "control/graph")
    ctx = make_env(tmp, stdout_text=so)
    R.preserve_runner_evidence(ctx)
    data, _ = R.load_raw_logs(ctx)
    rv = R.verify_runner_reports(ctx, data)
    check("T3 stdout cho thay luot dung lai -> report runner KHONG PASS", rv["status"] != R.PASS, rv["reasons"])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ================================================================== T2 report khong ro nguon
tmp = tempfile.mkdtemp()
try:
    ctx = make_env(tmp)
    # thay report song bang report kieu report_e1 TRUOC khi bao toan
    fake = {"mode": "graph", "overall_status": "VALID", "audit_notes": [], "gate": {}, "checks": []}
    json.dump(fake, open(os.path.join(ctx.log_dir, "eval_graph_report.json"), "w"))
    pres = R.preserve_runner_evidence(ctx)
    check("T2 report kieu report_e1 khong duoc dua vao kho bang chung",
          "eval_graph_report.json" not in pres["newly_preserved"], pres)
    check("T2 file phu (md/jsonl) khong duoc luu khi hai report chua xac nhan",
          not any(n in pres["newly_preserved"] for n in R.RUNNER_FILES_OTHER), pres["newly_preserved"])
    data, probs = R.load_raw_logs(ctx)
    rv = R.verify_runner_reports(ctx, data)
    check("T2 -> nguon report UNVERIFIED", rv["status"] == R.UNVERIFIED, rv["reasons"])
    checks = R.gather_checks(ctx, data, probs, rv, None, R.filesystem_evidence(ctx), (R.UNVERIFIED, "x", None))
    llm = [c for c in checks if c.name.startswith("khong co loi goi LLM")]
    check("T2 -> check LLM la UNVERIFIED, khong ke thua PASS", llm and llm[0].status == R.UNVERIFIED,
          [(c.status, c.detail) for c in llm])
    gate, overall = R.decide_gates({"x": 1}, checks)
    check("T2 -> cong NOT_EVALUATED", gate["status"] == "NOT_EVALUATED" and gate["rrf"]["passed"] is None)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

tmp = tempfile.mkdtemp()
try:
    ctx = make_env(tmp)
    # report dung cau truc runner nhung ghi TRUOC raw log cuoi -> ngoai khung thoi gian
    for mode in R.MODES:
        p = os.path.join(ctx.log_dir, f"eval_{mode}_report.json")
        old = os.path.getmtime(p) - 3600
        os.utime(p, (old, old))
    R.preserve_runner_evidence(ctx)
    data, _ = R.load_raw_logs(ctx)
    rv = R.verify_runner_reports(ctx, data)
    check("T2 report dung cau truc nhung sai khung thoi gian -> KHONG PASS", rv["status"] != R.PASS, rv["reasons"])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

tmp = tempfile.mkdtemp()
try:
    ctx = make_env(tmp)
    rp = os.path.join(ctx.log_dir, "eval_rrf_report.json")
    obj = json.load(open(rp))
    obj["final_chunks"]["ALL"]["wins"] += 3                      # so lieu khong khop raw log
    mt = os.path.getmtime(rp)
    json.dump(obj, open(rp, "w"))
    os.utime(rp, (mt, mt))
    R.preserve_runner_evidence(ctx)
    data, _ = R.load_raw_logs(ctx)
    rv = R.verify_runner_reports(ctx, data)
    check("T2 report co so lieu khong tinh lai duoc tu raw log -> FAIL", rv["status"] == R.FAIL, rv["reasons"])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ================================================================== T4 du 180 dong nhung sai question ID
tmp = tempfile.mkdtemp()
try:
    ctx = make_env(tmp, wrong_ids=True)
    try:
        code = R.build_and_write(ctx)
        crashed = None
    except Exception as e:                                      # noqa: BLE001
        code, crashed = None, repr(e)
    check("T4 khong crash", crashed is None, crashed)
    check("T4 exit code != 0", code not in (0, None), code)
    audit_p = os.path.join(ctx.log_dir, "validity_audit.json")
    check("T4 van ghi validity_audit.json", os.path.exists(audit_p))
    if os.path.exists(audit_p):
        a = json.load(open(audit_p, encoding="utf-8"))
        check("T4 overall = INVALID", a["overall_status"] == "INVALID", a["overall_status"])
        check("T4 cong NOT_EVALUATED, passed = null",
              a["gate"]["status"] == "NOT_EVALUATED" and a["gate"]["graph_only"]["passed"] is None)
        wrong = [c for c in a["checks"] if "dung va du bo cau hoi" in c["name"]]
        check("T4 check bo cau hoi FAIL o ca bon luot", len(wrong) == 4 and all(c["status"] == "FAIL" for c in wrong),
              [c["status"] for c in wrong])
    check("T4 KHONG tinh/ghi per_query khi chua hop le",
          not os.path.exists(os.path.join(ctx.log_dir, "per_query_graph.jsonl.new")) and
          open(os.path.join(ctx.log_dir, "per_query_graph.jsonl")).read() == "runner output\n")
    check("T4 KHONG ghi de eval_graph_report.json bang ket qua",
          "overall_status" not in json.load(open(os.path.join(ctx.log_dir, "eval_graph_report.json"))))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ================================================================== T5 report-only hai lan van giu bang chung goc
tmp = tempfile.mkdtemp()
try:
    ctx = make_env(tmp)
    R.build_and_write(ctx)
    reg1 = json.load(open(os.path.join(ctx.archive, "PRESERVED.json")))["files"]
    data, _ = R.load_raw_logs(ctx)
    rv1 = R.verify_runner_reports(ctx, data)
    check("T5 lan 1: bang chung runner duoc luu va xac minh PASS", rv1["status"] == R.PASS, rv1["reasons"])
    # mo phong report-only da ghi de file o vi tri song bang report cua chinh no
    for mode in R.MODES:
        json.dump({"mode": mode, "overall_status": "VALID", "audit_notes": [], "gate": {},
                   "check_summary": {}}, open(os.path.join(ctx.log_dir, f"eval_{mode}_report.json"), "w"))
    open(os.path.join(ctx.log_dir, "eval_summary.md"), "w").write("report_e1 output\n")
    R.build_and_write(ctx)
    reg2 = json.load(open(os.path.join(ctx.archive, "PRESERVED.json")))["files"]
    check("T5 lan 2: kho luu tru khong doi (cung file, cung sha256)",
          {k: v["sha256"] for k, v in reg1.items()} == {k: v["sha256"] for k, v in reg2.items()})
    check("T5 lan 2: ban luu eval_graph_report.json van la report cua runner",
          R.runner_v1_fingerprint(json.load(open(os.path.join(ctx.archive, "eval_graph_report.json"))))[0])
    rv2 = R.verify_runner_reports(ctx, data)
    check("T5 lan 2: van xac minh duoc bang chung goc (khong phu thuoc report vua sinh)",
          rv2["status"] == R.PASS, rv2["reasons"])
    # sua kho luu tru -> phai bi phat hien
    with open(os.path.join(ctx.archive, "eval_rrf_report.json"), "a") as f:
        f.write(" ")
    rv3 = R.verify_runner_reports(ctx, data)
    check("T5 kho luu tru bi sua sau khi bao toan -> FAIL", rv3["status"] == R.FAIL, rv3["reasons"])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
print("KET QUA:", "TAT CA PASS" if not fails else f"{len(fails)} FAIL: {fails}")
sys.exit(1 if fails else 0)
