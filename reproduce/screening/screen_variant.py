"""Sàng lọc biến thể truy hồi theo tầng A–C (ROADMAP: sửa đổi đăng ký trước BM25, 14/09/2026).

    reproduce/screening/run_screen.sh --variant b1 --stage offline   # tầng A (CPU; điền cache parser nếu thiếu)
    reproduce/screening/run_screen.sh --variant v3 --stage canary    # đông lạnh V3 canary — một lần
    reproduce/screening/run_screen.sh --variant b1 --stage canary    # tầng B, lô tuần tự 40 / 40 / 20
    reproduce/screening/run_screen.sh --variant v3 --stage dev       # mở rộng V3 đông lạnh cho dev 200 — một lần
    reproduce/screening/run_screen.sh --variant b1 --stage dev       # tầng C (chỉ khi canary PROMOTE)

- Chỉ nhận câu trong logs/devset.csv (assert). KHÔNG có tầng D: 435 câu ngoài dev cần lệnh riêng, duyệt riêng.
- Chế độ sàng lọc tất định: parser cache theo sha256 prompt, lời gọi sinh gửi seed 20260914.
- Câu có danh sách chunk, sha256 context và sha256 prompt giống hệt V3 đông lạnh → dùng lại câu trả lời + phán quyết
  V3; chỉ câu đổi context mới được sinh và chấm (1 lượt). Sinh xong phải khớp hash context đã tính, lệch → dừng.
- Báo cáo: logs/screening/<biến thể>/<tầng>_report.{txt,json}; câu trả lời: logs/screening/<biến thể>/answers.jsonl.
"""
import argparse, asyncio, csv, hashlib, json, math, os, statistics as st, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "reproduce"))
sys.path.insert(0, ROOT)

SEED = 20260914
D = 0.209                      # tỉ lệ đổi kết quả giữa hai lượt cùng cấu hình (tập lặp V3 cố định)
T_NONDEV = 4.18                # ngưỡng bền với nhiễu sinh trên 435 câu — chỉ để báo, tầng D không chạy ở đây
VARIANTS = {"v3": "rrf", "vec": "vector", "b1": "rrf_bm25", "b2": "vector_bm25"}
BASE_ENV = {"MINIRAG_ANSWER_TYPE_FIX": "1", "MINIRAG_PATH2CHUNK_FIX": "0", "MINIRAG_CHUNK_CUT": ""}
PREDICTION = {"b1": "câu đủ đáp án 72,8% · chunk giữ 75,8% (probe dev)", "b2": "câu đủ đáp án 83,9% · chunk giữ 86,0% (probe dev)"}
OUT = os.path.join(ROOT, "logs", "screening")
KW_CACHE = os.path.join(OUT, "cache", "kw_cache.jsonl")
FROZEN = os.path.join(OUT, "frozen", "v3.jsonl")
DEV_W = {"Single": 159 / 200, "Multi": 21 / 200, "Null": 20 / 200}
LABELS = ("accurate", "error", "neither")


def sigma(m):
    return math.sqrt(D * m)


def mcnemar_p(b, c):
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n)


def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


def load_jsonl(path):
    out = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                out[r["question"]] = r            # bản ghi sau cùng thắng (resume)
    return out


def append_jsonl(path, rec):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def cache_size():
    return sum(1 for l in open(KW_CACHE, encoding="utf-8") if l.strip()) if os.path.exists(KW_CACHE) else 0


# ---------------------------------------------------------------- tập câu hỏi (chỉ dev)
def dev_rows():
    rows = list(csv.DictReader(open(os.path.join(ROOT, "logs", "devset.csv"), encoding="utf-8")))
    assert len(rows) == 200 and len({r["Question"] for r in rows}) == 200
    return rows


def question_set(stage):
    dev = {r["Question"] for r in dev_rows()}
    if stage == "canary":
        rows = list(csv.DictReader(open(os.path.join(HERE, "canary100.csv"), encoding="utf-8")))
        assert len(rows) == 100
    else:
        rows = [dict(r, batch="1") for r in dev_rows()]
    for r in rows:
        assert r["Question"] in dev, f"câu ngoài dev bị chặn: {r['Question'][:70]}"
    return rows


def gold_map():
    g = {}
    for line in open(os.path.join(ROOT, "logs", "diag_path2chunk.jsonl"), encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            if r.get("gold"):
                g[r["question"]] = r["gold"]
    return g


# ---------------------------------------------------------------- truy vấn, sinh, chấm
def set_env(variant, ctx_log, cache_only):
    os.environ.update(BASE_ENV)
    os.environ.update({"MINIRAG_CHUNK_FUSION": VARIANTS[variant], "MINIRAG_CONTEXT_LOG": ctx_log,
                       "MINIRAG_KW_CACHE": KW_CACHE, "MINIRAG_SLM_SEED": str(SEED)})
    for k in ("MINIRAG_TRUNCATE_SOURCES", "MINIRAG_MAX_TOKEN_TEXT_UNIT"):
        os.environ.pop(k, None)
    if cache_only:
        os.environ["MINIRAG_KW_CACHE_ONLY"] = "1"
    else:
        os.environ.pop("MINIRAG_KW_CACHE_ONLY", None)


async def run_query(rag, q, variant, only_ctx, cache_only):
    from minirag import QueryParam
    log = os.path.join(OUT, "cache", f"ctx_{os.getpid()}.jsonl")
    os.makedirs(os.path.dirname(log), exist_ok=True)
    if os.path.exists(log):
        os.remove(log)
    set_env(variant, log, cache_only)
    t0 = time.perf_counter()
    out = await rag.aquery(q, QueryParam(mode="mini", only_need_context=only_ctx))
    ms = 1000 * (time.perf_counter() - t0)
    lines = [l for l in open(log, encoding="utf-8") if l.strip()] if os.path.exists(log) else []
    return out, (json.loads(lines[-1]) if lines else None), ms


def prompt_sha(q, ctx):
    from minirag import QueryParam
    from minirag.prompt import PROMPTS
    sp = PROMPTS["rag_response"].format(context_data=ctx, response_type=QueryParam().response_type)
    return hashlib.sha256((sp + "\x00" + q).encode("utf-8")).hexdigest()


async def contexts(rag, rows, variant, cache_only):
    res = {}
    for r in rows:
        q = r["Question"]
        out, rec, _ = await run_query(rag, q, variant, True, cache_only)
        if rec is None:        # parser hỏng hoặc đồ thị không ra node/cạnh -> câu trả lời cố định fail_response
            res[q] = {"none": True, "context_sha256": "NONE", "prompt_sha256": "NONE", "chunk_ids": [],
                      "ranked_ids": [], "tokens": None, "sources_tok": None, "retrieval_ms": None,
                      "graph_seeds": None, "graph_paths": None}
        else:
            res[q] = {"none": False, "context_sha256": rec["context_sha256"], "prompt_sha256": prompt_sha(q, out),
                      "chunk_ids": rec["chunk_ids"], "ranked_ids": rec["ranked_ids"],
                      "tokens": rec["sources_tok"] + rec["entities_tok"], "sources_tok": rec["sources_tok"],
                      "retrieval_ms": rec["retrieval_ms"], "graph_seeds": rec.get("graph_seeds"),
                      "graph_paths": rec.get("graph_paths")}
    return res


def same_context(a, b):
    return (a["context_sha256"] == b["context_sha256"] and a["chunk_ids"] == b["chunk_ids"]
            and a["prompt_sha256"] == b["prompt_sha256"])


def wait_for_qa():
    while subprocess.run(["pgrep", "-f", "Step_1_QA.py"], capture_output=True).returncode == 0:
        print(time.strftime("%H:%M"), "đang có Step_1_QA chạy — chờ 60 s (không sinh song song)", flush=True)
        time.sleep(60)


async def generate(rag, q, variant, ctx):
    from minirag.prompt import PROMPTS
    if ctx["none"]:
        return {"answer": PROMPTS["fail_response"].replace("\n", "").replace("\r", ""), "gen_ms": 0.0,
                "generated": False}
    for attempt in range(3):
        try:
            out, rec, ms = await run_query(rag, q, variant, False, True)
            break
        except Exception as e:     # noqa: BLE001
            print(f"  lỗi sinh ({attempt + 1}/3): {e}", flush=True)
            await asyncio.sleep(30)
    else:
        return None
    sha = rec["context_sha256"] if rec else "NONE"
    if sha != ctx["context_sha256"]:
        sys.exit(f"ASSERT: context lúc sinh lệch hash đã tính ({q[:60]}) — pipeline không tất định, dừng")
    return {"answer": (out or "").replace("\n", "").replace("\r", ""), "gen_ms": round(ms, 1), "generated": True,
            "endpoint": os.environ.get("MINIRAG_SLM_URL", "")}


def judge(items, tag, vdir):
    """1 lượt chấm qua Step_2_evaluate.py (env sạch biến SLM). items: [(question, gold, answer)]."""
    if not items:
        return {}
    os.makedirs(vdir, exist_ok=True)
    inp, outp = os.path.join(vdir, f"judge_{tag}.csv"), os.path.join(vdir, f"judge_{tag}_judged.csv")
    with open(inp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Question", "Gold Answer", "minirag"])
        w.writerows(items)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("MINIRAG_") and k not in ("GEMINI_API_BASE", "GEMINI_API_KEY_ONLY")}
    env.update(GEMINI_RPM="13", GEMINI_TPM="3000", PYTHONUNBUFFERED="1")
    for attempt in range(3):
        rc = subprocess.run([sys.executable, os.path.join(ROOT, "reproduce", "Step_2_evaluate.py"), "--inputpath", inp,
                             "--output", outp, "--repeats", "1"], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL).returncode
        if rc == 0:
            break
        print(f"  judge còn lượt hỏng — chờ 120 s rồi chấm lại ({attempt + 1}/3)", flush=True)
        time.sleep(120)
    got = {}
    if os.path.exists(outp):
        for r in csv.DictReader(open(outp, encoding="utf-8")):
            if r["run"] == "1" and r["verdict"] in LABELS:
                got[r["question"]] = r["verdict"]
    return got


# ---------------------------------------------------------------- thống kê và cổng
def compare(rows, base, var):
    types = {r["Question"]: r["Type"] for r in rows}
    qs = [r["Question"] for r in rows if base.get(r["Question"]) in LABELS and var.get(r["Question"]) in LABELS]
    acc = lambda d, q: d[q] == "accurate"  # noqa: E731

    def updown(qq):
        u = sum(acc(var, q) and not acc(base, q) for q in qq)
        dn = sum(acc(base, q) and not acc(var, q) for q in qq)
        return u, dn

    def rate(d, qq, lab):
        return 100 * sum(d[q] == lab for q in qq) / len(qq) if qq else None

    up, down = updown(qs)
    by = {}
    for t in DEV_W:
        tq = [q for q in qs if types[q] == t]
        u, dn = updown(tq)
        by[t] = {"n": len(tq), "base_acc": rate(base, tq, "accurate"), "var_acc": rate(var, tq, "accurate"),
                 "up": u, "down": dn, "net": u - dn}
    adj = lambda d: sum(DEV_W[t] * (rate(d, [q for q in qs if types[q] == t], "accurate") or 0) for t in DEV_W)  # noqa: E731
    return {"n": len(qs), "excluded": len(rows) - len(qs), "up": up, "down": down, "net": up - down,
            "mcnemar_p": mcnemar_p(up, down), "base": {l: rate(base, qs, l) for l in LABELS},
            "var": {l: rate(var, qs, l) for l in LABELS},
            "err_delta_count": sum(var[q] == "error" for q in qs) - sum(base[q] == "error" for q in qs),
            "by_type": by, "adj_base_acc": adj(base), "adj_var_acc": adj(var)}


def safety(s, var_ctx, base_ctx, rows, stage):
    qs = [r["Question"] for r in rows]
    vt, bt = med(var_ctx[q]["tokens"] for q in qs), med(base_ctx[q]["tokens"] for q in qs)
    vm, bm = med(var_ctx[q]["retrieval_ms"] for q in qs), med(base_ctx[q]["retrieval_ms"] for q in qs)
    err_lim = 3 if stage == "canary" else 4
    checks = {"Null net ≥ −3": s["by_type"]["Null"]["net"] >= -3,
              "Multi net ≥ −3": s["by_type"]["Multi"]["net"] >= -3,
              f"số phiếu error tăng ≤ +{err_lim}": s["err_delta_count"] <= err_lim,
              "token context trung vị ±5%": bool(vt and bt and abs(vt / bt - 1) <= 0.05),
              "truy hồi thêm ≤ 50 ms": bool(vm is not None and bm is not None and vm - bm <= 50)}
    if stage == "dev":
        checks["Single net ≥ 0"] = s["by_type"]["Single"]["net"] >= 0
    return checks, {"tokens_var": vt, "tokens_base": bt, "retrieval_ms_var": vm, "retrieval_ms_base": bm}


def evidence(rows, ctxs, gold):
    rs = [r["Question"] for r in rows if r["Question"] in gold]
    G = sum(len(gold[q]) for q in rs)
    kept = sum(g in ctxs[q]["chunk_ids"] for q in rs for g in gold[q])
    full = sum(all(g in ctxs[q]["chunk_ids"] for g in gold[q]) for q in rs)
    return {"questions": len(rs), "gold_chunks": G, "retention": 100 * kept / G if G else None,
            "full": 100 * full / len(rs) if rs else None}


def fmt(x, nd=2):
    return "–" if x is None else f"{x:.{nd}f}".replace(".", ",")


def run_meta():
    """Ai chạy, trên endpoint nào — mỗi người chạy trên Modal của riêng mình nên phải ghi lại (không ghi khoá)."""
    name = subprocess.run(["git", "config", "user.name"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return {"endpoint": os.environ.get("MINIRAG_SLM_URL", ""), "ran_by": name}


def write_report(vdir, stage, rep, lines):
    meta = run_meta()
    rep = {**rep, **meta}
    lines = lines[:2] + [f"Endpoint: {meta['endpoint'] or '–'} · chạy bởi: {meta['ran_by'] or '–'}"] + lines[2:]
    os.makedirs(vdir, exist_ok=True)
    json.dump(rep, open(os.path.join(vdir, f"{stage}_report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(os.path.join(vdir, f"{stage}_report.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)


def qa_lines(s, gens, judges, gens_total, judges_total, extra=()):
    bt = s["by_type"]
    t = lambda k: f"{bt[k]['up']} lên / {bt[k]['down']} xuống (acc {fmt(bt[k]['base_acc'], 1)} → {fmt(bt[k]['var_acc'], 1)}, n = {bt[k]['n']})"  # noqa: E731
    return ["QA:",
            f"- câu đánh giá: {s['n']} (loại {s['excluded']})",
            f"- sinh mới: {gens} (cộng dồn biến thể: {gens_total}) · lời gọi judge: {judges} (cộng dồn: {judges_total})",
            f"- acc: {fmt(s['base']['accurate'])} → {fmt(s['var']['accurate'])} (Δ {fmt(s['var']['accurate'] - s['base']['accurate'])});"
            f" điều chỉnh theo tỉ lệ dev: {fmt(s['adj_base_acc'])} → {fmt(s['adj_var_acc'])}",
            f"- err: {fmt(s['base']['error'])} → {fmt(s['var']['error'])} (Δ số phiếu {s['err_delta_count']:+d});"
            f" neither {fmt(s['base']['neither'])} → {fmt(s['var']['neither'])}",
            f"- Single: {t('Single')}", f"- Multi: {t('Multi')}", f"- Null: {t('Null')}",
            f"- ghép cặp: {s['up']} lên / {s['down']} xuống, net {s['net']:+d} (McNemar p = {fmt(s['mcnemar_p'], 3)} — chỉ tham khảo)",
            *extra]


def savings_line(gens_total, judges_total):
    return (f"Tiết kiệm so với 637 × 3 cho biến thể này: sinh {gens_total}/637 ({fmt(100 * (1 - gens_total / 637), 1)}% ít hơn),"
            f" judge {judges_total}/1.911 ({fmt(100 * (1 - judges_total / 1911), 1)}% ít hơn).")


# ---------------------------------------------------------------- đông lạnh V3
async def freeze(rag, rows, stage, gold):
    frozen = load_jsonl(FROZEN)
    qid = {}
    for i, r in enumerate(csv.DictReader(open(os.path.join(ROOT, "dataset", "LiHua-World", "qa", "query_set.csv"),
                                          encoding="utf-8"))):
        qid.setdefault(r["Question"], i)
    new = [r for r in rows if r["Question"] not in frozen]
    print(f"V3 đông lạnh: đã có {len(rows) - len(new)}/{len(rows)} câu, cần thêm {len(new)}", flush=True)
    parser_before, gens = cache_size(), 0
    if new:
        wait_for_qa()
        ctxs = await contexts(rag, new, "v3", cache_only=False)
        for r in new:
            q = r["Question"]
            g = await generate(rag, q, "v3", ctxs[q])
            if g is None:
                print("  bỏ qua (sinh lỗi 3 lần):", q[:60], flush=True)
                continue
            gens += g["generated"]
            append_jsonl(FROZEN, {"question": q, "qid": qid[q], "type": r["Type"], "gold": r["Gold Answer"],
                                  "seed": SEED, "fusion": "rrf", **ctxs[q], **g, "verdict": None,
                                  "frozen_at": time.strftime("%Y-%m-%d %H:%M")})
        det_path = os.path.join(OUT, "frozen", "determinism.json")
        if stage == "canary" and not os.path.exists(det_path):
            frozen = load_jsonl(FROZEN)
            sample = [r["Question"] for r in rows if not frozen[r["Question"]]["none"]][:20]
            same = 0
            for q in sample:
                g2 = await generate(rag, q, "v3", frozen[q])
                gens += 1
                same += g2 is not None and g2["answer"] == frozen[q]["answer"]
            json.dump({"sample": len(sample), "identical": same}, open(det_path, "w"), indent=1)
            print(f"kiểm tất định: {same}/{len(sample)} câu trả lời trùng khớp khi sinh lại cùng seed", flush=True)
    frozen = load_jsonl(FROZEN)
    todo = [r for r in rows if r["Question"] in frozen and frozen[r["Question"]]["verdict"] is None]
    got = judge([(r["Question"], r["Gold Answer"], frozen[r["Question"]]["answer"]) for r in todo], f"v3_{stage}",
                os.path.join(OUT, "v3"))
    for r in todo:
        if r["Question"] in got:
            append_jsonl(FROZEN, {**frozen[r["Question"]], "verdict": got[r["Question"]]})
    frozen = load_jsonl(FROZEN)
    verdicts = {q: frozen[q]["verdict"] for q in frozen}
    s = compare(rows, verdicts, verdicts)
    ev = evidence([r for r in rows if r["Question"] in frozen], frozen, gold)
    det = json.load(open(os.path.join(OUT, "frozen", "determinism.json"))) if os.path.exists(
        os.path.join(OUT, "frozen", "determinism.json")) else None
    lines = [f"Variant: v3 (đông lạnh, chế độ sàng lọc seed {SEED})", f"Stage: {stage}",
             f"- câu có phán quyết: {s['n']}/{len(rows)} (thiếu {s['excluded']})",
             f"- acc / err / neither: {fmt(s['base']['accurate'])} / {fmt(s['base']['error'])} / {fmt(s['base']['neither'])};"
             f" điều chỉnh theo tỉ lệ dev: {fmt(s['adj_base_acc'])}",
             "- theo loại: " + " · ".join(f"{t} {fmt(v['base_acc'], 1)} (n = {v['n']})" for t, v in s["by_type"].items()),
             f"- bằng chứng: chunk đáp án giữ {fmt(ev['retention'], 1)}% · câu đủ đáp án {fmt(ev['full'], 1)}% ({ev['questions']} câu có evidence)",
             f"- sinh mới lần này: {gens} · lời gọi parser mới: {cache_size() - parser_before} · judge: {len(todo)}",
             f"- kiểm tất định (sinh lại cùng seed): {det['identical']}/{det['sample']} trùng khớp" if det else "- kiểm tất định: chưa chạy",
             "Decision: " + ("FROZEN" if s["excluded"] == 0 else "CHƯA ĐỦ — chạy lại để chấm/sinh phần thiếu")]
    write_report(os.path.join(OUT, "v3"), stage, {"stage": stage, "decision": "FROZEN" if s["excluded"] == 0 else "INCOMPLETE",
                                                  "summary": s, "evidence": ev, "determinism": det}, lines)


# ---------------------------------------------------------------- tầng A
async def stage_offline(rag, variant, gold):
    rows = [r for r in dev_rows() if r["Question"] in gold]
    parser_before = cache_size()
    try:
        base = await contexts(rag, rows, "v3", cache_only=True)
    except RuntimeError:
        print("cache parser thiếu câu dev — điền một lần (lời gọi parser ngắn, seed cố định)", flush=True)
        wait_for_qa()
        base = await contexts(rag, rows, "v3", cache_only=False)
    var = await contexts(rag, rows, variant, cache_only=True)
    types = {r["Question"]: r["Type"] for r in rows}
    full = lambda c, q: all(g in c[q]["chunk_ids"] for g in gold[q])  # noqa: E731
    qs = [r["Question"] for r in rows]
    b = sum(full(var, q) and not full(base, q) for q in qs)
    c = sum(full(base, q) and not full(var, q) for q in qs)
    by = {t: (sum(full(var, q) and not full(base, q) for q in qs if types[q] == t),
              sum(full(base, q) and not full(var, q) for q in qs if types[q] == t)) for t in ("Single", "Multi")}
    eb, ev = evidence(rows, base, gold), evidence(rows, var, gold)

    def rank_med(ctx):
        ranks = [ctx[q]["ranked_ids"].index(g) + 1 for q in qs for g in gold[q] if g in ctx[q]["ranked_ids"]]
        return med(ranks), sum(g in ctx[q]["ranked_ids"][:30] for q in qs for g in gold[q]) / eb["gold_chunks"] * 100

    (rb, r30b), (rv, r30v) = rank_med(base), rank_med(var)
    stb, stv = med(base[q]["sources_tok"] for q in qs), med(var[q]["sources_tok"] for q in qs)
    msb, msv = med(base[q]["retrieval_ms"] for q in qs), med(var[q]["retrieval_ms"] for q in qs)
    gates = {"R1 net câu đủ đáp án ≥ +9 và McNemar p < 0,01": b - c >= 9 and mcnemar_p(b, c) < 0.01,
             "R2 chunk đáp án giữ ≥ +3 điểm": ev["retention"] - eb["retention"] >= 3,
             "R3 token Sources trung vị ±5%": abs(stv / stb - 1) <= 0.05,
             "R4 Single xuống ≤ lên; Multi net ≥ −1": by["Single"][1] <= by["Single"][0] and by["Multi"][0] - by["Multi"][1] >= -1,
             "R5 truy hồi thêm ≤ 50 ms, không thêm lời gọi LLM": msv - msb <= 50}
    decision = "CONTINUE TO CANARY" if all(gates.values()) else "STOP"
    lines = [f"Variant: {variant} ({VARIANTS[variant]})", "Stage: offline (tầng A, dev 180 câu có evidence, parser cache, 0 judge)",
             "Retrieval:",
             f"- chunk đáp án giữ sau cắt 4.000: {fmt(eb['retention'], 1)}% → {fmt(ev['retention'], 1)}%",
             f"- câu đủ đáp án: {fmt(eb['full'], 1)}% → {fmt(ev['full'], 1)}% ({b} lên / {c} xuống, p = {mcnemar_p(b, c):.2g});"
             f" Single {by['Single'][0]}/{by['Single'][1]} · Multi {by['Multi'][0]}/{by['Multi'][1]}",
             f"- recall@30 trong thứ tự trộn: {fmt(r30b, 1)}% → {fmt(r30v, 1)}% · hạng trung vị chunk đáp án: {fmt(rb, 0)} → {fmt(rv, 0)}",
             f"- token Sources trung vị: {fmt(stb, 0)} → {fmt(stv, 0)} · chunk trung vị: {fmt(med(len(base[q]['chunk_ids']) for q in qs), 0)} → {fmt(med(len(var[q]['chunk_ids']) for q in qs), 0)}",
             f"- truy hồi (dựng context) trung vị: {fmt(msb, 1)} → {fmt(msv, 1)} ms · seed đồ thị trung vị {fmt(med(base[q]['graph_seeds'] for q in qs), 0)}, đường {fmt(med(base[q]['graph_paths'] for q in qs), 0)}",
             f"- dự báo từ probe: {PREDICTION.get(variant, '–')}",
             f"- lời gọi parser mới (điền cache): {cache_size() - parser_before}",
             "Gates:"] + [f"- {'ĐẠT' if ok else 'TRƯỢT'}: {k}" for k, ok in gates.items()] + [f"Decision: {decision}"]
    write_report(os.path.join(OUT, variant), "offline", {"gates": gates, "decision": decision, "up": b, "down": c,
                                                         "evidence_base": eb, "evidence_var": ev}, lines)


# ---------------------------------------------------------------- tầng B và C
async def stage_screen(rag, variant, stage, gold):
    rows = question_set(stage)
    vdir = os.path.join(OUT, variant)
    frozen = load_jsonl(FROZEN)
    missing = [r for r in rows if frozen.get(r["Question"], {}).get("verdict") not in LABELS]
    if missing:
        sys.exit(f"thiếu V3 đông lạnh cho {len(missing)} câu — chạy --variant v3 --stage {stage} trước")
    if stage == "dev":
        can = os.path.join(vdir, "canary_report.json")
        if not os.path.exists(can) or json.load(open(can))["decision"] != "PROMOTE":
            sys.exit("tầng C chỉ chạy khi canary của biến thể này là PROMOTE")
    print("dựng lại context V3 (cache parser) để kiểm tất định và đo độ trễ cùng lượt...", flush=True)
    base_ctx = await contexts(rag, rows, "v3", cache_only=True)
    bad = [q for q, c in base_ctx.items() if not same_context(c, frozen[q])]
    if bad:
        sys.exit(f"ASSERT: context V3 dựng lại lệch hash đông lạnh ở {len(bad)} câu — truy hồi không tất định, dừng")
    var_ctx = await contexts(rag, rows, variant, cache_only=True)
    changed = {q: not same_context(var_ctx[q], frozen[q]) for q in var_ctx}
    ans_path = os.path.join(vdir, "answers.jsonl")
    answers = load_jsonl(ans_path)
    gens = judges = 0
    base = {r["Question"]: frozen[r["Question"]]["verdict"] for r in rows}

    def variant_verdicts(subset):
        return {r["Question"]: (frozen[r["Question"]]["verdict"] if not changed[r["Question"]]
                                else answers.get(r["Question"], {}).get("verdict")) for r in subset}

    async def run_batch(brows, tag):
        nonlocal gens, judges
        need = [r for r in brows if changed[r["Question"]] and answers.get(r["Question"], {}).get("verdict") not in LABELS]
        to_gen = [r for r in need if "answer" not in answers.get(r["Question"], {})]
        if any(not var_ctx[r["Question"]]["none"] for r in to_gen):
            wait_for_qa()
        for r in to_gen:
            q = r["Question"]
            g = await generate(rag, q, variant, var_ctx[q])
            if g is None:
                continue
            gens += g["generated"]
            answers[q] = {"question": q, "type": r["Type"], **var_ctx[q], **g, "verdict": None}
            append_jsonl(ans_path, answers[q])
        items = [(r["Question"], r["Gold Answer"], answers[r["Question"]]["answer"]) for r in need if r["Question"] in answers]
        got = judge(items, f"{stage}_{tag}", vdir)
        judges += len(items)
        for q, v in got.items():
            answers[q]["verdict"] = v
            append_jsonl(ans_path, answers[q])

    m_total = sum(changed.values())
    decision, batch_log, processed, net_b1 = None, [], [], None
    if m_total == 0:
        decision = "STOP"
        batch_log.append("m = 0: biến thể không đổi đầu vào generator ở câu nào")
    batches = ["1", "2", "3"] if stage == "canary" else ["1"]
    for b in batches if decision is None else []:
        brows = [r for r in rows if r["batch"] == b]
        await run_batch(brows, f"b{b}")
        processed += brows
        s = compare(processed, base, variant_verdicts(processed))
        m = sum(changed[r["Question"]] for r in processed)
        sg = sigma(m)
        checks, eff = safety(s, var_ctx, base_ctx, processed, stage)
        invalid = s["excluded"] > 0.01 * len(processed)
        note = f"sau {len(processed)} câu: m = {m}, net {s['net']:+d}, σ(m) = {fmt(sg)}, loại {s['excluded']}"
        if invalid:
            decision = "INVALID"
        elif stage == "dev":
            decision = "PROMOTE" if s["net"] >= 1.0 * sg and all(checks.values()) else "STOP"
        elif b == "1":
            net_b1 = s["net"]
            if m > 0 and s["net"] <= -1.0 * sg:
                decision = "STOP"
        elif b == "2":
            if m > 0 and s["net"] <= -0.5 * sg:
                decision = "STOP"
            elif m > 0 and s["net"] >= 2.0 * sg and net_b1 > 0 and all(checks.values()):
                decision = "PROMOTE"
        else:
            decision = "PROMOTE" if s["net"] >= 1 and all(checks.values()) else "STOP"
        batch_log.append(note + (f" → {decision}" if decision else " → chạy tiếp"))
        print(batch_log[-1], flush=True)
        if decision:
            break

    s = compare(processed or rows, base, variant_verdicts(processed or rows))
    checks, eff = safety(s, var_ctx, base_ctx, processed or rows, stage)
    gens_total = sum(1 for a in answers.values() if a.get("generated"))
    judges_total = sum(1 for a in answers.values() if a.get("verdict") in LABELS)
    extra = []
    vec_j = os.path.join(ROOT, "logs", "qwen637_vec_judged.csv")
    if variant == "b2" and os.path.exists(vec_j):
        vec = {r["question"]: r["verdict"] for r in csv.DictReader(open(vec_j, encoding="utf-8")) if r["run"] == "1"}
        sv = compare(processed, vec, variant_verdicts(processed))
        extra.append(f"- phụ: so với vector thuần (lượt chính thức, run = 1, một lần rút không seed): {sv['up']} lên / {sv['down']} xuống")
    other = {"b1": "b2", "b2": "b1"}.get(variant)
    if other and os.path.exists(os.path.join(OUT, other, "answers.jsonl")):
        oans = load_jsonl(os.path.join(OUT, other, "answers.jsonl"))
        octx = await contexts(rag, processed, other, cache_only=True)
        ov = {r["Question"]: (frozen[r["Question"]]["verdict"] if same_context(octx[r["Question"]], frozen[r["Question"]])
                              else oans.get(r["Question"], {}).get("verdict")) for r in processed}
        so = compare(processed, ov, variant_verdicts(processed))
        m_diff = sum(not same_context(octx[r["Question"]], var_ctx[r["Question"]]) for r in processed)
        extra.append(f"- phụ: {variant} so với {other} trên {so['n']} câu chung: {so['up']} lên / {so['down']} xuống,"
                     f" net {so['net']:+d}, m khác nhau = {m_diff}, σ = {fmt(sigma(m_diff))}")
    ev_b, ev_v = evidence(processed or rows, base_ctx, gold), evidence(processed or rows, var_ctx, gold)
    lines = [f"Variant: {variant} ({VARIANTS[variant]})",
             f"Stage: {stage} ({len(processed)}/{len(rows)} câu; một lượt sinh seed {SEED} × một lượt chấm; bằng chứng sàng lọc, không phải kết luận H1–H3)",
             "Retrieval:",
             f"- chunk đáp án giữ: {fmt(ev_b['retention'], 1)}% → {fmt(ev_v['retention'], 1)}% · câu đủ đáp án: {fmt(ev_b['full'], 1)}% → {fmt(ev_v['full'], 1)}% ({ev_v['questions']} câu có evidence)",
             f"- token context trung vị: {fmt(eff['tokens_base'], 0)} → {fmt(eff['tokens_var'], 0)}",
             f"- truy hồi trung vị: {fmt(eff['retrieval_ms_base'], 1)} → {fmt(eff['retrieval_ms_var'], 1)} ms",
             f"- context đổi so với V3: {m_total}/{len(rows)} câu (câu không đổi dùng lại câu trả lời + phán quyết V3)",
             *qa_lines(s, gens, judges, gens_total, judges_total, extra),
             "Sequential gates:", *[f"- {x}" for x in batch_log],
             "Safety:", *[f"- {'ĐẠT' if ok else 'TRƯỢT'}: {k}" for k, ok in checks.items()],
             "Decision: " + {"PROMOTE": "CONTINUE TO DEV200" if stage == "canary" else "FINALIST (chờ duyệt tầng D)",
                             "STOP": "STOP", "INVALID": "INVALID (thiếu phán quyết > 1% — chạy lại để chấm bù)"}.get(decision, str(decision)),
             savings_line(gens_total, judges_total)]
    write_report(vdir, stage, {"stage": stage, "decision": decision, "processed": len(processed), "m_total": m_total,
                               "summary": s, "safety": checks, "efficiency": eff, "batches": batch_log,
                               "gens_total": gens_total, "judges_total": judges_total,
                               "contexts": {q: {"sha": c["context_sha256"], "changed": changed[q]} for q, c in var_ctx.items()}},
                 lines)


async def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--variant", required=True, choices=sorted(VARIANTS))
    ap.add_argument("--stage", required=True, choices=["offline", "canary", "dev"])
    own, rest = ap.parse_known_args()
    sys.argv = [sys.argv[0]] + rest
    from gemini_common import build_rag, get_args
    rag = build_rag(get_args("screen_variant"))
    gold = gold_map()
    if own.variant == "v3":
        if own.stage == "offline":
            sys.exit("V3 là mốc; tầng offline chỉ chạy cho biến thể")
        await freeze(rag, question_set(own.stage), own.stage, gold)
    elif own.stage == "offline":
        await stage_offline(rag, own.variant, gold)
    else:
        await stage_screen(rag, own.variant, own.stage, gold)


if __name__ == "__main__":
    asyncio.run(main())
