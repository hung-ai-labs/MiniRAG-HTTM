"""Máy chủ demo: hỏi một câu, nhận HAI câu trả lời (MiniRAG gốc và B2) kèm bằng chứng lấy được,
rồi để Gemini chấm cả hai.

    reproduce/demo/run_server.sh              # Modal Qwen2.5-3B (khớp số benchmark)
    MINIRAG_DEMO_LLM=gemini reproduce/demo/run_server.sh

Rồi mở http://127.0.0.1:8765

An toàn:
- Kho đã đóng băng (LiHua-World-qwen-modal) CHỈ ĐỌC. Mọi tài liệu tải lên đi vào kho riêng
  playground-index/demo/ — nếu ghi vào kho đông lạnh thì mọi số benchmark trong repo mất giá trị.
- Hai cấu hình chạy TUẦN TỰ trên cùng câu hỏi, cùng kho, cùng model sinh; chỉ khác đúng một biến:
  MINIRAG_CHUNK_FUSION rỗng (gốc) so với vector_bm25 (B2).
- Giám khảo Gemini chạy HAI việc tách biệt, đừng trộn hai thứ này khi trình bày:
  (a) phán quyết accurate/error/neither bằng ĐÚNG prompt của Step_2_evaluate — đây là con số
      so sánh được với benchmark; mỗi câu trả lời được chấm độc lập, không thấy câu còn lại;
  (b) một nhận xét so sánh, có làm mù thứ tự (A/B hoán vị ngẫu nhiên) để tránh thiên lệch vị trí.
      Đây là bình luận định tính, KHÔNG phải số liệu benchmark.
- Hai cấu hình chia nhau cùng bảng Entities và cùng tập đường đi: MINIRAG_CHUNK_FUSION chỉ đổi
  xếp hạng Sources. Nên phần entity/path thường giống nhau — UI nói thẳng điều đó thay vì
  dựng ra một khác biệt không có.
"""
import asyncio, csv, io, json, os, random, re, shutil, sys, time, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "reproduce"))

FROZEN = os.path.join(ROOT, "LiHua-World-qwen-modal")
PLAY = os.path.join(ROOT, "playground-index", "demo")
UPLOADS = os.path.join(ROOT, "uploads", "demo")
CTXLOG = os.path.join(ROOT, "logs", "demo", "_ctx")
QUERYSET = os.path.join(ROOT, "dataset", "LiHua-World", "qa", "query_set.csv")
BASE_ENV = {"MINIRAG_ANSWER_TYPE_FIX": "1", "MINIRAG_PATH2CHUNK_FIX": "0", "MINIRAG_CHUNK_CUT": ""}
JUDGE_MODEL = os.environ.get("MINIRAG_DEMO_JUDGE", "gemini-flash-lite-latest")
ARMS = [("goc", "MiniRAG gốc", ""), ("b2", "B2 — bản cải tiến", "vector_bm25")]

_lock = asyncio.Lock()          # biến môi trường là toàn cục -> phải chạy tuần tự
_rags, _graph_cache = {}, {}


# ---------------------------------------------------------------- kho
def build(workdir):
    if workdir in _rags:
        return _rags[workdir]
    from gemini_common import build_rag, get_args
    argv, sys.argv = sys.argv, [sys.argv[0]]
    try:
        a = get_args("demo")
        a.workingdir = workdir
        a.model = os.environ.get("MINIRAG_SLM_MODEL") or a.model
        _rags[workdir] = build_rag(a)
    finally:
        sys.argv = argv
    return _rags[workdir]


def chunks_of(workdir):
    p = os.path.join(workdir, "kv_store_text_chunks.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def ctime(text):
    m = re.search(r"Time:\s*(\S+)", text or "")
    return m.group(1) if m else ""


def snippet(text, n=150):
    for l in (text or "").split("\n"):
        l = l.strip()
        if l and not l.startswith("Time:"):
            return l[:n] + ("…" if len(l) > n else "")
    return (text or "")[:n]


def graph_of(workdir):
    """Đọc đồ thị thực thể từ graphml (nhớ đệm lại vì file lớn)."""
    if workdir in _graph_cache:
        return _graph_cache[workdir]
    import networkx as nx
    p = os.path.join(workdir, "graph_chunk_entity_relation.graphml")
    if not os.path.exists(p):
        return {"nodes": [], "edges": [], "n_nodes": 0, "n_edges": 0}
    g = nx.read_graphml(p)
    deg = dict(g.degree())
    nodes = [{"id": n, "type": (d.get("entity_type") or "").strip('"'),
              "desc": (d.get("description") or "")[:400], "deg": deg.get(n, 0)}
             for n, d in g.nodes(data=True)]
    nodes.sort(key=lambda x: -x["deg"])
    edges = [{"s": u, "t": v, "desc": (d.get("description") or "")[:240],
              "w": float(d.get("weight", 1) or 1)} for u, v, d in g.edges(data=True)]
    out = {"nodes": nodes, "edges": edges, "n_nodes": g.number_of_nodes(), "n_edges": g.number_of_edges()}
    _graph_cache[workdir] = out
    return out


# ---------------------------------------------------------------- bộ câu hỏi có sẵn
_qs_cache = {}


def queryset():
    """Câu hỏi kèm đáp án vàng của chính LiHua-World, để hỏi cái đã biết đáp án."""
    if "rows" in _qs_cache:
        return _qs_cache["rows"]
    rows, seen = [], set()
    if os.path.exists(QUERYSET):
        for r in csv.DictReader(open(QUERYSET, encoding="utf-8")):
            q = (r["Question"] or "").strip()
            if not q or q in seen:                 # query_set có 2 câu trùng
                continue
            seen.add(q)
            rows.append({"q": q, "gold": (r["Gold Answer"] or "").strip(),
                         "type": (r["Type"] or "").strip(),
                         "evidence": [t for t in (r["Evidence"] or "").split("<and>") if t.strip()]})
    _qs_cache["rows"] = rows
    return rows


def evidence_map(workdir):
    """Evidence trong query_set là dấu thời gian -> tìm chunk mang đúng 'Time: <ts>'."""
    key = ("ev", workdir)
    if key in _qs_cache:
        return _qs_cache[key]
    m = {}
    for cid, rec in chunks_of(workdir).items():
        t = ctime(rec.get("content", ""))
        if t:
            m.setdefault(t, []).append(cid)
    _qs_cache[key] = m
    return m


# ---------------------------------------------------------------- giám khảo Gemini
JUDGE_PROMPT = """You are grading a question-answering system.

Question: {question}
Gold answer: {gold}
System answer: {pred}

Reply with exactly one word:
- "accurate" if the system answer conveys the gold answer. Wording may differ;
  a more specific but consistent answer still counts (gold "bottle", answer
  "water bottle" -> accurate).
- "error" if the system answer asserts something that contradicts the gold
  answer, without acknowledging any uncertainty.
- "neither" if the system answer says it does not know, refuses to answer, or
  is off-topic.
"""

COMPARE_PROMPT = """Bạn là giám khảo cho một hệ thống hỏi đáp trên tài liệu. Trả lời bằng tiếng Việt.

Câu hỏi: {question}
{goldline}
Câu trả lời A: {a}

Câu trả lời B: {b}

Hãy trả về ĐÚNG định dạng JSON sau, không thêm chữ nào ngoài JSON:
{{"winner": "A" | "B" | "tie",
  "ly_do": "<một đến hai câu: vì sao bên thắng tốt hơn, nêu rõ chi tiết cụ thể>",
  "nhan_xet_A": "<một câu>",
  "nhan_xet_B": "<một câu>"}}

Tiêu chí, theo thứ tự quan trọng: (1) có nêu đúng dữ kiện mà câu hỏi đòi hay không;
(2) có dữ kiện nào bị bịa hoặc mâu thuẫn (sai ngày, sai người nói, sai thứ tự) hay không;
(3) có nói "không biết" khi lẽ ra trả lời được hay không. Câu dài hơn không phải là tốt hơn.
"""


async def judge_one(question, gold, pred):
    """Phán quyết một câu, ĐÚNG prompt benchmark. Lỗi thì nói lỗi, không bịa 'neither'."""
    from minirag.llm.gemini import gemini_complete_if_cache
    for attempt in range(4):
        try:
            v = await gemini_complete_if_cache(
                JUDGE_MODEL, JUDGE_PROMPT.format(question=question, gold=gold, pred=pred))
            v = (v or "").strip().strip('".').lower()
            return v if v in ("accurate", "error", "neither") else f"khong_ro:{v[:40]}"
        except Exception as e:
            if attempt == 3:
                return f"judge_failed: {type(e).__name__}"
            await asyncio.sleep(1.5 * (attempt + 1))


async def judge_compare(question, gold, ans):
    """Nhận xét so sánh, có làm mù thứ tự để không thiên lệch vị trí."""
    from minirag.llm.gemini import gemini_complete_if_cache
    keys = [k for k, _l, _f in ARMS]
    random.shuffle(keys)                              # A/B là cấu hình nào -> ngẫu nhiên
    slot = {"A": keys[0], "B": keys[1]}
    prompt = COMPARE_PROMPT.format(
        question=question,
        goldline=f"Đáp án vàng: {gold}" if gold else "(Câu này không có đáp án vàng.)",
        a=ans[slot["A"]], b=ans[slot["B"]])
    try:
        raw = await gemini_complete_if_cache(JUDGE_MODEL, prompt)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return {"error": "giám khảo không trả về JSON", "raw": (raw or "")[:400]}
    try:
        d = json.loads(m.group(0))
    except Exception as e:
        return {"error": f"JSON hỏng: {e}", "raw": (raw or "")[:400]}
    w = str(d.get("winner", "")).strip().upper()
    return {"winner_key": slot.get(w) if w in slot else "tie",
            "slot": slot,                              # công khai phép hoán vị để kiểm lại được
            "ly_do": d.get("ly_do", ""),
            "nhan_xet": {slot["A"]: d.get("nhan_xet_A", ""), slot["B"]: d.get("nhan_xet_B", "")}}


# ---------------------------------------------------------------- truy vấn
async def run_arm(rag, question, fusion, workdir):
    from minirag import QueryParam
    os.makedirs(CTXLOG, exist_ok=True)
    log = os.path.join(CTXLOG, f"{uuid.uuid4().hex}.jsonl")
    os.environ.update(BASE_ENV)
    os.environ["MINIRAG_CONTEXT_LOG"] = log
    os.environ.pop("MINIRAG_RERANK", None)          # chế độ cross-encoder KHÔNG bật trong demo
    if fusion:
        os.environ["MINIRAG_CHUNK_FUSION"] = fusion
    else:
        os.environ.pop("MINIRAG_CHUNK_FUSION", None)
    for k in ("MINIRAG_TRUNCATE_SOURCES", "MINIRAG_MAX_TOKEN_TEXT_UNIT", "MINIRAG_KW_CACHE_ONLY"):
        os.environ.pop(k, None)
    t0 = time.perf_counter()
    answer = await rag.aquery(question, QueryParam(mode="mini"))
    ms = 1000 * (time.perf_counter() - t0)
    rec = None
    if os.path.exists(log):
        lines = [l for l in open(log, encoding="utf-8") if l.strip()]
        rec = json.loads(lines[-1]) if lines else None
        os.remove(log)
    os.environ.pop("MINIRAG_CONTEXT_LOG", None)

    ch = chunks_of(workdir)
    out = {"answer": answer, "ms": round(ms), "none": rec is None}
    if rec:
        ranked = rec.get("ranked_ids") or []
        out.update({
            "n_cand": len(ranked), "sources_tok": rec.get("sources_tok"),
            "entities_tok": rec.get("entities_tok"),
            "graph_seeds": rec.get("graph_seeds"), "graph_paths": rec.get("graph_paths"),
            "retrieval_ms": round(rec.get("retrieval_ms") or 0),
            "sources": [{"id": c, "rank": ranked.index(c) + 1 if c in ranked else None,
                         "time": ctime(ch.get(c, {}).get("content", "")),
                         "snip": snippet(ch.get(c, {}).get("content", ""))}
                        for c in rec.get("chunk_ids", [])],
            # phần đồ thị: thực thể rút từ câu hỏi, bảng Entities thật sự vào context, và đường đi
            "query_entities": rec.get("query_entities") or [],
            "entities": [{"name": n, "score": round(sc, 4)}
                         for n, sc in (rec.get("entities_used") or [])],
            "paths": rec.get("paths") or [],
            "ranked_ids": ranked,
        })
    return out


def entities_from_context(ctx):
    """Bảng Entities nằm ngay trong context -> lấy ra để hiện 'thực thể đã dùng'."""
    m = re.search(r"-----Entities-----\s*```csv\s*(.*?)```", ctx or "", re.S)
    if not m:
        return []
    rows = [r for r in m.group(1).strip().split("\n") if r.strip()]
    return [r.split(",")[1].strip().strip('"') for r in rows[1:] if "," in r][:40]


# ---------------------------------------------------------------- app
def make_app():
    import gemini_common  # noqa: F401  — nạp .env ngay, để giám khảo Gemini chạy được cả khi sinh bằng Modal
    from fastapi import FastAPI, UploadFile, File, Form, HTTPException
    from fastapi.responses import HTMLResponse, JSONResponse

    app = FastAPI(title="MiniRAG demo")
    UI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.html")

    @app.get("/", response_class=HTMLResponse)
    def index():
        return open(UI, encoding="utf-8").read()

    @app.get("/api/status")
    def status():
        def info(w, name, ro):
            ch = chunks_of(w)
            docs = os.path.join(w, "kv_store_full_docs.json")
            nd = len(json.load(open(docs, encoding="utf-8"))) if os.path.exists(docs) else 0
            return {"key": name, "dir": os.path.relpath(w, ROOT), "docs": nd, "chunks": len(ch),
                    "readonly": ro, "exists": bool(ch)}
        return {"corpora": [info(FROZEN, "frozen", True), info(PLAY, "playground", False)],
                "llm": os.environ.get("MINIRAG_SLM_MODEL") or "gemini-flash-lite-latest",
                "endpoint": os.environ.get("GEMINI_API_BASE", "Gemini mặc định")}

    @app.get("/api/graph")
    def graph(corpus: str = "frozen", q: str = "", limit: int = 60):
        w = FROZEN if corpus == "frozen" else PLAY
        g = graph_of(w)
        nodes = g["nodes"]
        if q:
            s = q.lower()
            nodes = [n for n in nodes if s in n["id"].lower() or s in n["desc"].lower()]
        top = nodes[:limit]
        ids = {n["id"] for n in top}
        edges = [e for e in g["edges"] if e["s"] in ids and e["t"] in ids][:400]
        return {"n_nodes": g["n_nodes"], "n_edges": g["n_edges"], "matched": len(nodes),
                "nodes": top, "edges": edges}

    @app.get("/api/paths")
    def paths(corpus: str = "frozen", node: str = "", hops: int = 2, limit: int = 40):
        """Đường đi 2 bước từ một thực thể — đúng loại đường mà MiniRAG gốc dùng để xếp hạng chunk."""
        import networkx as nx
        w = FROZEN if corpus == "frozen" else PLAY
        p = os.path.join(w, "graph_chunk_entity_relation.graphml")
        if not os.path.exists(p) or not node:
            return {"paths": []}
        g = nx.read_graphml(p)
        if node not in g:
            raise HTTPException(404, f"không có thực thể {node!r}")
        out = []
        for nb in list(g.neighbors(node))[:limit]:
            if hops == 1:
                out.append([node, nb])
                continue
            for nb2 in list(g.neighbors(nb))[:6]:
                if nb2 != node:
                    out.append([node, nb, nb2])
                if len(out) >= limit:
                    break
            if len(out) >= limit:
                break
        return {"paths": out[:limit]}

    @app.post("/api/ask")
    async def ask(payload: dict):
        question = (payload.get("question") or "").strip()
        corpus = payload.get("corpus") or "frozen"
        if not question:
            raise HTTPException(400, "thiếu câu hỏi")
        w = FROZEN if corpus == "frozen" else PLAY
        if not chunks_of(w):
            raise HTTPException(400, "kho này chưa có tài liệu nào — tải tệp lên trước")
        async with _lock:
            rag = build(w)
            res = {}
            for key, label, fusion in ARMS:
                try:
                    res[key] = await run_arm(rag, question, fusion, w)
                    res[key]["label"] = label
                except Exception as e:                       # hỏng thì báo to, không giấu
                    res[key] = {"label": label, "error": f"{type(e).__name__}: {e}"}
        return JSONResponse({"arms": res, "gold": gold_info(question, w)})

    def gold_info(question, w):
        """Chunk đáp án theo cột Evidence của chính bộ dữ liệu — dùng để CHẤM, không vào runtime."""
        row = next((r for r in queryset() if r["q"] == question), None)
        if not row or w != FROZEN:
            return None
        ev, ch = evidence_map(w), chunks_of(w)
        want = []
        for ts in row["evidence"]:
            for cid in ev.get(ts.strip(), []):
                want.append({"id": cid, "time": ts.strip(),
                             "snip": snippet(ch.get(cid, {}).get("content", ""))})
        return {"gold_answer": row["gold"], "type": row["type"],
                "evidence_ts": row["evidence"], "chunks": want,
                "missing_ts": [t.strip() for t in row["evidence"] if not ev.get(t.strip())]}

    @app.get("/api/questions")
    def questions(q: str = "", type: str = "", limit: int = 60):
        rows = queryset()
        if type:
            rows = [r for r in rows if r["type"].lower() == type.lower()]
        if q:
            s = q.lower()
            rows = [r for r in rows if s in r["q"].lower()]
        return {"total": len(rows), "items": rows[:limit]}

    @app.post("/api/judge")
    async def judge(payload: dict):
        question = (payload.get("question") or "").strip()
        answers = payload.get("answers") or {}
        gold = (payload.get("gold") or "").strip()
        if not question or len(answers) < 2:
            raise HTTPException(400, "cần câu hỏi và hai câu trả lời")
        out = {"model": JUDGE_MODEL, "gold": gold}
        if gold:
            ks = list(answers)
            vs = await asyncio.gather(*[judge_one(question, gold, answers[k]) for k in ks])
            out["verdict"] = dict(zip(ks, vs))
        out["compare"] = await judge_compare(question, gold, answers)
        return out

    @app.post("/api/upload")
    async def upload(file: UploadFile = File(...)):
        name = os.path.basename(file.filename or "tai_lieu")
        raw = await file.read()
        ext = os.path.splitext(name)[1].lower()
        if ext == ".docx":
            import docx
            text = "\n".join(p.text for p in docx.Document(io.BytesIO(raw)).paragraphs)
        elif ext in (".txt", ".md", ".csv", ".json"):
            text = raw.decode("utf-8", "replace")
        else:
            raise HTTPException(400, f"chưa hỗ trợ đuôi {ext} — dùng .docx, .txt, .md")
        text = text.strip()
        if len(text) < 30:
            raise HTTPException(400, "tệp không có nội dung chữ đọc được")
        os.makedirs(UPLOADS, exist_ok=True)
        open(os.path.join(UPLOADS, name), "w", encoding="utf-8").write(text)
        async with _lock:
            os.makedirs(PLAY, exist_ok=True)
            rag = build(PLAY)                                # luôn là kho riêng, không bao giờ là kho đông lạnh
            os.environ.update(BASE_ENV)
            os.environ.pop("MINIRAG_CONTEXT_LOG", None)
            t0 = time.perf_counter()
            await rag.ainsert(text)
            _graph_cache.pop(PLAY, None)
        return {"ok": True, "name": name, "chars": len(text),
                "sec": round(time.perf_counter() - t0, 1), "chunks": len(chunks_of(PLAY))}

    @app.post("/api/reset_playground")
    async def reset():
        """Xoá kho nháp. KHÔNG bao giờ chạm vào kho đông lạnh."""
        async with _lock:
            _rags.pop(PLAY, None)
            _graph_cache.pop(PLAY, None)
            if os.path.isdir(PLAY):
                shutil.rmtree(PLAY)
        return {"ok": True}

    return app


if __name__ == "__main__":
    import uvicorn
    assert os.path.abspath(PLAY) != os.path.abspath(FROZEN), "kho nháp trùng kho đông lạnh"
    print(f"Kho đông lạnh (chỉ đọc): {FROZEN}")
    print(f"Kho nháp cho tệp tải lên: {PLAY}")
    print("→ http://127.0.0.1:8765")
    uvicorn.run(make_app(), host="127.0.0.1", port=int(os.environ.get("PORT", 8765)), log_level="warning")
