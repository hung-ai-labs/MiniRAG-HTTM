"""E1 offline retrieval evaluation -- ghep cap CONTROL vs TREATMENT, khong sinh, khong cham.

Hai nhanh DUY NHAT duoc dung cho ket qua chinh (da dong bang, xem
logs/entity_resolution/reembed_pair_report.json):

    CONTROL   logs/entity_resolution/pair/control     (chua gop)
    TREATMENT logs/entity_resolution/pair/entres      (da gop E1)

Ca hai da duoc chuan hoa vdb_relationships bang cung hf_embed + batch = 1 theo Amendment
17/09/2026 trong preregistration.md. KHONG dung truc tiep LiHua-World-qwen-modal /
LiHua-World-qwen-entres cho ket qua chinh.

Hoan toan offline:
  - parser lay tu cache rieng logs/entity_resolution/cache/kw_cache.jsonl,
    MINIRAG_KW_CACHE_ONLY=1 o CA HAI nhanh -> thieu cache la loi, khong goi LLM;
  - llm_model_func la stub cam: bat ky duong nao goi LLM se raise RuntimeError;
  - only_need_context=True -> tra context roi dung, khong sinh;
  - khong judge.

    .venv/Scripts/python.exe reproduce/entity_resolution/eval_offline.py
    .venv/Scripts/python.exe reproduce/entity_resolution/eval_offline.py --limit 3   # chay thu
"""

import argparse
import asyncio
import hashlib
import json
import os
import statistics as st
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "reproduce", "screening"))

from eval_set import evidence_rows  # noqa: E402
from merge_entities import build_local_embedding_func, file_sha256, read_graph  # noqa: E402
# Chi lay ham thong ke da kiem chung. TUYET DOI khong dung contexts()/run_query()/set_env()
# cua screening: set_env() ep MINIRAG_KW_CACHE ve logs/screening/ (screen_variant.py:99-108).
from screen_variant import mcnemar_p  # noqa: E402

PAIR = os.path.join(ROOT, "logs", "entity_resolution", "pair")
ARMS = {"control": os.path.join(PAIR, "control"), "treatment": os.path.join(PAIR, "entres")}
MODES = {"graph": "", "rrf": "rrf"}          # ten mode -> gia tri MINIRAG_CHUNK_FUSION
LOG_DIR = os.path.join(ROOT, "logs", "entity_resolution")
EVAL_DIR = os.path.join(LOG_DIR, "eval")
KW_CACHE = os.path.join(LOG_DIR, "cache", "kw_cache.jsonl")
REEMBED_REPORT = os.path.join(LOG_DIR, "reembed_pair_report.json")

# Giong het BASE_ENV cua sang loc (screen_variant.py:26) de giong thiet lap da dang ky.
BASE_ENV = {"MINIRAG_ANSWER_TYPE_FIX": "1", "MINIRAG_PATH2CHUNK_FIX": "0", "MINIRAG_CHUNK_CUT": ""}
UNSET_ENV = ("MINIRAG_TRUNCATE_SOURCES", "MINIRAG_MAX_TOKEN_TEXT_UNIT")
CTX_KEYS = ("chunk_ids", "graph_ids", "ranked_ids", "vector_ids", "fusion",
            "graph_seeds", "graph_paths", "retrieval_ms", "n_chunks", "context_sha256")

# Cong da dang ky truoc -- KHONG doi sau khi thay ket qua.
GATE = {"graph": "full-evidence net >= +9 VA p < 0,01", "rrf": "full-evidence net >= 0"}

LLM_CALLS = []
_EMBED = []


def shared_embedding_func():
    """Nap all-MiniLM-L6-v2 dung mot lan roi dung lai cho ca bon luot chay -- cung mot doi
    tuong ham nghia la ca hai nhanh chac chan dung y het mot embedding."""
    if not _EMBED:
        _EMBED.append(build_local_embedding_func())
    return _EMBED[0]


async def forbidden_llm(*args, **kwargs):
    """Stub cam: E1 offline khong duoc goi LLM o bat ky duong nao."""
    LLM_CALLS.append(args[:1])
    raise RuntimeError("EXPERIMENT INVALID: co duong code goi LLM trong danh gia offline E1")


def build_rag_offline(workingdir):
    """MiniRAG tro vao mot nhanh. Cau hinh GIONG HET nhau giua hai nhanh tru working_dir.

    enable_llm_cache=False de _query_done() khong ghi kv_store_llm_response_cache.json vao thu
    muc nhanh da dong bang (minirag.py:596-602). Khong anh huong truy hoi: cache do chi phuc vu
    loi goi LLM, ma o day LLM bi cam.
    """
    from minirag import MiniRAG

    return MiniRAG(
        working_dir=workingdir,
        llm_model_func=forbidden_llm,
        llm_model_max_token_size=200,
        llm_model_name="FORBIDDEN-OFFLINE-STUB",
        llm_model_max_async=8,
        embedding_func_max_async=4,
        embedding_func=shared_embedding_func(),
        enable_llm_cache=False,
    )


def set_experiment_env(mode, ctx_log):
    os.environ.update(BASE_ENV)
    os.environ["MINIRAG_CHUNK_FUSION"] = MODES[mode]
    os.environ["MINIRAG_CONTEXT_LOG"] = ctx_log
    os.environ["MINIRAG_KW_CACHE"] = KW_CACHE
    os.environ["MINIRAG_KW_CACHE_ONLY"] = "1"        # ca hai nhanh: cache da du 200/200
    for k in UNSET_ENV:
        os.environ.pop(k, None)


def env_fingerprint():
    keys = sorted(set(BASE_ENV) | {"MINIRAG_CHUNK_FUSION", "MINIRAG_KW_CACHE",
                                    "MINIRAG_KW_CACHE_ONLY"} | set(UNSET_ENV))
    return {k: os.environ.get(k) for k in keys}


def index_hashes(workingdir):
    return {f: file_sha256(os.path.join(workingdir, f))
            for f in sorted(os.listdir(workingdir))
            if f.endswith(".json") or f.endswith(".graphml")}


def load_done(out_path, rows, limit):
    """Tra ve list ban ghi neu file da co du va dung bo cau hoi; nguoc lai None."""
    if not os.path.exists(out_path):
        return None
    recs = [json.loads(ln) for ln in open(out_path, encoding="utf-8") if ln.strip()]
    want = [r["Question"] for r in (rows[:limit] if limit else rows)]
    return recs if [r.get("question") for r in recs] == want else None


async def run_arm(arm, mode, rows, out_path, limit=0):
    """Chay mot nhanh o mot mode, ghi <arm>_<mode>.jsonl. Tra ve list ban ghi."""
    from minirag import QueryParam

    workingdir = ARMS[arm]
    before = index_hashes(workingdir)
    rag = build_rag_offline(workingdir)
    tmp_log = os.path.join(EVAL_DIR, f"_ctx_{arm}_{mode}_{os.getpid()}.jsonl")
    records = []
    use = rows[:limit] if limit else rows
    t0 = time.perf_counter()
    for n, r in enumerate(use, 1):
        q = r["Question"]
        if os.path.exists(tmp_log):
            os.remove(tmp_log)
        set_experiment_env(mode, tmp_log)
        out = await rag.aquery(q, QueryParam(mode="mini", only_need_context=True))
        lines = [ln for ln in open(tmp_log, encoding="utf-8") if ln.strip()] \
            if os.path.exists(tmp_log) else []
        rec = json.loads(lines[-1]) if lines else None
        if rec is None:
            # _build_mini_query_context tra None (khong ra node hoac khong ra canh) -> khong co
            # dong log. Ghi nhan la truy hoi rong, tinh la FAIL o chi so full-evidence.
            row = {"question": q, "type": r["Type"], "none": True, "graph_ids": [],
                   "chunk_ids": [], "ranked_ids": [], "vector_ids": [], "fusion": MODES[mode],
                   "graph_seeds": None, "graph_paths": None, "retrieval_ms": None,
                   "n_chunks": 0, "context_sha256": "NONE",
                   "context_none": out is None}
        else:
            row = {"question": q, "type": r["Type"], "none": False,
                   **{k: rec.get(k) for k in CTX_KEYS}}
        records.append(row)
        if n % 30 == 0 or n == len(use):
            print(f"    [{arm}/{mode}] {n}/{len(use)} ({time.perf_counter() - t0:.0f}s)", flush=True)
    if os.path.exists(tmp_log):
        os.remove(tmp_log)
    with open(out_path, "w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    after = index_hashes(workingdir)
    return records, before == after


# ------------------------------------------------------------------ chi so
def full_evidence(row, gold, field):
    """Full-evidence: TOAN BO chunk dap an phai nam trong danh sach, khong phai trung mot phan."""
    ids = set(row.get(field) or [])
    return all(g in ids for g in gold[row["question"]])


def paired(control, treatment, gold, field, subset=None):
    cmap = {r["question"]: r for r in control}
    tmap = {r["question"]: r for r in treatment}
    qs = [q for q in cmap if q in tmap]
    if subset:
        qs = [q for q in qs if cmap[q]["type"] == subset]
    wins = losses = tie_pass = tie_fail = 0
    for q in qs:
        c = full_evidence(cmap[q], gold, field)
        t = full_evidence(tmap[q], gold, field)
        if t and not c:
            wins += 1
        elif c and not t:
            losses += 1
        elif c and t:
            tie_pass += 1
        else:
            tie_fail += 1
    n = len(qs)
    c_pass = tie_pass + losses
    t_pass = tie_pass + wins
    return {
        "n": n,
        "control_pass": c_pass, "control_rate": 100 * c_pass / n if n else None,
        "treatment_pass": t_pass, "treatment_rate": 100 * t_pass / n if n else None,
        "wins": wins, "losses": losses, "tie_pass": tie_pass, "tie_fail": tie_fail,
        "net": wins - losses, "mcnemar_p": mcnemar_p(wins, losses),
    }


def workload(records):
    out = {}
    for key in ("graph_seeds", "graph_paths", "retrieval_ms"):
        vals = [r[key] for r in records if r.get(key) is not None]
        if not vals:
            out[key] = None
            continue
        s = sorted(vals)
        out[key] = {"n": len(s), "mean": round(st.mean(s), 2), "median": round(st.median(s), 2),
                    "p95": round(s[min(len(s) - 1, int(0.95 * len(s)))], 2), "max": round(max(s), 2)}
    return out


# ------------------------------------------------------------------ sanity
def sanity_checks(data, rows, gold, cfg, hashes_ok, cache_before, cache_after):
    from minirag import QueryParam

    checks = []

    def add(name, ok, detail=""):
        checks.append({"name": name, "passed": bool(ok), "detail": str(detail)})

    expected_qs = [r["Question"] for r in rows]
    for mode in MODES:
        for arm in ARMS:
            recs = data[(arm, mode)]
            add(f"{arm}/{mode}: dung 180 ban ghi", len(recs) == 180, len(recs))
            add(f"{arm}/{mode}: khong trung cau hoi",
                len({r['question'] for r in recs}) == len(recs))
            add(f"{arm}/{mode}: dung bo cau hoi cua tap do",
                [r["question"] for r in recs] == expected_qs)
            add(f"{arm}/{mode}: schema context log hop le",
                all(all(k in r for k in ("graph_ids", "chunk_ids", "graph_seeds",
                                          "graph_paths", "retrieval_ms")) for r in recs))
            fus = {r.get("fusion") for r in recs}
            add(f"{arm}/{mode}: fusion dung {MODES[mode]!r}, khong lan mode khac",
                fus == {MODES[mode]}, fus)
            if mode == "graph":
                bad = [r["question"] for r in recs
                       if not r["none"] and r.get("ranked_ids") != r.get("graph_ids")]
                add(f"{arm}/graph: ranked_ids == graph_ids (khong co tron RRF)", not bad, len(bad))

    add("tap do: 180 = 159 Single + 21 Multi + 0 Null",
        len(rows) == 180
        and sum(1 for r in rows if r["Type"] == "Single") == 159
        and sum(1 for r in rows if r["Type"] == "Multi") == 21
        and sum(1 for r in rows if r["Type"] == "Null") == 0)
    add("gold map phu du 180 cau", all(r["Question"] in gold for r in rows))
    add("khong co loi goi LLM nao", not LLM_CALLS, len(LLM_CALLS))
    add("cache parser khong bi ghi them (KW_CACHE_ONLY=1)", cache_before == cache_after,
        f"{cache_before} -> {cache_after}")
    add("cau hinh hai nhanh giong nhau tru working_dir",
        cfg["control"] == cfg["treatment"], "")
    add("max_token_for_text_unit = 4000", QueryParam().max_token_for_text_unit == 4000,
        QueryParam().max_token_for_text_unit)
    add("cat Sources dung thiet lap da dang ky (TRUNCATE_SOURCES bat, khong de-doi ngan sach)",
        os.environ.get("MINIRAG_TRUNCATE_SOURCES", "1") != "0"
        and not os.environ.get("MINIRAG_MAX_TOKEN_TEXT_UNIT", "").strip())
    add("top_k = 60 (graph top-30 = top_k/2)", QueryParam().top_k == 60, QueryParam().top_k)
    for arm, ok in hashes_ok.items():
        add(f"{arm}: file index khong doi sau khi chay", ok)
    return checks


def fmt_block(res):
    return (f"  control  {res['control_pass']}/{res['n']} = {res['control_rate']:.2f}%\n"
            f"  treatment {res['treatment_pass']}/{res['n']} = {res['treatment_rate']:.2f}%\n"
            f"  wins {res['wins']} / losses {res['losses']} / tie-pass {res['tie_pass']} / "
            f"tie-fail {res['tie_fail']}\n"
            f"  net {res['net']:+d}, McNemar exact p = {res['mcnemar_p']:.6g}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="chay thu N cau (0 = full 180)")
    ap.add_argument("--resume", action="store_true",
                    help="dung lai ket qua da co neu file du 180 ban ghi dung bo cau hoi")
    args = ap.parse_args()

    # ---- tien kiem ----
    rep = json.load(open(REEMBED_REPORT, encoding="utf-8"))
    if rep["status"] != "PASS":
        raise SystemExit(f"reembed_pair_report.status = {rep['status']} -- khong duoc chay")
    rows, gold = evidence_rows(strict=True)
    graphs = {arm: read_graph(d) for arm, d in ARMS.items()}
    pools = {arm: sorted({d["entity_type"].lower() for _, d in g.nodes(data=True)
                           if "entity_type" in d}) for arm, g in graphs.items()}
    if pools["control"] != pools["treatment"]:
        raise SystemExit("TYPE_POOL hai nhanh khac nhau -- ghep cap parser mat hieu luc")
    cache_keys = {json.loads(ln)["prompt_sha256"]
                  for ln in open(KW_CACHE, encoding="utf-8") if ln.strip()}
    from minirag.prompt import PROMPTS
    tmpl = PROMPTS["minirag_query2kwd"]
    for arm in ARMS:
        miss = [r["Question"] for r in rows
                if hashlib.sha256(tmpl.format(query=r["Question"],
                                               TYPE_POOL=pools[arm]).encode("utf-8")).hexdigest()
                not in cache_keys]
        if miss:
            raise SystemExit(f"{arm}: thieu {len(miss)} cau trong cache parser -- dung")
    print(f"tien kiem PASS: reembed {rep['status']}, tap do {len(rows)} cau, "
          f"TYPE_POOL giong nhau ({len(pools['control'])} gia tri), cache du 180/180 ca hai nhanh")

    os.makedirs(EVAL_DIR, exist_ok=True)
    cache_before = len(cache_keys)

    # ---- chay: moi mode, control truoc roi treatment ----
    data, hashes_ok, cfg = {}, {}, {}
    for mode in MODES:
        for arm in ("control", "treatment"):
            out_path = os.path.join(EVAL_DIR, f"{arm}_{mode}.jsonl")
            done = load_done(out_path, rows, args.limit) if args.resume else None
            if done is not None:
                print(f"  bo qua {arm}/{mode}: da co {len(done)} ban ghi (--resume)", flush=True)
                recs, unchanged = done, True
            else:
                print(f"  chay {arm}/{mode} -> {os.path.basename(out_path)}", flush=True)
                recs, unchanged = asyncio.run(run_arm(arm, mode, rows, out_path, args.limit))
            data[(arm, mode)] = recs
            hashes_ok[arm] = hashes_ok.get(arm, True) and unchanged
            cfg[arm] = {"env": env_fingerprint(), "mode_value": MODES[mode]}
            cfg[arm]["env"].pop("MINIRAG_CHUNK_FUSION", None)  # khac nhau theo mode, khong theo nhanh
    cache_after = len({json.loads(ln)["prompt_sha256"]
                       for ln in open(KW_CACHE, encoding="utf-8") if ln.strip()})

    checks = sanity_checks(data, rows if not args.limit else rows[:args.limit],
                           gold, cfg, hashes_ok, cache_before, cache_after) \
        if not args.limit else []
    valid = all(c["passed"] for c in checks) if checks else None

    # ---- chi so ----
    results = {}
    for mode in MODES:
        c, t = data[("control", mode)], data[("treatment", mode)]
        results[mode] = {
            "graph_top30": {"ALL": paired(c, t, gold, "graph_ids"),
                             "Single": paired(c, t, gold, "graph_ids", "Single"),
                             "Multi": paired(c, t, gold, "graph_ids", "Multi")},
            "final_chunks": {"ALL": paired(c, t, gold, "chunk_ids"),
                              "Single": paired(c, t, gold, "chunk_ids", "Single"),
                              "Multi": paired(c, t, gold, "chunk_ids", "Multi")},
            "workload": {"control": workload(c), "treatment": workload(t)},
        }

    if args.limit:
        print(json.dumps(results, ensure_ascii=False, indent=1)[:2000])
        return 0

    # ---- cong da dang ky ----
    g = results["graph"]["graph_top30"]["ALL"]
    r = results["rrf"]["graph_top30"]["ALL"]
    gate = {
        "graph_only": {"rule": GATE["graph"], "net": g["net"], "p": g["mcnemar_p"],
                        "passed": g["net"] >= 9 and g["mcnemar_p"] < 0.01},
        "rrf": {"rule": GATE["rrf"], "net": r["net"], "passed": r["net"] >= 0},
    }

    for mode in MODES:
        payload = {"mode": mode, "fusion": MODES[mode],
                    "arms": {a: ARMS[a] for a in ARMS},
                    "valid": valid, "checks": checks, **results[mode]}
        with open(os.path.join(LOG_DIR, f"eval_{mode}_report.json"), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        with open(os.path.join(LOG_DIR, f"per_query_{mode}.jsonl"), "w", encoding="utf-8") as f:
            cmap = {x["question"]: x for x in data[("control", mode)]}
            for t_rec in data[("treatment", mode)]:
                q = t_rec["question"]
                c_rec = cmap[q]
                f.write(json.dumps({
                    "question": q, "type": t_rec["type"], "gold": gold[q],
                    "control_graph_full": full_evidence(c_rec, gold, "graph_ids"),
                    "treatment_graph_full": full_evidence(t_rec, gold, "graph_ids"),
                    "control_chunk_full": full_evidence(c_rec, gold, "chunk_ids"),
                    "treatment_chunk_full": full_evidence(t_rec, gold, "chunk_ids"),
                    "control_graph_ids": c_rec["graph_ids"], "treatment_graph_ids": t_rec["graph_ids"],
                    "control_chunk_ids": c_rec["chunk_ids"], "treatment_chunk_ids": t_rec["chunk_ids"],
                    "control_workload": {k: c_rec.get(k) for k in ("graph_seeds", "graph_paths", "retrieval_ms")},
                    "treatment_workload": {k: t_rec.get(k) for k in ("graph_seeds", "graph_paths", "retrieval_ms")},
                }, ensure_ascii=False) + "\n")

    lines = ["# E1 offline evaluation -- " + time.strftime("%Y-%m-%d %H:%M"), "",
             "Entity Resolution E1 under the deterministic relationship-embedding correction "
             "preregistered on 17/09/2026.", "",
             f"control   = {ARMS['control']}", f"treatment = {ARMS['treatment']}",
             f"tap do: {len(rows)} cau co evidence (159 Single + 21 Multi + 0 Null)",
             f"sanity: {'VALID' if valid else 'INVALID'} "
             f"({sum(1 for c in checks if c['passed'])}/{len(checks)} check)", ""]
    for mode in MODES:
        lines.append(f"## mode = {mode} (MINIRAG_CHUNK_FUSION={MODES[mode]!r})")
        for field, label in (("graph_top30", "full-evidence trong graph top-30"),
                              ("final_chunks", "full-evidence trong chunk_ids sau cat 4.000")):
            lines.append(f"### {label}")
            for subset in ("ALL", "Single", "Multi"):
                lines.append(f"- {subset}:")
                lines.append(fmt_block(results[mode][field][subset]))
            lines.append("")
        lines.append("### workload")
        for arm in ARMS:
            lines.append(f"- {arm}: " + json.dumps(results[mode]["workload"][arm], ensure_ascii=False))
        lines.append("")
    lines += ["## cong da dang ky truoc", json.dumps(gate, ensure_ascii=False, indent=1)]
    with open(os.path.join(LOG_DIR, "eval_summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print("\n".join(lines))
    fails = [c for c in checks if not c["passed"]]
    if fails:
        print("\nEXPERIMENT INVALID -- sanity check truot:")
        for c in fails:
            print("  FAIL", c["name"], c["detail"])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
