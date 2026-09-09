"""Serve MiniRAG's bundled web UI against the team's Gemini + local-embedding setup.

The upstream server (`minirag/api/minirag_server.py`) cannot be used here. It
accepts only lollms / ollama / openai / azure_openai for the embedding binding
(`minirag_server.py:720`), and none of those is the local
`all-MiniLM-L6-v2` this project indexed with. Pointing it at any other embedder
would search a 384-dimension index with vectors from a different space -- the
results would be meaningless rather than merely worse.

So this reuses `reproduce/gemini_common.build_rag()`, which is already the
exact configuration that produced the frozen baseline, and serves the same
static UI on top of it. Read-only: the upload/scan endpoints are deliberately
not implemented, because inserting a document here would mutate the baseline
index.

    python reproduce/serve_ui.py --workingdir ./LiHua-World-gemini --port 9621
"""

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.append(_HERE)
sys.path.append(_ROOT)

from fastapi import FastAPI, File, UploadFile  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from gemini_common import build_rag, get_args  # noqa: E402
from minirag import QueryParam  # noqa: E402

STATIC_DIR = os.path.join(_ROOT, "minirag", "api", "static")

# The index the frozen baseline (accuracy 57.33 +/- 1.53) was measured on.
# Inserting into it would change the graph and silently void every comparison
# made against that number, so indexing is refused there no matter what flags
# are passed.
BASELINE_DIR = os.path.abspath(os.path.join(_ROOT, "LiHua-World-gemini"))

REFUSE_MSG = (
    "Indexing is disabled on this server. Start it with --allow-index and a "
    "--workingdir that is NOT the baseline index, e.g.:\n"
    "  python reproduce/serve_ui.py --workingdir ./playground-index "
    "--allow-index"
)


class QueryRequest(BaseModel):
    query: str
    mode: str = "mini"
    only_need_context: bool = False
    top_k: int = 0
    stream: bool = False


def parse_args():
    # gemini_common.get_args() calls parse_args(), which rejects anything it
    # does not declare -- so pull our own flags out of sys.argv first.
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--port", type=int, default=9621)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--allow-index", action="store_true",
                   help="Permit uploading and indexing documents. Never allowed "
                        "on the baseline index.")
    p.add_argument("--uploaddir", default="./uploads")
    extra, rest = p.parse_known_args()
    sys.argv = [sys.argv[0]] + rest

    args = get_args("Serve the MiniRAG UI over the project's Gemini setup")
    args.port, args.host = extra.port, extra.host
    args.allow_index, args.uploaddir = extra.allow_index, extra.uploaddir

    if args.allow_index and os.path.abspath(args.workingdir) == BASELINE_DIR:
        sys.exit(
            "Refusing to enable indexing on the baseline index "
            f"({args.workingdir}).\nThe frozen baseline 57.33 +/- 1.53 was "
            "measured on this exact graph; adding documents would void every "
            "comparison against it.\nPass a different --workingdir, e.g. "
            "./playground-index"
        )
    return args


ARGS = parse_args()
print("Loading index from", ARGS.workingdir, "...")
RAG = build_rag(ARGS)
print("Index ready.")

app = FastAPI(title="MiniRAG UI (Gemini + local embeddings)")


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "working_directory": ARGS.workingdir,
        "configuration": {
            "llm_model": ARGS.model,
            "embedding": "sentence-transformers/all-MiniLM-L6-v2 (384d, local)",
            "indexing": "enabled" if ARGS.allow_index else "disabled (read-only)",
        },
    }


@app.get("/graph")
async def graph_data(limit: int = 400, min_degree: int = 0):
    """Nodes and edges for the viewer, heaviest-connected first.

    The baseline graph has 770 nodes and 1,779 edges; drawing all of them at
    once is unreadable, so the busiest `limit` nodes are kept and edges are
    restricted to that subset.
    """
    g = RAG.chunk_entity_relation_graph._graph
    ranked = sorted(g.nodes(), key=lambda n: g.degree(n), reverse=True)
    keep = [n for n in ranked if g.degree(n) >= min_degree][:limit]
    kept = set(keep)
    nodes = [{
        "id": n.strip('"'),
        "type": str(g.nodes[n].get("entity_type", "")).strip('"').upper() or "UNKNOWN",
        "degree": g.degree(n),
        "description": str(g.nodes[n].get("description", "")).strip('"')
                         .replace("<SEP>", " · ")[:400],
    } for n in keep]
    def _clean(x, n=400):
        x = str(x or "").strip('"').replace("<SEP>", " · ")
        return x if len(x) <= n else x[: n - 1] + "…"

    edges = [{
        "source": u.strip('"'), "target": v.strip('"'),
        "keywords": _clean(d.get("keywords"), 120),
        "description": _clean(d.get("description")),
        "weight": d.get("weight", 1),
    } for u, v, d in g.edges(data=True) if u in kept and v in kept]
    return {
        "nodes": nodes, "edges": edges,
        "total_nodes": g.number_of_nodes(), "total_edges": g.number_of_edges(),
        "shown_nodes": len(nodes), "shown_edges": len(edges),
    }


# Everything this server rewrites must be uncacheable. A browser that already
# holds upstream's api.js will keep serving it from cache -- the patched route
# returns 200 and looks fine from curl, while the page silently runs the old
# file and both panels stay empty.
NO_CACHE = {"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}


@app.get("/graph-view")
async def graph_view():
    from fastapi.responses import HTMLResponse

    with open(os.path.join(_HERE, "graph_view.html"), encoding="utf-8") as f:
        return HTMLResponse(f.read(), headers=NO_CACHE)


@app.get("/documents")
async def documents():
    """List what is actually in the index.

    The bundled UI has an "Indexed Files" panel but nothing ever fills it --
    `api.js` calls no listing endpoint, so the panel is empty on every reload
    and uploaded files look lost even though they were indexed.
    """
    store = RAG.doc_status._data if hasattr(RAG.doc_status, "_data") else {}
    docs = []
    for doc_id, v in store.items():
        docs.append({
            "id": doc_id,
            "summary": (v.get("content_summary") or "")[:120],
            "length": v.get("content_length", 0),
            "chunks": v.get("chunks_count", 0),
            "status": str(v.get("status", "")),
            "updated_at": v.get("updated_at", ""),
        })
    docs.sort(key=lambda d: d["updated_at"], reverse=True)
    g = RAG.chunk_entity_relation_graph._graph
    return {"documents": docs, "count": len(docs),
            "graph": {"nodes": g.number_of_nodes(), "edges": g.number_of_edges()}}


# Served before the StaticFiles mount so this patched copy wins over the file
# on disk. Upstream's own api.js is left untouched.
@app.get("/js/api.js")
async def patched_api_js():
    from fastapi.responses import Response

    with open(os.path.join(STATIC_DIR, "js", "api.js"), encoding="utf-8") as f:
        js = f.read()

    # 1. The Knowledge Graph tab is an "Under Construction" placeholder
    #    upstream. Point it at the viewer instead.
    start = js.find("'knowledge-graph': () => `")
    if start != -1:
        end = js.find("`,", js.find("`", start + 25))
        js = (js[:start]
              + "'knowledge-graph': () => `\n"
                '<iframe src="/graph-view" style="width:100%;height:calc(100vh - 120px);'
                'border:0;border-radius:8px"></iframe>\n`'
              + js[end + 1:])

    # 2. Fill the empty "Indexed Files" panel. The UI has no router hook to
    #    attach to, so watch for the panel appearing instead.
    js += """

// --- added by reproduce/serve_ui.py ---
(function pollIndexedFiles(){
  let last = "";
  setInterval(async () => {
    const box = document.querySelector("#indexedFiles div.space-y-2");
    if (!box) return;
    let d;
    try { d = await (await fetch("/documents")).json(); } catch (e) { return; }
    const sig = JSON.stringify(d.documents.map(x => x.id));
    if (sig === last && box.children.length) return;
    last = sig;
    box.innerHTML = d.documents.length
      ? `<p class="text-sm text-gray-500 mb-2">${d.count} tài liệu · đồ thị
           ${d.graph.nodes} node / ${d.graph.edges} cạnh</p>` +
        d.documents.map(x => `
          <div class="bg-white p-3 rounded-lg border border-gray-200">
            <div class="text-sm text-gray-800">${x.summary}…</div>
            <div class="text-xs text-gray-500 mt-1">
              ${x.length.toLocaleString()} ký tự · ${x.chunks} chunk · ${x.status}
            </div>
          </div>`).join("")
      : `<p class="text-sm text-gray-500">Chưa có tài liệu nào trong index.</p>`;
  }, 1200);
})();
"""
    return Response(js, media_type="application/javascript", headers=NO_CACHE)


@app.post("/query")
async def query(req: QueryRequest):
    kw = {"mode": req.mode, "only_need_context": req.only_need_context}
    if req.top_k:
        kw["top_k"] = req.top_k
    try:
        answer = await RAG.aquery(req.query, param=QueryParam(**kw))
    except Exception as e:  # surface the real error in the UI instead of a blank box
        return JSONResponse(status_code=500, content={"detail": f"{type(e).__name__}: {e}"})
    return {"response": answer}


def _extract_text(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".md", ".csv", ".json"):
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    if ext == ".docx":
        import docx

        return "\n".join(p.text for p in docx.Document(path).paragraphs)
    if ext == ".pdf":
        from PyPDF2 import PdfReader

        return "\n".join((p.extract_text() or "") for p in PdfReader(path).pages)
    raise ValueError(f"Unsupported file type: {ext or '(none)'}")


@app.post("/documents/upload")
async def upload(file: UploadFile = File(...)):
    if not ARGS.allow_index:
        return JSONResponse(status_code=403, content={"detail": REFUSE_MSG})

    os.makedirs(ARGS.uploaddir, exist_ok=True)
    dest = os.path.join(ARGS.uploaddir, os.path.basename(file.filename or "upload"))
    with open(dest, "wb") as f:
        f.write(await file.read())

    try:
        text = _extract_text(dest)
    except Exception as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})
    if not text.strip():
        return JSONResponse(
            status_code=400,
            content={"detail": "No text could be extracted (a scanned PDF has no text layer)."},
        )

    # Indexing costs roughly 2 LLM calls per 1200-token chunk.
    await RAG.ainsert(text)
    return {"status": "success", "message": f"Indexed {os.path.basename(dest)} "
                                            f"({len(text)} characters)"}


@app.post("/documents/scan")
async def scan():
    if not ARGS.allow_index:
        return JSONResponse(status_code=403, content={"detail": REFUSE_MSG})
    return {"status": "scan_started"}


@app.get("/documents/scan-progress")
async def _scan_progress():
    return {"is_scanning": False, "current_file": "", "indexed_count": 0, "total_files": 0, "progress": 0}


# Changes whenever this file does, so a browser holding an older api.js is
# asked for a URL it has never seen. no-store alone is not enough: it governs
# the response being sent now, while the stale entry the browser already has
# was stored without it and keeps being reused.
BUILD_ID = str(int(os.path.getmtime(__file__)))


@app.get("/")
@app.get("/index.html")
async def index():
    from fastapi.responses import HTMLResponse

    with open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8") as f:
        html = f.read()
    html = html.replace('src="/js/api.js"', f'src="/js/api.js?v={BUILD_ID}"')
    return HTMLResponse(html, headers=NO_CACHE)


if os.path.isdir(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
else:
    print("WARNING: static UI not found at", STATIC_DIR)


if __name__ == "__main__":
    import uvicorn

    print(f"\n  UI:   http://{ARGS.host}:{ARGS.port}")
    print(f"  Docs: http://{ARGS.host}:{ARGS.port}/docs\n")
    uvicorn.run(app, host=ARGS.host, port=ARGS.port, log_level="warning")
