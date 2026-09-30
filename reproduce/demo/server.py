"""Máy chủ demo: hỏi một câu, nhận HAI câu trả lời (MiniRAG gốc và B2) kèm bằng chứng lấy được.

    reproduce/demo/run_server.sh              # Modal Qwen2.5-3B (khớp số benchmark)
    MINIRAG_DEMO_LLM=gemini reproduce/demo/run_server.sh

Rồi mở http://127.0.0.1:8765

An toàn:
- Kho đã đóng băng (LiHua-World-qwen-modal) CHỈ ĐỌC. Mọi tài liệu tải lên đi vào kho riêng
  playground-index/demo/ — nếu ghi vào kho đông lạnh thì mọi số benchmark trong repo mất giá trị.
- Hai cấu hình chạy TUẦN TỰ trên cùng câu hỏi, cùng kho, cùng model sinh; chỉ khác đúng một biến:
  MINIRAG_CHUNK_FUSION rỗng (gốc) so với vector_bm25 (B2).
"""
import asyncio, io, json, os, re, shutil, sys, time, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "reproduce"))

FROZEN = os.path.join(ROOT, "LiHua-World-qwen-modal")
PLAY = os.path.join(ROOT, "playground-index", "demo")
UPLOADS = os.path.join(ROOT, "uploads", "demo")
CTXLOG = os.path.join(ROOT, "logs", "demo", "_ctx")
BASE_ENV = {"MINIRAG_ANSWER_TYPE_FIX": "1", "MINIRAG_PATH2CHUNK_FIX": "0", "MINIRAG_CHUNK_CUT": ""}
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
        return JSONResponse(res)

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
