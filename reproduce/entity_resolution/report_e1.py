"""Lop phan tich / bao cao cho E1 -- TACH KHOI runner truy hoi. KHONG chay truy van.

    .venv/Scripts/python.exe reproduce/entity_resolution/report_e1.py

Thu tu bat buoc trong build_and_write():
  1. bao toan bang chung goc cua lan chay (report cua runner, stdout tien trinh) vao
     logs/entity_resolution/provenance/runner_original/ -- chi chep MOT lan, khong bao gio ghi de;
  2. thu thap check. Moi check co TRANG THAI BA MUC (PASS / FAIL / UNVERIFIED) va NGUON;
  3. FAIL-CLOSED: neu con check bat buoc nao khac PASS -> ghi bao cao chan doan, cong
     NOT_EVALUATED, passed = null, exit code != 0, va DUNG TRUOC khi tinh ket qua chinh;
  4. chi khi moi check bat buoc PASS moi tinh chi so, per-query va cong.

Nguyen tac bang chung:
  - Trang thai cua TIEN TRINH BAO CAO khong phai bang chung ve TIEN TRINH TRUY HOI.
  - Report chi duoc dung lam bang chung ve lan chay khi XAC MINH duoc nguon: dung cau truc cua
    runner, dung bo ten check runner phat ra, dung khung thoi gian, khop so lieu tinh lai tu raw
    log, khop stdout cua tien trinh. Report khong ro nguon -> khong dung.
  - Report-only luon doc bang chung tu ban luu tru goc, KHONG tu file o vi tri song (vi tri song
    se bi chinh report-only ghi de).
  - Khong tao hash/run_id hoi to roi goi la bang chung truoc run. Hash ghi luc bao toan chi dung
    de phat hien ban luu tru bi sua ve sau.
  - Manifest thieu truong bat buoc -> UNVERIFIED. Bang chung cua mot arm/mode khong dai dien cho
    ca bon. Luot duoc dung lai (--resume) khong mang provenance cua invocation moi.
"""

import hashlib
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

PASS, FAIL, UNVERIFIED = "PASS", "FAIL", "UNVERIFIED"
MODES = {"graph": "", "rrf": "rrf"}
ARM_NAMES = ("control", "treatment")
RUNS = [f"{a}/{m}" for m in MODES for a in ARM_NAMES]

RUNNER_FILES_JSON = ("eval_graph_report.json", "eval_rrf_report.json")
RUNNER_FILES_OTHER = ("eval_summary.md", "per_query_graph.jsonl", "per_query_rrf.jsonl")
RUNNER_V1_TOP_KEYS = {"mode", "fusion", "arms", "valid", "checks", "graph_top30", "final_chunks",
                      "workload"}
REPORT_E1_MARKERS = {"overall_status", "audit_notes", "check_summary", "gate", "timestamp"}
REPORT_WINDOW_S = 900          # runner ghi report ngay sau arm cuoi; cho phep toi da 15 phut


# =================================================================== kieu du lieu
@dataclass
class Check:
    name: str
    status: str
    detail: str = ""
    source: str = ""
    required: bool = True


@dataclass
class Ctx:
    root: str
    log_dir: str
    eval_dir: str
    prov_dir: str
    arms: dict
    cache_path: str
    source_cache_path: str
    process_output: Optional[str]
    freeze_report: str
    launch_source: Optional[str]
    current_runner: Optional[str]
    post_launch_patch: Optional[str]
    rows: list = field(default_factory=list)
    gold: dict = field(default_factory=dict)
    corpus: dict = field(default_factory=dict)        # chunk_id -> content
    type_pools: dict = field(default_factory=dict)
    dangling_ids: tuple = ()                          # chunk id do thi tham chieu nhung kho chunk khong co

    @property
    def archive(self):
        return os.path.join(self.prov_dir, "runner_original")


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def split_sep(blob):
    """Tach source_id theo GRAPH_FIELD_SEP ('<SEP>') giong minirag/utils.split_string_by_multi_markers."""
    return [x.strip() for x in str(blob or "").split("<SEP>") if x.strip()]


def ts(x):
    return None if x is None else time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(x))


# =================================================================== raw log
def load_raw_logs(ctx):
    data, problems = {}, []
    for run in RUNS:
        arm, mode = run.split("/")
        p = os.path.join(ctx.eval_dir, f"{arm}_{mode}.jsonl")
        if not os.path.exists(p):
            problems.append(f"thieu raw log {arm}_{mode}.jsonl")
            continue
        recs = []
        try:
            for i, ln in enumerate(open(p, encoding="utf-8"), 1):
                if not ln.strip():
                    continue
                try:
                    rec = json.loads(ln)
                except json.JSONDecodeError as e:
                    problems.append(f"{arm}_{mode}.jsonl dong {i}: JSON hong ({e})")
                    continue
                if not isinstance(rec, dict):
                    problems.append(f"{arm}_{mode}.jsonl dong {i}: khong phai object")
                    continue
                recs.append(rec)
        except OSError as e:
            problems.append(f"khong doc duoc {p}: {e}")
            continue
        data[(arm, mode)] = recs
    return data, problems


# =================================================================== dau van tay runner v1
def runner_v1_expected_names():
    names = []
    for mode in MODES:
        for arm in ARM_NAMES:
            names += [f"{arm}/{mode}: dung 180 ban ghi", f"{arm}/{mode}: khong trung cau hoi",
                      f"{arm}/{mode}: dung bo cau hoi cua tap do",
                      f"{arm}/{mode}: schema context log hop le",
                      f"{arm}/{mode}: fusion dung {MODES[mode]!r}, khong lan mode khac"]
            if mode == "graph":
                names.append(f"{arm}/graph: ranked_ids == graph_ids (khong co tron RRF)")
    names += ["tap do: 180 = 159 Single + 21 Multi + 0 Null", "gold map phu du 180 cau",
              "khong co loi goi LLM nao", "cache parser khong bi ghi them (KW_CACHE_ONLY=1)",
              "cau hinh hai nhanh giong nhau tru working_dir", "max_token_for_text_unit = 4000",
              "cat Sources dung thiet lap da dang ky (TRUNCATE_SOURCES bat, khong de-doi ngan sach)",
              "top_k = 60 (graph top-30 = top_k/2)"]
    names += [f"{arm}: file index khong doi sau khi chay" for arm in ARM_NAMES]
    return names


def runner_v1_fingerprint(obj):
    """(ok, ly_do). Chi dung cau truc runner v1 moi la UNG VIEN report cua runner."""
    if not isinstance(obj, dict):
        return False, "khong phai object JSON"
    if REPORT_E1_MARKERS & set(obj):
        return False, f"co dau hieu cua report_e1 ({sorted(REPORT_E1_MARKERS & set(obj))})"
    if set(obj) != RUNNER_V1_TOP_KEYS:
        return False, f"bo khoa khac runner v1: {sorted(set(obj) ^ RUNNER_V1_TOP_KEYS)}"
    checks = obj.get("checks")
    if not isinstance(checks, list) or not all(
            isinstance(c, dict) and set(c) == {"name", "passed", "detail"}
            and isinstance(c["passed"], bool) for c in checks):
        return False, "schema check khong phai {name, passed(bool), detail}"
    names = [c["name"] for c in checks]
    expected = runner_v1_expected_names()
    if sorted(names) != sorted(expected):
        return False, (f"bo ten check khac runner v1 (thieu {sorted(set(expected) - set(names))[:3]}, "
                       f"thua {sorted(set(names) - set(expected))[:3]})")
    return True, "khop cau truc va bo ten check cua runner v1"


# =================================================================== bao toan bang chung goc
def preserve_runner_evidence(ctx):
    """Chep bang chung goc vao kho luu tru MOT LAN. Khong bao gio ghi de ban da luu.

    Report JSON chi duoc luu neu dung dau van tay runner v1, nen report do chinh report_e1 sinh ra
    (co marker rieng) khong bao gio lot vao kho bang chung, du chay report-only bao nhieu lan.
    """
    os.makedirs(ctx.archive, exist_ok=True)
    reg_path = os.path.join(ctx.archive, "PRESERVED.json")
    reg = json.load(open(reg_path, encoding="utf-8")) if os.path.exists(reg_path) else {
        "_note": ("sha256/mtime/ctime ghi LUC BAO TOAN (sau khi lan chay ket thuc). Chung chi dung de "
                  "phat hien ban luu tru bi sua ve sau; KHONG phai hash truoc lan chay."),
        "files": {}}
    newly, skipped = [], []

    def keep(src, name):
        tgt = os.path.join(ctx.archive, name)
        if os.path.exists(tgt) or name in reg["files"]:
            skipped.append(f"{name}: da luu truoc do, giu nguyen")
            return
        st = os.stat(src)
        shutil.copyfile(src, tgt)
        reg["files"][name] = {"sha256": sha256_file(tgt), "size": st.st_size,
                               "original_path": src, "original_mtime": st.st_mtime,
                               "original_ctime": st.st_ctime, "preserved_at": time.time()}
        newly.append(name)

    fps = {}
    for name in RUNNER_FILES_JSON:
        live = os.path.join(ctx.log_dir, name)
        if not os.path.exists(live):
            continue
        try:
            ok, why = runner_v1_fingerprint(json.load(open(live, encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as e:
            ok, why = False, f"doc loi: {e}"
        fps[name] = (ok, why)
        if ok:
            keep(live, name)
        else:
            skipped.append(f"{name}: khong luu -- {why}")
    both_runner = all(fps.get(n, (False,))[0] for n in RUNNER_FILES_JSON)
    for name in RUNNER_FILES_OTHER:
        live = os.path.join(ctx.log_dir, name)
        if not os.path.exists(live):
            continue
        if both_runner:
            keep(live, name)
        else:
            skipped.append(f"{name}: khong luu -- hai report JSON cung luc chua xac nhan la cua runner")
    if ctx.process_output and os.path.exists(ctx.process_output):
        keep(ctx.process_output, "process_stdout.txt")
    # minirag.log: MiniRAG dau tien trong tien trinh gan file handler (minirag/utils.py:41), nen moi truy van
    # cua CA BON luot deu ghi vao pair/control/minirag.log. Chi luu khi hai report runner da xac nhan, tuc la
    # tien trinh da chay xong -- tranh luu ban dang do.
    mlog = os.path.join(ctx.arms["control"], "minirag.log")
    if both_runner and os.path.exists(mlog):
        keep(mlog, "minirag_log_control.txt")
    with open(reg_path, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)
    return {"newly_preserved": newly, "skipped": skipped}


# =================================================================== metric dung y runner v1
def _v1_full(row, gold_ids, fld):
    ids = set(row.get(fld) or [])
    return all(g in ids for g in gold_ids)


def _v1_paired(control, treatment, gold, fld, subset=None):
    cmap = {r.get("question"): r for r in control}
    tmap = {r.get("question"): r for r in treatment}
    qs = [q for q in cmap if q in tmap]
    if subset:
        qs = [q for q in qs if cmap[q].get("type") == subset]
    w = l = tp = tf = 0
    for q in qs:
        c, t = _v1_full(cmap[q], gold.get(q, []), fld), _v1_full(tmap[q], gold.get(q, []), fld)
        w += t and not c
        l += c and not t
        tp += c and t
        tf += (not c) and (not t)
    return {"n": len(qs), "control_pass": tp + l, "treatment_pass": tp + w,
            "wins": w, "losses": l, "tie_pass": tp, "tie_fail": tf}


# =================================================================== xac minh nguon report runner
def verify_runner_reports(ctx, data):
    """status PASS = xac minh duoc la report cua CHINH lan chay tao ra bon raw log hien co.
    FAIL = co bang chung mau thuan. UNVERIFIED = thieu bang chung."""
    out = {"status": UNVERIFIED, "reasons": [], "checks": {}, "stdout": None}
    reg_path = os.path.join(ctx.archive, "PRESERVED.json")
    if not os.path.exists(reg_path):
        out["reasons"].append("chua co kho bang chung goc (PRESERVED.json)")
        return out
    reg = json.load(open(reg_path, encoding="utf-8"))["files"]

    for name, meta in reg.items():
        p = os.path.join(ctx.archive, name)
        if not os.path.exists(p) or sha256_file(p) != meta["sha256"]:
            out["reasons"].append(f"ban luu {name} bi mat hoac bi sua sau khi bao toan")
            out["status"] = FAIL
            return out

    reports = {}
    for name in RUNNER_FILES_JSON:
        if name not in reg:
            out["reasons"].append(f"khong co {name} goc trong kho bang chung")
            return out
        obj = json.load(open(os.path.join(ctx.archive, name), encoding="utf-8"))
        ok, why = runner_v1_fingerprint(obj)
        if not ok:
            out["reasons"].append(f"{name}: {why}")
            return out
        reports[name] = obj

    a, b = (reports[n]["checks"] for n in RUNNER_FILES_JSON)
    if a != b:
        out["reasons"].append("hai report JSON co bo check khac nhau -- khong cung mot lan chay")
        return out

    raw_mtimes = []
    for run in RUNS:
        arm, mode = run.split("/")
        p = os.path.join(ctx.eval_dir, f"{arm}_{mode}.jsonl")
        if os.path.exists(p):
            raw_mtimes.append(os.path.getmtime(p))
    if len(raw_mtimes) != 4:
        out["reasons"].append("thieu raw log de doi chieu thoi gian")
        return out
    last_raw = max(raw_mtimes)
    for name in RUNNER_FILES_JSON:
        m = reg[name]["original_mtime"]
        if not (last_raw - 1 <= m <= last_raw + REPORT_WINDOW_S):
            out["reasons"].append(f"{name} ghi luc {ts(m)} ngoai khung [{ts(last_raw)}, +{REPORT_WINDOW_S}s]")
            return out

    for name in RUNNER_FILES_JSON:
        mode = reports[name].get("mode")
        if mode not in MODES or ("control", mode) not in data or ("treatment", mode) not in data:
            out["reasons"].append(f"{name}: mode {mode!r} khong co raw log de doi chieu")
            return out
        c, t = data[("control", mode)], data[("treatment", mode)]
        for metric, fld in (("graph_top30", "graph_ids"), ("final_chunks", "chunk_ids")):
            for subset in ("ALL", "Single", "Multi"):
                got = _v1_paired(c, t, ctx.gold, fld, None if subset == "ALL" else subset)
                rep = (reports[name].get(metric) or {}).get(subset) or {}
                diff = {k: (rep.get(k), v) for k, v in got.items() if rep.get(k) != v}
                if diff:
                    out["reasons"].append(f"{name} {metric}/{subset} khong khop raw log: {diff}")
                    out["status"] = FAIL
                    return out

    stdout = ""
    if "process_stdout.txt" in reg:
        stdout = open(os.path.join(ctx.archive, "process_stdout.txt"), encoding="utf-8", errors="replace").read()
    out["stdout"] = stdout
    for run in RUNS:
        if f"bo qua {run}" in stdout:
            out["reasons"].append(f"luot {run} duoc DUNG LAI -- khong mang provenance cua invocation nay")
            return out
    for bad in ("Traceback", "RuntimeError", "EXPERIMENT INVALID: co duong code goi LLM"):
        if bad in stdout:
            out["reasons"].append(f"stdout co '{bad}'")
            out["status"] = FAIL
            return out

    stdout_passes = bool(stdout) and all(f"chay {r} ->" in stdout for r in RUNS)
    if stdout_passes:
        out["passes"] = (PASS, "stdout goc cho thay ca bon luot duoc chay")
    else:
        out["passes"] = pass_evidence_from_minirag_log(ctx, reg, data)
    if out["passes"][0] != PASS:
        out["reasons"].append(f"khong xac minh duoc bon luot duoc chay: {out['passes'][1]}")
        out["status"] = out["passes"][0]
        return out

    out["status"] = PASS
    out["checks"] = {c["name"]: c for c in a}
    out["reasons"].append("report goc: dung dau van tay runner v1, cung bo check, dung khung thoi gian, so lieu "
                          "tinh lai khop raw log; " + out["passes"][1])
    return out


def pass_evidence_from_minirag_log(ctx, reg, data):
    """Bang chung GHI TRONG LAN CHAY rang ca bon luot deu thuc su chay, dung thu tu, trong mot tien trinh.

    NanoVectorDBStorage.query (minirag/kg/nano_vector_db_impl.py:140) ghi moi truy van; truy van kho chunk bang
    cau hoi goc dung top_k = 30 (operate.py:1465) va xay ra truoc moi nhanh fusion. Cua so cua luot i la
    (moc ket thuc luot i-1, mtime raw log luot i]; luot dau bat dau tu ctime file stdout do harness tao luc khoi
    chay. Moi cua so phai co DUNG chuoi cau hoi cua raw log luot do, dung thu tu. Log do Windows ghi bang cp1252.
    """
    import datetime as dt
    import re

    if "minirag_log_control.txt" not in reg:
        return UNVERIFIED, "khong co minirag.log trong kho bang chung"
    if "process_stdout.txt" not in reg:
        return UNVERIFIED, "khong co moc khoi chay (ctime file stdout)"
    start = dt.datetime.fromtimestamp(reg["process_stdout.txt"]["original_ctime"]).replace(microsecond=0)
    pat = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ - minirag - INFO - Query: (.*), top_k: 30, "
                     r"cosine_better_than_threshold")
    lines = []
    with open(os.path.join(ctx.archive, "minirag_log_control.txt"), encoding="cp1252", errors="strict") as f:
        for ln in f:
            m = pat.match(ln)
            if m:
                lines.append((dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"), m.group(2)))
    details = []
    prev = start
    for run in RUNS:
        arm, mode = run.split("/")
        p = os.path.join(ctx.eval_dir, f"{arm}_{mode}.jsonl")
        if not os.path.exists(p) or (arm, mode) not in data:
            return UNVERIFIED, f"thieu raw log {run}"
        end = dt.datetime.fromtimestamp(os.path.getmtime(p)).replace(microsecond=0)
        seen = [q for t, q in lines if prev <= t <= end]
        want = [r.get("question") for r in data[(arm, mode)] if not r.get("none")]
        if seen != want:
            return FAIL, (f"{run}: cua so [{prev:%H:%M:%S}, {end:%H:%M:%S}] co {len(seen)} truy van kho chunk, "
                          f"khong khop {len(want)} cau cua raw log theo thu tu")
        details.append(f"{run} {len(seen)} cau [{prev:%H:%M:%S}-{end:%H:%M:%S}]")
        prev = end
    return PASS, "minirag.log ghi trong lan chay: " + "; ".join(details)


# =================================================================== manifest (cho cac lan chay sau)
def make_run_record(executed, raw_log_path, records, started_at=None, finished_at=None,
                    index_before=None, index_after=None, env=None, llm_before=None, llm_after=None):
    """Ban ghi manifest cho MOT luot (arm, mode). Runner dung ham nay de ghi manifest schema 2.

    Luot DUNG LAI (executed=False) chi ghi so dong va sha256 raw log hien co -- TUYET DOI khong gan
    env / hash index / so loi goi LLM cua invocation hien tai cho no, vi invocation nay khong quan
    sat luot do. validate_manifest() se tra UNVERIFIED cho luot nhu vay.
    """
    rec = {"executed_in_this_invocation": bool(executed), "records": records,
           "raw_log_sha256": sha256_file(raw_log_path) if os.path.exists(raw_log_path) else None}
    if not executed:
        rec["note"] = "raw log co san duoc dung lai; invocation nay KHONG quan sat luot nay"
        return rec
    rec.update({"started_at": started_at, "finished_at": finished_at,
                "index_sha256_before": index_before, "index_sha256_after": index_after,
                "env": env, "llm_calls_before": llm_before, "llm_calls_after": llm_after})
    return rec


MANIFEST_REQUIRED = ("kind", "schema", "invocation", "llm", "cache", "runs")
# Thiet lap da dang ky (giong BASE_ENV cua sang loc). Khoa co gia tri None = phai KHONG duoc dat.
REGISTERED_ENV = {"MINIRAG_ANSWER_TYPE_FIX": "1", "MINIRAG_PATH2CHUNK_FIX": "0", "MINIRAG_CHUNK_CUT": "",
                  "MINIRAG_KW_CACHE_ONLY": "1", "MINIRAG_TRUNCATE_SOURCES": None,
                  "MINIRAG_MAX_TOKEN_TEXT_UNIT": None}
RUN_REQUIRED = ("executed_in_this_invocation", "started_at", "finished_at", "records",
                "raw_log_sha256", "index_sha256_before", "index_sha256_after", "env",
                "llm_calls_before", "llm_calls_after")


def validate_manifest(man, ctx):
    """{thuoc tinh: (status, detail)}. Khong tin boolean -- tu so du lieu nguon."""
    if not isinstance(man, dict):
        return {"manifest": (UNVERIFIED, "khong co manifest")}
    missing = [k for k in MANIFEST_REQUIRED if man.get(k) is None]
    if missing:
        return {"manifest": (UNVERIFIED, f"thieu truong bat buoc: {missing}")}
    if man.get("kind") != "e1_retrieval_run_manifest" or man.get("schema") != 2:
        return {"manifest": (UNVERIFIED, f"kind/schema khong ho tro: {man.get('kind')}/{man.get('schema')}")}
    res = {"manifest": (PASS, "du truong bat buoc")}

    llm = man["llm"] if isinstance(man["llm"], dict) else {}
    calls = llm.get("calls")
    res["llm"] = ((UNVERIFIED, "thieu llm.calls") if calls is None
                  else (PASS, "0 loi goi") if calls == 0 else (FAIL, f"{calls} loi goi LLM"))

    cache = man["cache"] if isinstance(man["cache"], dict) else {}
    b, a = cache.get("sha256_before"), cache.get("sha256_after")
    if b is None or a is None:
        res["cache_content"] = (UNVERIFIED, "thieu sha256_before hoac sha256_after -- khong so duoc noi dung")
    elif b != a:
        res["cache_content"] = (FAIL, "noi dung cache thay doi trong lan chay")
    else:
        res["cache_content"] = (PASS, "sha256 truoc == sau")
    kb, ka = cache.get("unique_keys_before"), cache.get("unique_keys_after")
    res["cache_key_count"] = ((UNVERIFIED, "thieu so key truoc hoac sau") if kb is None or ka is None
                              else (PASS, f"{kb} -> {ka}") if kb == ka else (FAIL, f"{kb} -> {ka}"))

    runs = man["runs"] if isinstance(man["runs"], dict) else {}
    for run in RUNS:
        r = runs.get(run)
        if not isinstance(r, dict):
            res[f"run:{run}"] = (UNVERIFIED, "manifest khong co ban ghi cho luot nay")
            continue
        miss = [k for k in RUN_REQUIRED if r.get(k) is None]
        if miss:
            res[f"run:{run}"] = (UNVERIFIED, f"thieu truong: {miss}")
            continue
        if r["executed_in_this_invocation"] is not True:
            res[f"run:{run}"] = (UNVERIFIED, "luot duoc dung lai tu invocation truoc -- invocation nay "
                                             "khong co bang chung ve no")
            continue
        res[f"run:{run}"] = (PASS, "luot duoc chay trong invocation nay")
        before, after = r["index_sha256_before"], r["index_sha256_after"]
        if not isinstance(before, dict) or not isinstance(after, dict) or not before:
            res[f"index:{run}"] = (UNVERIFIED, "hash index truoc/sau rong hoac sai kieu")
        else:
            changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
            res[f"index:{run}"] = (PASS, f"{len(before)} file khong doi") if not changed \
                else (FAIL, f"file doi: {changed}")
        arm, mode = run.split("/")
        p = os.path.join(ctx.eval_dir, f"{arm}_{mode}.jsonl")
        if not os.path.exists(p):
            res[f"rawlog:{run}"] = (FAIL, "raw log khong con")
        else:
            res[f"rawlog:{run}"] = (PASS, "sha256 raw log khop manifest") \
                if sha256_file(p) == r["raw_log_sha256"] else (FAIL, "raw log khac voi luc chay")
        res[f"llm:{run}"] = (PASS, "0 -> 0") if (r["llm_calls_before"] == 0 and r["llm_calls_after"] == 0) \
            else (FAIL, f"{r['llm_calls_before']} -> {r['llm_calls_after']}")
        env = r["env"] if isinstance(r["env"], dict) else {}
        want = {**REGISTERED_ENV, "MINIRAG_CHUNK_FUSION": MODES[mode]}
        miss_env = sorted(k for k in want if k not in env)
        bad_env = {k: (env.get(k), v) for k, v in want.items() if k in env and env.get(k) != v}
        res[f"registered_env:{run}"] = (
            (UNVERIFIED, f"env thieu khoa: {miss_env}") if miss_env
            else (FAIL, f"lech thiet lap da dang ky: {bad_env}") if bad_env
            else (PASS, "env dung thiet lap da dang ky"))
    for mode in MODES:
        rc, rt = runs.get(f"control/{mode}"), runs.get(f"treatment/{mode}")
        if not (isinstance(rc, dict) and isinstance(rt, dict)
                and rc.get("executed_in_this_invocation") is True
                and rt.get("executed_in_this_invocation") is True
                and isinstance(rc.get("env"), dict) and isinstance(rt.get("env"), dict)):
            res[f"config:{mode}"] = (UNVERIFIED, "thieu env duoc ghi trong invocation nay cho mot trong hai nhanh")
        else:
            res[f"config:{mode}"] = (PASS, "env giong nhau") if rc["env"] == rt["env"] \
                else (FAIL, "env hai nhanh khac nhau")
    return res


# =================================================================== bang chung tu du lieu nguon
def _encoder():
    import tiktoken
    return tiktoken.encoding_for_model("gpt-4o")


def recompute_truncation(recs, corpus, budget=4000, enc=None):
    """A1: chunk_ids phai la tien to dai nhat cua ranked_ids co tong token <= budget
    (utils.truncate_list_by_token_size, goi o operate.py:1541-1548). Tra ve danh sach cau lech."""
    enc = enc or _encoder()
    cache, bad = {}, []
    for r in recs:
        ranked = [c for c in (r.get("ranked_ids") or []) if c in corpus]
        tot, keep = 0, []
        for cid in ranked:
            if cid not in cache:
                cache[cid] = len(enc.encode(corpus[cid]))
            tot += cache[cid]
            if tot > budget:
                break
            keep.append(cid)
        if keep != (r.get("chunk_ids") or []):
            bad.append(r.get("question"))
    return bad


def filesystem_evidence(ctx):
    ev = {"freeze_anchor": None, "launch_anchor": None, "arm_index_mtimes": {}, "cache": {}}
    if os.path.exists(ctx.freeze_report):
        ev["freeze_anchor"] = os.path.getmtime(ctx.freeze_report)
    reg_path = os.path.join(ctx.archive, "PRESERVED.json")
    if os.path.exists(reg_path):
        meta = json.load(open(reg_path, encoding="utf-8"))["files"].get("process_stdout.txt")
        if meta:
            ev["launch_anchor"] = meta["original_ctime"]   # file do harness tao luc khoi chay tien trinh
    for arm, d in ctx.arms.items():
        if os.path.isdir(d):
            ev["arm_index_mtimes"][arm] = {f: os.path.getmtime(os.path.join(d, f))
                                           for f in sorted(os.listdir(d))
                                           if f.endswith((".json", ".graphml"))}
    if os.path.exists(ctx.cache_path):
        st = os.stat(ctx.cache_path)
        ev["cache"] = {"mtime": st.st_mtime, "sha256": sha256_file(ctx.cache_path),
                       "source_sha256": sha256_file(ctx.source_cache_path)
                       if os.path.exists(ctx.source_cache_path) else None}
    return ev


def verify_launch_source(ctx):
    """Ma runner luc khoi chay DUNG LAI bang cach dao patch sau launch. Xac minh: ap lai patch len ban
    dung lai phai ra DUNG runner hien tai. Bang chung ho tro -- khong phai snapshot truoc run."""
    paths = (ctx.launch_source, ctx.current_runner, ctx.post_launch_patch)
    if not all(paths) or not all(os.path.exists(p) for p in paths):
        return UNVERIFIED, "thieu ban dung lai / runner hien tai / patch sau launch", None
    import ast
    src = open(ctx.post_launch_patch, encoding="utf-8").read()
    pairs = [(ast.literal_eval(n.value.args[0]), ast.literal_eval(n.value.args[1]))
             for n in ast.parse(src).body
             if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
             and getattr(n.value.func, "id", None) == "rep"]
    launch = open(ctx.launch_source, encoding="utf-8").read()
    cur = open(ctx.current_runner, encoding="utf-8").read()
    s = launch
    for old, new in pairs:
        if s.count(old) != 1:
            return UNVERIFIED, "ban dung lai khong ap lai patch duoc mot cach duy nhat", launch
        s = s.replace(old, new, 1)
    if s != cur:
        return UNVERIFIED, ("ap lai patch sau launch len ban dung lai KHONG ra runner hien tai "
                            "(runner da bi sua them?)"), launch
    return PASS, f"patch(ban_dung_lai) == runner hien tai ({len(pairs)} phep thay the)", launch


# =================================================================== tap hop check
def gather_checks(ctx, data, problems, runner, manifest, fs, launch):
    import collections
    from collections import Counter

    checks = []

    def add(name, status, detail="", source="", required=True):
        checks.append(Check(name, status, str(detail), source, required))

    for p in problems:
        add(f"nap du lieu: {p}", FAIL, p, "nap du lieu")

    expected = [r["Question"] for r in ctx.rows]
    typ = {r["Question"]: r["Type"] for r in ctx.rows}

    # ---------------- 1. hinh dang raw log
    for run in RUNS:
        arm, mode = run.split("/")
        recs = data.get((arm, mode))
        if recs is None:
            add(f"{run}: co raw log", FAIL, "thieu", "raw_log")
            continue
        add(f"{run}: dung 180 ban ghi", PASS if len(recs) == 180 else FAIL, len(recs), "raw_log")
        qs = [r.get("question") for r in recs]
        add(f"{run}: khong trung cau hoi", PASS if len(set(qs)) == len(qs) else FAIL,
            f"{len(qs)} dong / {len(set(qs))} cau", "raw_log")
        add(f"{run}: dung va du bo cau hoi cua tap do", PASS if qs == expected else FAIL,
            "khop" if qs == expected else
            f"thieu {len(set(expected) - set(qs))}, la {len(set(qs) - set(expected))}", "raw_log")
        need = ("question", "type", "graph_ids", "chunk_ids", "ranked_ids", "vector_ids", "fusion",
                "graph_seeds", "graph_paths", "retrieval_ms")
        bad = sum(1 for r in recs if any(k not in r for k in need))
        add(f"{run}: schema log du truong", PASS if not bad else FAIL, f"{bad} ban ghi thieu", "raw_log")
        wrong_t = sum(1 for r in recs if typ.get(r.get("question")) not in (None, r.get("type")))
        add(f"{run}: type moi cau khop tap do", PASS if not wrong_t else FAIL, wrong_t, "raw_log")
        leak = sum(1 for r in recs if "gold" in r)
        add(f"{run}: raw log khong chua nhan gold", PASS if not leak else FAIL, leak, "raw_log")
        fus = {r.get("fusion") for r in recs}
        add(f"{run}: fusion dung {MODES[mode]!r}, khong tron mode", PASS if fus == {MODES[mode]} else FAIL,
            sorted(map(str, fus)), "raw_log")
        over = sum(1 for r in recs if len(r.get("graph_ids") or []) > 30)
        add(f"{run}: graph_ids <= 30 (kwd2chunk chunk_nums = top_k/2)", PASS if not over else FAIL,
            f"{over} vuot", "raw_log")
        if mode == "graph":
            mism = sum(1 for r in recs if not r.get("none") and r.get("ranked_ids") != r.get("graph_ids"))
            add(f"{run}: ranked_ids == graph_ids (khong tron o mode graph)", PASS if not mism else FAIL,
                f"{mism} lech", "raw_log")
        # Bat bien THAT: context cuoi va xep hang vector chi duoc chua chunk co trong kho.
        unk = {c for r in recs for c in (r.get("chunk_ids") or []) + (r.get("vector_ids") or [])
               if c not in ctx.corpus}
        add(f"{run}: moi chunk id trong chunk_ids/vector_ids thuoc corpus", PASS if not unk else FAIL,
            f"{len(unk)} id la", "raw_log + kv_store_text_chunks.json")
        # graph_ids KHONG co bat bien do: kwd2chunk xep hang chunk lay tu source_id cua node, ma do thi
        # Qwen da commit co tham chieu toi chunk khong con trong kv_store_text_chunks. Chunk nhu vay bi
        # loai o operate.py:1518 truoc khi vao chunk_ids. Ghi nhan de bao cao, khong chan cong.
        stale = collections.Counter(c for r in recs for c in (r.get("graph_ids") or [])
                                    if c not in ctx.corpus)
        add(f"{run}: graph_ids tham chieu chunk khong con trong kho (dac tinh co san cua do thi)",
            PASS, f"{sum(stale.values())} lan, {len(stale)} id: {sorted(stale)[:2]}",
            "raw_log + kv_store_text_chunks.json", required=False)
        # Khang dinh bat buoc di kem: tap id "treo" do PHAI nam tron trong tap treo THUA KE tu
        # source_id cua chinh do thi nhanh. Neu xuat hien id la ngoai tap do thi la dau hieu log bi
        # tron tu nguon khac -- phai chan cong.
        extra = sorted(set(stale) - set(ctx.dangling_ids))
        add(f"{run}: khong co id la ngoai tap chunk treo thua ke tu do thi",
            PASS if not extra else FAIL,
            f"treo thua ke {len(ctx.dangling_ids)} id; ngoai danh sach: {extra}",
            "raw_log + source_id cua do thi nhanh + kv_store_text_chunks.json")

    complete = all(len(data.get(tuple(r.split("/")), [])) == 180 for r in RUNS)

    # ---------------- 2. cap tham so, TINH TU DU LIEU NGUON cho tung luot
    for mode in MODES:
        c, t = data.get(("control", mode)), data.get(("treatment", mode))
        if not c or not t:
            add(f"{mode}: vector_ids giong het giua hai nhanh", UNVERIFIED, "thieu raw log", "raw_log")
            continue
        vt = {r.get("question"): r.get("vector_ids") for r in t}
        diff = sum(1 for r in c if r.get("vector_ids") != vt.get(r.get("question")))
        add(f"{mode}: vector_ids giong het giua hai nhanh (cung embedding, top_k, kho chunk)",
            PASS if not diff else FAIL, f"{diff} cau lech", "raw_log")
    for arm in ARM_NAMES:
        g, r_ = data.get((arm, "graph")), data.get((arm, "rrf"))
        if not g or not r_:
            add(f"{arm}: graph_ids va vector_ids bat bien giua hai mode", UNVERIFIED, "thieu raw log", "raw_log")
            continue
        rm = {x.get("question"): x for x in r_}
        dg = sum(1 for x in g if x.get("graph_ids") != rm.get(x.get("question"), {}).get("graph_ids"))
        dv = sum(1 for x in g if x.get("vector_ids") != rm.get(x.get("question"), {}).get("vector_ids"))
        add(f"{arm}: graph_ids va vector_ids bat bien giua hai mode (chi fusion khac; operate.py:1489)",
            PASS if dg == 0 and dv == 0 else FAIL, f"graph_ids lech {dg}, vector_ids lech {dv}", "raw_log")
    if complete and ctx.corpus:
        enc = _encoder()
        for run in RUNS:
            arm, mode = run.split("/")
            bad = recompute_truncation(data[(arm, mode)], ctx.corpus, 4000, enc)
            add(f"{run}: chunk_ids = tien to dai nhat cua ranked_ids co <= 4000 token (A1@4000)",
                PASS if not bad else FAIL, f"{len(bad)} cau lech", "tinh lai tu raw log + tiktoken gpt-4o")
    else:
        add("ngan sach 4000 tinh lai tu raw log", UNVERIFIED, "raw log hoac corpus chua day du", "raw_log")

    # ---------------- 3. tap do, gold
    bt = Counter(r["Type"] for r in ctx.rows)
    ok = len(ctx.rows) == 180 and bt.get("Single") == 159 and bt.get("Multi") == 21 and bt.get("Null", 0) == 0
    add("tap do = 180 (159 Single + 21 Multi + 0 Null)", PASS if ok else FAIL, dict(bt), "eval_set.py")
    empty = sum(1 for r in ctx.rows if not ctx.gold.get(r["Question"]))
    add("moi cau co gold_chunk_ids khong rong", PASS if ctx.rows and not empty else FAIL,
        f"{empty} rong", "diag_path2chunk.jsonl")
    outside = {g for r in ctx.rows for g in ctx.gold.get(r["Question"], []) if g not in ctx.corpus}
    add("moi gold chunk thuoc corpus", PASS if ctx.corpus and not outside else FAIL,
        f"{len(outside)} id la", "kv_store_text_chunks.json")
    tpc, tpt = ctx.type_pools.get("control"), ctx.type_pools.get("treatment")
    add("TYPE_POOL control == treatment", PASS if tpc and tpc == tpt else FAIL,
        f"{len(tpc or [])} gia tri", "graphml hai nhanh (hien tai)")

    # ---------------- 4. provenance CHINH lan chay
    if isinstance(manifest, dict):
        for key, (st, det) in sorted(validate_manifest(manifest, ctx).items()):
            add(f"manifest {key}", st, det, "run_manifest.json")
    else:
        rs, rc = runner["status"], runner["checks"]
        why = "; ".join(runner["reasons"])
        add("nguon report cua runner duoc xac minh", rs, why, "provenance/runner_original")

        def from_runner(label, check_name, extra_ok=True, extra_detail=""):
            if rs != PASS:
                add(label, FAIL if rs == FAIL else UNVERIFIED,
                    f"khong dung duoc report runner: {why}", "provenance/runner_original")
                return
            c = rc.get(check_name)
            if c is None:
                add(label, UNVERIFIED, f"report runner khong co check '{check_name}'", "provenance/runner_original")
            elif not c["passed"]:
                add(label, FAIL, f"runner bao truot: {c['detail']}", "provenance/runner_original")
            elif not extra_ok:
                add(label, UNVERIFIED, f"runner bao dat nhung bang chung bo tro khong khop: {extra_detail}",
                    "provenance/runner_original + filesystem")
            else:
                add(label, PASS, f"runner: {c['detail']}" + (f"; {extra_detail}" if extra_detail else ""),
                    "provenance/runner_original" + (" + filesystem" if extra_detail else ""))

        pst, pdet = runner.get("passes", (UNVERIFIED, why))
        add("ca bon luot duoc CHAY trong cung mot tien trinh, dung thu tu (khong luot nao dung lai)",
            pst if rs != FAIL else FAIL, pdet,
            "provenance/runner_original (stdout hoac minirag.log ghi trong lan chay)")

        from_runner("khong co loi goi LLM trong lan chay truy hoi (ca bon luot)", "khong co loi goi LLM nao")

        cache, la = fs.get("cache") or {}, fs.get("launch_anchor")
        cache_ok = bool(cache and la and cache["mtime"] <= la and cache.get("source_sha256")
                        and cache["source_sha256"] == cache["sha256"])
        cache_det = (f"cache mtime {ts(cache.get('mtime'))} <= khoi chay {ts(la)}; noi dung == nguon screening"
                     if cache_ok else f"cache mtime {ts(cache.get('mtime'))}, khoi chay {ts(la)}, "
                                      f"noi dung khop nguon={cache.get('source_sha256') == cache.get('sha256')}")
        from_runner("cache parser: so key khong doi (runner) va file khong bi ghi trong lan chay (filesystem)",
                    "cache parser khong bi ghi them (KW_CACHE_ONLY=1)", cache_ok, cache_det)

        fa = fs.get("freeze_anchor")
        for arm in ARM_NAMES:
            mt = fs["arm_index_mtimes"].get(arm, {})
            late = sorted(f for f, m in mt.items() if fa is None or m > fa)
            fs_ok = bool(mt) and fa is not None and not late
            det = (f"moi file index mtime <= moc dong bang {ts(fa)}" if fs_ok
                   else f"file moi hon moc dong bang: {late[:4]}")
            from_runner(f"{arm}: index khong doi trong ca hai luot (hash truoc/sau cua runner AND 2 mode)",
                        f"{arm}: file index khong doi sau khi chay", fs_ok, det)

        launch_st, launch_det, launch_txt = launch
        add("ma runner luc khoi chay duoc dung lai va xac minh", launch_st, launch_det,
            "provenance/eval_offline_AT_LAUNCH_reconstructed.py")
        if launch_st == PASS and launch_txt:
            need = {
                "stub LLM cam duoc noi vao MiniRAG": "llm_model_func=forbidden_llm",
                "cache parser chi-doc cho moi luot": 'os.environ["MINIRAG_KW_CACHE_ONLY"] = "1"',
                "BASE_ENV dat lai truoc moi truy van": "os.environ.update(BASE_ENV)",
                "BASE_ENV dung thiet lap da dang ky": 'BASE_ENV = {"MINIRAG_ANSWER_TYPE_FIX": "1", '
                                                      '"MINIRAG_PATH2CHUNK_FIX": "0", "MINIRAG_CHUNK_CUT": ""}',
                "bo TRUNCATE_SOURCES / MAX_TOKEN_TEXT_UNIT": 'UNSET_ENV = ("MINIRAG_TRUNCATE_SOURCES", '
                                                             '"MINIRAG_MAX_TOKEN_TEXT_UNIT")',
                "only_need_context=True": "only_need_context=True",
                "khong ghi llm cache vao nhanh": "enable_llm_cache=False",
            }
            for label, snippet in need.items():
                add(f"ma luc khoi chay: {label}", PASS if snippet in launch_txt else FAIL, snippet,
                    "ban dung lai da xac minh")
        else:
            add("ma luc khoi chay: cau hinh LLM/cache/BASE_ENV", UNVERIFIED,
                "khong xac minh duoc ma runner luc khoi chay", "thieu")
        c = rc.get("cau hinh hai nhanh giong nhau tru working_dir") if rs == PASS else None
        add("runner: cau hinh hai nhanh giong nhau (CHI phu mode rrf vi cfg bi ghi de -- bo tro)",
            PASS if (c and c["passed"]) else UNVERIFIED, (c or {}).get("detail", "khong co"),
            "provenance/runner_original", required=False)

    add("hien tai: hai nhanh ton tai", PASS if all(os.path.isdir(d) for d in ctx.arms.values()) else FAIL,
        list(ctx.arms.values()), "trang thai hien tai (khong phai bang chung ve lan chay)", required=False)
    return checks


# =================================================================== ket qua (chi goi khi VALID)
def full_evidence(row, gold_ids, fld):
    """gold_chunk_ids PHAI la tap con. Trung mot phan khong tinh; gold rong khong tinh."""
    ids = set(row.get(fld) or [])
    return bool(gold_ids) and all(g in ids for g in gold_ids)


def paired(control, treatment, gold, fld, subset=None):
    cmap = {r["question"]: r for r in control}
    tmap = {r["question"]: r for r in treatment}
    qs = [q for q in cmap if q in tmap]
    if subset:
        qs = [q for q in qs if cmap[q].get("type") == subset]
    w = l = tp = tf = 0
    outcomes = {}
    for q in qs:
        c, t = full_evidence(cmap[q], gold[q], fld), full_evidence(tmap[q], gold[q], fld)
        outcomes[q] = (c, t)
        if t and not c:
            w += 1
        elif c and not t:
            l += 1
        elif c and t:
            tp += 1
        else:
            tf += 1
    n = len(qs)
    cp = sum(1 for c, _ in outcomes.values() if c)
    tpp = sum(1 for _, t in outcomes.values() if t)
    assert w + l + tp + tf == n and cp == tp + l and tpp == tp + w, "paired counts khong nhat quan"
    from screen_variant import mcnemar_p
    return {"n": n, "control_pass": cp, "control_rate": 100 * cp / n if n else None,
            "treatment_pass": tpp, "treatment_rate": 100 * tpp / n if n else None,
            "wins": w, "losses": l, "tie_pass": tp, "tie_fail": tf, "net": w - l,
            "mcnemar_p": mcnemar_p(w, l),
            "mcnemar_method": "exact two-sided binomial tren cap lech: min(1, 2*P(X<=min(b,c))), X~Bin(b+c,0.5)"}


def workload(records):
    import statistics as st
    out = {}
    for key in ("graph_seeds", "graph_paths", "retrieval_ms"):
        vals = sorted(r[key] for r in records if r.get(key) is not None)
        out[key] = None if not vals else {
            "n": len(vals), "mean": round(st.mean(vals), 2), "median": round(st.median(vals), 2),
            "p95": round(vals[min(len(vals) - 1, int(0.95 * len(vals)))], 2), "max": round(vals[-1], 2)}
    return out


def compute_results(data, gold):
    res = {}
    for mode in MODES:
        c, t = data[("control", mode)], data[("treatment", mode)]
        res[mode] = {m: {s: paired(c, t, gold, f, None if s == "ALL" else s) for s in ("ALL", "Single", "Multi")}
                     for m, f in (("graph_top30", "graph_ids"), ("final_chunks", "chunk_ids"))}
        res[mode]["workload"] = {"control": workload(c), "treatment": workload(t)}
    return res


GATE_SPEC = {
    "graph_only": {"metric_path": ("graph", "graph_top30", "ALL"),
                    "rule": "full-evidence net >= +9 VA McNemar exact p < 0,01"},
    "rrf": {"metric_path": ("rrf", "final_chunks", "ALL"), "rule": "full-evidence net >= 0"},
}


def overall_status(checks):
    req = [c for c in checks if c.required]
    if any(c.status == FAIL for c in req):
        return "INVALID"
    if any(c.status == UNVERIFIED for c in req):
        return "UNVERIFIED"
    return "VALID"


def not_evaluated_gate(checks):
    gate = {"status": "NOT_EVALUATED",
            "blocking_checks": [f"{c.status}: {c.name}" for c in checks if c.required and c.status != PASS]}
    for key, spec in GATE_SPEC.items():
        mode, metric, subset = spec["metric_path"]
        gate[key] = {"metric": f"mode={mode} -> {metric} ({subset})", "rule": spec["rule"],
                     "net": None, "mcnemar_p": None, "passed": None}
    return gate


def decide_gates(results, checks):
    """Chi tinh cong khi moi check bat buoc PASS; nguoc lai NOT_EVALUATED, passed = None."""
    overall = overall_status(checks)
    if overall != "VALID" or results is None:
        return not_evaluated_gate(checks), overall
    gate = {"status": "EVALUATED", "blocking_checks": []}
    for key, spec in GATE_SPEC.items():
        mode, metric, subset = spec["metric_path"]
        m = results[mode][metric][subset]
        passed = (m["net"] >= 9 and m["mcnemar_p"] < 0.01) if key == "graph_only" else (m["net"] >= 0)
        gate[key] = {"metric": f"mode={mode} -> {metric} ({subset})", "rule": spec["rule"],
                     "net": m["net"], "mcnemar_p": m["mcnemar_p"], "passed": bool(passed)}
    return gate, overall


# =================================================================== driver
AUDIT_NOTES = [
    "3-query engineering smoke test was observed before the full run; no merge decision, metric definition "
    "or numerical threshold was changed based on it. Its n=3 pass counts for mode=graph were printed to the "
    "operator.",
    "The RRF gate was corrected at the ANALYSIS layer from graph_top30 to final_chunks because graph_ids is "
    "captured before chunk fusion (minirag/operate.py:1489). The correction was applied to eval_offline.py at "
    "2026-09-17 22:52:08 (file mtime), after the full run was launched at 22:43:00 (process output file "
    "ctime) and before the first full-run raw log existed (control_graph.jsonl ctime 23:25:45). It is NOT a "
    "preregistration made before measurement. Preregistered thresholds (+9 / p<0.01; >=0) are unchanged.",
    "The running retrieval process keeps the launch-time code in memory, so it still writes reports with the "
    "uncorrected RRF gate. Those reports are preserved under provenance/runner_original/ as run evidence and "
    "are superseded by this report for gate conclusions.",
    "Report-layer changes (fail-closed gating, provenance verification) do not change the merge list, the "
    "retrieval implementation, the sample, the metric definitions or the numerical thresholds.",
    "Control arm is NOT the byte-identical committed retrieval index: both arms had their relationship VDB "
    "re-embedded with hf_embed at batch=1 per the 17/09/2026 amendment.",
    "Headline result: effect of E1 entity resolution under the deterministic relationship-embedding correction.",
]


def default_ctx():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))
    log_dir = os.path.join(root, "logs", "entity_resolution")
    prov = os.path.join(log_dir, "provenance")
    return Ctx(
        root=root, log_dir=log_dir, eval_dir=os.path.join(log_dir, "eval"), prov_dir=prov,
        arms={"control": os.path.join(log_dir, "pair", "control"),
              "treatment": os.path.join(log_dir, "pair", "entres")},
        cache_path=os.path.join(log_dir, "cache", "kw_cache.jsonl"),
        source_cache_path=os.path.join(root, "logs", "screening", "cache", "kw_cache.jsonl"),
        process_output=os.environ.get("E1_PROCESS_OUTPUT", "").strip() or None,
        freeze_report=os.path.join(log_dir, "reembed_pair_report.json"),
        launch_source=os.path.join(prov, "eval_offline_AT_LAUNCH_reconstructed.py"),
        current_runner=os.path.join(prov, "eval_offline_AFTER_GATE_PATCH_2252.py"),
        post_launch_patch=os.path.join(prov, "patch_gate_applied_2252.py"),
    )


def load_context_data(ctx):
    """Nap tap do, gold, corpus, TYPE_POOL. Loi -> problems (FAIL check) thay vi crash truoc audit."""
    problems = []
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (here, ctx.root, os.path.join(ctx.root, "reproduce", "screening")):
        if p not in sys.path:
            sys.path.insert(0, p)
    if not ctx.rows:
        try:
            from eval_set import evidence_rows
            ctx.rows, ctx.gold = evidence_rows(strict=True)
        except (SystemExit, Exception) as e:           # noqa: BLE001
            problems.append(f"khong nap duoc tap do: {e}")
    if not ctx.corpus:
        try:
            ctx.corpus = {k: v["content"] for k, v in json.load(open(
                os.path.join(ctx.arms["control"], "kv_store_text_chunks.json"), encoding="utf-8")).items()}
        except Exception as e:                          # noqa: BLE001
            problems.append(f"khong nap duoc corpus: {e}")
    if not ctx.type_pools:
        try:
            import networkx as nx
            dangling = set()
            for arm, d in ctx.arms.items():
                g = nx.read_graphml(os.path.join(d, "graph_chunk_entity_relation.graphml"))
                ctx.type_pools[arm] = sorted({x["entity_type"].lower() for _, x in g.nodes(data=True)
                                              if "entity_type" in x})
                # chunk id do do thi tham chieu qua source_id nhung kho chunk khong con: tap "treo"
                for _, x in g.nodes(data=True):
                    dangling |= set(split_sep(x.get("source_id")))
                for _, _, x in g.edges(data=True):
                    dangling |= set(split_sep(x.get("source_id")))
            ctx.dangling_ids = tuple(sorted(dangling - set(ctx.corpus))) if ctx.corpus else ()
        except Exception as e:                          # noqa: BLE001
            problems.append(f"khong nap duoc TYPE_POOL: {e}")
    return problems


def write_audit(ctx, checks, overall, gate, preserve, extra):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    req = [c for c in checks if c.required]
    summ = {"required": len(req), "pass": sum(c.status == PASS for c in req),
            "fail": sum(c.status == FAIL for c in req), "unverified": sum(c.status == UNVERIFIED for c in req)}
    audit = {"timestamp": stamp, "overall_status": overall, "check_summary": summ, "gate": gate,
             "checks": [asdict(c) for c in checks], "preservation": preserve,
             "audit_notes": AUDIT_NOTES, **extra}
    with open(os.path.join(ctx.log_dir, "validity_audit.json"), "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)
    L = [f"# E1 -- validity audit ({stamp})", "",
         f"Trang thai: **{overall}** -- check bat buoc {summ['pass']} PASS / {summ['fail']} FAIL / "
         f"{summ['unverified']} UNVERIFIED", "", f"Cong: **{gate['status']}**", ""]
    if overall != "VALID":
        L += ["Fail-closed: con check bat buoc chua PASS -> KHONG tinh ket qua chinh, KHONG ket luan cong.", "",
              "| trang thai | check | chi tiet | nguon |", "|---|---|---|---|"]
        L += [f"| {c.status} | {c.name} | {c.detail} | {c.source} |" for c in req if c.status != PASS]
        L.append("")
    L += ["## Moi check", "", "| trang thai | bat buoc | check | chi tiet | nguon |", "|---|---|---|---|---|"]
    L += [f"| {c.status} | {'x' if c.required else ''} | {c.name} | {c.detail} | {c.source} |" for c in checks]
    L += ["", "## Audit notes", ""] + [f"- {n}" for n in AUDIT_NOTES]
    with open(os.path.join(ctx.log_dir, "validity_audit.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    return audit


def build_and_write(ctx=None):
    ctx = ctx or default_ctx()
    os.makedirs(ctx.log_dir, exist_ok=True)

    preserve = preserve_runner_evidence(ctx)                       # 1. bao toan truoc tien

    problems = load_context_data(ctx)                              # 2. check, CHUA tinh ket qua
    data, raw_problems = load_raw_logs(ctx)
    problems += raw_problems
    runner = verify_runner_reports(ctx, data) if ctx.gold else {
        "status": UNVERIFIED, "reasons": ["khong co gold de doi chieu"], "checks": {}, "stdout": None}
    mpath = os.path.join(ctx.eval_dir, "run_manifest.json")
    manifest = None
    if os.path.exists(mpath):
        try:
            manifest = json.load(open(mpath, encoding="utf-8"))
        except json.JSONDecodeError:
            problems.append("run_manifest.json hong JSON")
    fs = filesystem_evidence(ctx)
    launch = verify_launch_source(ctx)
    checks = gather_checks(ctx, data, problems, runner, manifest, fs, launch)

    overall = overall_status(checks)                               # 3. fail-closed
    extra = {"runner_evidence": {"status": runner["status"], "reasons": runner["reasons"]},
             "manifest_present": manifest is not None,
             "anchors": {"freeze": ts(fs.get("freeze_anchor")), "launch": ts(fs.get("launch_anchor"))}}
    if overall != "VALID":
        gate = not_evaluated_gate(checks)
        write_audit(ctx, checks, overall, gate, preserve, extra)
        print(f"overall = {overall}; cong = NOT_EVALUATED")
        for c in checks:
            if c.required and c.status != PASS:
                print(f"  {c.status:10s} {c.name} | {c.detail} | nguon: {c.source}")
        return 2

    results = compute_results(data, ctx.gold)                      # 4. chi toi day moi tinh
    gate, overall = decide_gates(results, checks)
    audit = write_audit(ctx, checks, overall, gate, preserve, extra)
    for mode in MODES:
        payload = {"mode": mode, "fusion": MODES[mode], "arms": ctx.arms, "timestamp": audit["timestamp"],
                   "overall_status": overall, "gate": gate, "audit_notes": AUDIT_NOTES,
                   "check_summary": audit["check_summary"], **results[mode]}
        with open(os.path.join(ctx.log_dir, f"eval_{mode}_report.json"), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        cmap = {x["question"]: x for x in data[("control", mode)]}
        with open(os.path.join(ctx.log_dir, f"per_query_{mode}.jsonl"), "w", encoding="utf-8") as f:
            for t in data[("treatment", mode)]:
                q, c = t["question"], cmap[t["question"]]
                f.write(json.dumps({
                    "question": q, "type": t["type"], "gold": ctx.gold[q],
                    "control_graph_full": full_evidence(c, ctx.gold[q], "graph_ids"),
                    "treatment_graph_full": full_evidence(t, ctx.gold[q], "graph_ids"),
                    "control_chunk_full": full_evidence(c, ctx.gold[q], "chunk_ids"),
                    "treatment_chunk_full": full_evidence(t, ctx.gold[q], "chunk_ids"),
                    "control_graph_ids": c["graph_ids"], "treatment_graph_ids": t["graph_ids"],
                    "control_chunk_ids": c["chunk_ids"], "treatment_chunk_ids": t["chunk_ids"],
                    "control_workload": {k: c.get(k) for k in ("graph_seeds", "graph_paths", "retrieval_ms")},
                    "treatment_workload": {k: t.get(k) for k in ("graph_seeds", "graph_paths", "retrieval_ms")},
                }, ensure_ascii=False) + "\n")
    write_summary(ctx, results, gate, overall, audit)
    print(f"overall = {overall}; cong = {gate['status']}")
    return 0


def write_summary(ctx, results, gate, overall, audit):
    L = [f"# E1 offline evaluation -- {audit['timestamp']}", "",
         "**Effect of E1 entity resolution under the deterministic relationship-embedding correction.** "
         "Control is NOT the byte-identical committed retrieval index.", "",
         f"- control   : `{ctx.arms['control']}`", f"- treatment : `{ctx.arms['treatment']}`",
         "- tap do    : 180 cau co evidence (159 Single + 21 Multi + 0 Null)",
         f"- validity  : **{overall}** ({audit['check_summary']['pass']}/{audit['check_summary']['required']} "
         "check bat buoc PASS -- xem validity_audit.md)", ""]
    for mode in MODES:
        L.append(f"## mode = {mode} (MINIRAG_CHUNK_FUSION={MODES[mode]!r})")
        for metric, label in (("graph_top30", "full-evidence trong graph_ids (<=30, truoc fusion)"),
                              ("final_chunks", "full-evidence trong chunk_ids (sau fusion + A1@4000)")):
            L += [f"### {label}", "",
                  "| tap | n | control | treatment | wins | losses | tie-pass | tie-fail | net | McNemar p |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
            for s in ("ALL", "Single", "Multi"):
                m = results[mode][metric][s]
                L.append(f"| {s} | {m['n']} | {m['control_pass']} ({m['control_rate']:.1f}%) | "
                         f"{m['treatment_pass']} ({m['treatment_rate']:.1f}%) | {m['wins']} | {m['losses']} | "
                         f"{m['tie_pass']} | {m['tie_fail']} | {m['net']:+d} | {m['mcnemar_p']:.4g} |")
            L.append("")
        L += ["### workload", "", "| arm | chi so | mean | median | p95 | max |", "|---|---|---:|---:|---:|---:|"]
        for arm in ARM_NAMES:
            for k, v in results[mode]["workload"][arm].items():
                if v:
                    L.append(f"| {arm} | {k} | {v['mean']} | {v['median']} | {v['p95']} | {v['max']} |")
        L.append("")
    L += ["## Cong da dang ky (nguong khong doi; cong RRF doc final_chunks)", "", "```json",
          json.dumps(gate, ensure_ascii=False, indent=1), "```", "", "## Audit notes", ""] + \
         [f"- {n}" for n in AUDIT_NOTES]
    with open(os.path.join(ctx.log_dir, "eval_summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    sys.exit(build_and_write())
