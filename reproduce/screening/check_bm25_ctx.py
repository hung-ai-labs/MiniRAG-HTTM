"""Selftest BM25 (B1 = rrf_bm25, B2 = vector_bm25) + cache parser + seed sàng lọc. 0 API, 0 GPU.

Đăng ký trước: ROADMAP, "BM25 — đăng ký trước hai lượt B1, B2" và sửa đổi 14/09/2026. Chạy trên BẢN SAO index
(aquery ghi file cache vào working dir):

    python reproduce/screening/check_bm25_ctx.py --workingdir <bản sao index Qwen> --n 40
    python reproduce/screening/check_bm25_ctx.py --workingdir <bản sao> --ctxlog logs/<lượt>_ctx.jsonl

Selftest ĐẠT khi mọi kiểm dưới đây khớp 100% (câu hỏi lấy từ canary, tức chỉ dev):
 1. STOP của minirag/bm25.py trùng probe_query_signals.py; bm25_ids trong context-log trùng BM25 của probe.
 2. vector_ids = top-30 chunks_vdb trên câu hỏi gốc.
 3. ranked_ids = thứ tự trộn đúng công thức và chunk_ids = A1(ranked_ids) ở cả 5 chế độ: rỗng (đồ thị), rrf,
    vector, rrf_bm25, vector_bm25 (RRF tính lại độc lập bằng simulate_fusion.rrf).
 4. graph_ids giống nhau giữa các chế độ; chế độ không có BM25 không ghi bm25_ids.
 5. context_sha256 = sha256 của chuỗi context trả về; giá trị công tắc lạ báo lỗi.
 6. Cache parser: lần gọi thứ hai không gọi LLM, nạp lại từ file vẫn đúng; MINIRAG_KW_CACHE_ONLY=1 báo lỗi khi thiếu.
 7. MINIRAG_SLM_SEED được gửi vào request; không đặt thì không gửi.
Chế độ --ctxlog: kiểm 1–4 cho mọi dòng của một lượt chạy thật (đồ thị lấy từ graph_ids đã ghi).
"""
import asyncio, csv, hashlib, json, os, re, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "reproduce"))
sys.path.insert(0, ROOT)

import minirag.bm25 as mbm  # noqa: E402
import minirag.operate as op  # noqa: E402
from minirag import QueryParam  # noqa: E402
from gemini_common import build_rag, get_args  # noqa: E402
from probe_query_signals import BM25 as ProbeBM25, STOP as PROBE_STOP  # noqa: E402
from simulate_fusion import rrf  # noqa: E402

MODES = ("", "rrf", "vector", "rrf_bm25", "vector_bm25")
TOPN, A1 = 30, 4000


def a1(order, chunks):
    kept, tok = [], 0
    for cid in order:
        if cid not in chunks:
            continue
        t = len(op.encode_string_by_tiktoken(chunks[cid]["content"]))
        if tok + t > A1:
            break
        tok += t
        kept.append(cid)
    return kept, tok


def expected_order(mode, g, v, k):
    return {"": lambda: list(g), "rrf": lambda: rrf(g, v), "vector": lambda: list(v),
            "rrf_bm25": lambda: rrf(g, v, k), "vector_bm25": lambda: rrf(v, k)}[mode]()


def check_record(rec, mode, vexp, kexp, chunks, fails, tag):
    def check(cond, msg):
        if not cond:
            fails.append(f"{tag}: {msg}")
    check(rec["vector_ids"] == vexp, "vector_ids lệch top-30")
    if mode in ("rrf_bm25", "vector_bm25"):
        check(rec.get("bm25_ids") == kexp, "bm25_ids lệch probe")
    else:
        check("bm25_ids" not in rec, "có bm25_ids ở chế độ không BM25")
    order = expected_order(mode, rec["graph_ids"], vexp, kexp)
    kept, tok = a1(order, chunks)
    check(rec["ranked_ids"] == order, "thứ tự trộn lệch công thức")
    check(rec["chunk_ids"] == kept and rec["n_chunks"] == len(kept) and rec["sources_tok"] == tok, "A1 lệch")
    check(rec["fusion"] == mode, "fusion ghi sai")


async def selftest(rag, chunks, qs, fails):
    check = lambda cond, msg: None if cond else fails.append(msg)  # noqa: E731
    check(set(mbm.STOP) == set(PROBE_STOP), "STOP lệch probe")
    pbm = ProbeBM25({c: v["content"] for c, v in chunks.items()})
    tmp = tempfile.mkdtemp(prefix="bm25_selftest_")
    calls = {"kw": 0, "gen": 0}

    async def fake_llm(prompt, system_prompt=None, **kw):
        if "answer_type_keywords" in prompt:
            calls["kw"] += 1
            m = re.search(r"Query: (.*?)\nAnswer type pool", prompt.split("-Real Data-")[-1], re.S)
            ents = re.findall(r"\b[A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z]+)?", m.group(1) if m else "")[:4] or ["LI HUA"]
            return json.dumps({"answer_type_keywords": ["PERSON"], "entities_from_query": ents})
        calls["gen"] += 1
        return "stub answer"

    rag.llm_model_func = fake_llm
    os.environ.update({"MINIRAG_ANSWER_TYPE_FIX": "1", "MINIRAG_PATH2CHUNK_FIX": "0", "MINIRAG_CHUNK_CUT": ""})
    for k in ("MINIRAG_KW_CACHE", "MINIRAG_KW_CACHE_ONLY", "MINIRAG_TRUNCATE_SOURCES", "MINIRAG_MAX_TOKEN_TEXT_UNIT",
              "MINIRAG_SLM_SEED"):
        os.environ.pop(k, None)
    log = os.path.join(tmp, "ctx.jsonl")
    none = 0
    for q in qs:
        vexp = [x["id"] for x in await rag.chunks_vdb.query(q, top_k=TOPN)]
        kexp = pbm.rank(q)
        recs = {}
        for mode in MODES:
            if os.path.exists(log):
                os.remove(log)
            os.environ["MINIRAG_CHUNK_FUSION"], os.environ["MINIRAG_CONTEXT_LOG"] = mode, log
            ctx = await rag.aquery(q, QueryParam(mode="mini", only_need_context=True))
            recs[mode] = None if ctx is None or not os.path.exists(log) else (
                ctx, json.loads(open(log, encoding="utf-8").read().strip().splitlines()[-1]))
        if any(recs[m] is None for m in MODES):
            check(all(recs[m] is None for m in MODES), f"context None không nhất quán giữa chế độ: {q[:60]}")
            none += 1
            continue
        g = recs[""][1]["graph_ids"]
        for mode in MODES:
            ctx, rec = recs[mode]
            tag = f"[{mode or 'đồ thị'}] {q[:50]}"
            check(rec["graph_ids"] == g, f"{tag}: graph_ids đổi theo chế độ")
            check(rec["context_sha256"] == hashlib.sha256(ctx.encode("utf-8")).hexdigest(), f"{tag}: hash context lệch")
            check_record(rec, mode, vexp, kexp, chunks, fails, tag)

    os.environ["MINIRAG_CONTEXT_LOG"] = ""
    os.environ["MINIRAG_CHUNK_FUSION"] = "bm25_typo"
    try:
        await rag.aquery(qs[0], QueryParam(mode="mini", only_need_context=True))
        check(False, "công tắc lạ không báo lỗi")
    except ValueError:
        pass

    os.environ["MINIRAG_CHUNK_FUSION"] = "rrf"
    os.environ["MINIRAG_KW_CACHE"] = os.path.join(tmp, "kw.jsonl")
    op._KW_CACHE.clear()
    before = calls["kw"]
    c1 = await rag.aquery(qs[0], QueryParam(mode="mini", only_need_context=True))
    c2 = await rag.aquery(qs[0], QueryParam(mode="mini", only_need_context=True))
    op._KW_CACHE.clear()
    c3 = await rag.aquery(qs[0], QueryParam(mode="mini", only_need_context=True))
    check(calls["kw"] - before == 1, f"cache parser gọi LLM {calls['kw'] - before} lần, cần 1")
    check(c1 == c2 == c3, "cache parser: context đổi giữa các lần gọi")
    os.environ["MINIRAG_KW_CACHE_ONLY"] = "1"
    try:
        await rag.aquery(qs[1], QueryParam(mode="mini", only_need_context=True))
        check(False, "MINIRAG_KW_CACHE_ONLY không báo lỗi khi thiếu")
    except RuntimeError:
        pass
    for k in ("MINIRAG_KW_CACHE", "MINIRAG_KW_CACHE_ONLY"):
        os.environ.pop(k, None)

    import minirag.llm.gemini as gm
    captured = []

    class _Completions:
        async def create(self, **kw):
            captured.append(kw)
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="ok"))])

    fake = types.SimpleNamespace(chat=types.SimpleNamespace(completions=_Completions()))
    orig = gm._client
    gm._client = lambda *a, **k: fake
    try:
        os.environ["MINIRAG_SLM_SEED"] = "20260914"
        await gm.gemini_complete_if_cache("m", "hi")
        os.environ.pop("MINIRAG_SLM_SEED")
        await gm.gemini_complete_if_cache("m", "hi")
    finally:
        gm._client = orig
    check(len(captured) == 2 and captured[0].get("seed") == 20260914 and "seed" not in captured[1],
          "seed không được gửi đúng")
    return len(qs) - none, none


async def check_ctxlog(rag, chunks, path, fails):
    pbm = ProbeBM25({c: v["content"] for c, v in chunks.items()})
    recs = {}
    for line in open(path, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            recs[r["query"]] = r     # resume ghi lại vài câu -> giữ bản cuối
    for q, rec in recs.items():
        vexp = [x["id"] for x in await rag.chunks_vdb.query(q, top_k=TOPN)]
        check_record(rec, rec["fusion"], vexp, pbm.rank(q), chunks, fails, q[:50])
    return len(recs)


async def main():
    argv, n, ctxlog = sys.argv[1:], 40, None
    if "--n" in argv:
        i = argv.index("--n"); n = int(argv[i + 1]); del argv[i:i + 2]
    if "--ctxlog" in argv:
        i = argv.index("--ctxlog"); ctxlog = argv[i + 1]; del argv[i:i + 2]
    sys.argv = [sys.argv[0]] + argv
    args = get_args("Selftest BM25")
    wd = os.path.realpath(args.workingdir)
    assert wd != os.path.realpath(os.path.join(ROOT, "LiHua-World-qwen-modal")), "chạy trên BẢN SAO index"
    rag = build_rag(args)
    chunks = json.load(open(os.path.join(wd, "kv_store_text_chunks.json"), encoding="utf-8"))
    fails = []
    if ctxlog:
        k = await check_ctxlog(rag, chunks, ctxlog, fails)
        print(f"context-log {ctxlog}: {k} câu")
        ok = k > 0
    else:
        qs = [r["Question"] for r in csv.DictReader(open(os.path.join(HERE, "canary100.csv"), encoding="utf-8"))][:n]
        good, none = await selftest(rag, chunks, qs, fails)
        print(f"selftest BM25: {len(qs)} câu canary, {good} có context ({none} câu đồ thị không ra node/cạnh), "
              f"{len(MODES)} chế độ mỗi câu + công tắc lạ + cache parser + seed")
        ok = good > 0
    for f in fails[:25]:
        print("  LỆCH:", f)
    ok = ok and not fails
    print("KIỂM TOÀN VẸN:", "ĐẠT" if ok else f"TRƯỢT ({len(fails)} lỗi)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
