"""Kiểm toàn vẹn cho ablation vector thuần (MINIRAG_CHUNK_FUSION=vector). 0 API, 0 GPU.

Sources của chế độ vector chỉ phụ thuộc câu hỏi gốc (top-30 chunks_vdb rồi cắt A1@4000),
không phụ thuộc từ khoá LLM trích ra, nên tính lại offline được chính xác.

  --selftest N   chạy thật _build_mini_query_context trên N câu với LLM giả (trả JSON từ
                 khoá cố định), ghi lại thứ tự chunk được lấy ra, so với top-30 vector và
                 với context-log (số chunk, token). Chạy TRƯỚC khi tốn GPU.
  --ctxlog PATH  sau khi QA xong: so từng dòng context-log của lượt chạy thật với
                 A1(top-30 vector) tính offline. Mọi câu phải khớp.

Dùng --workingdir trỏ tới BẢN SAO index: aquery ghi lại file cache khi xong truy vấn.
"""
import asyncio, csv, json, os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(_HERE); sys.path.append(os.path.dirname(_HERE))

import minirag.operate as op  # noqa: E402
from minirag import QueryParam  # noqa: E402
from gemini_common import build_rag, get_args  # noqa: E402

TOPN, A1 = 30, 4000


def a1(ids, chunks):
    kept, tok = [], 0
    for cid in ids:
        if cid not in chunks:
            continue
        t = len(op.encode_string_by_tiktoken(chunks[cid]["content"]))
        if tok + t > A1:
            break
        tok += t
        kept.append(cid)
    return kept, tok


async def expected(rag, chunks, q):
    ids = [r["id"] for r in await rag.chunks_vdb.query(q, top_k=TOPN)]
    return ids, *a1(ids, chunks)


async def selftest(rag, chunks, questions, n, scratch):
    async def fake_llm(prompt, **kw):
        return json.dumps({"answer_type_keywords": ["PERSON"],
                           "entities_from_query": ["LI HUA", "WOLFGANG"]})
    rag.llm_model_func = fake_llm

    fetched = []
    orig = rag.text_chunks.get_by_id
    rag.text_chunks.get_by_id = lambda cid: (fetched.append(cid), orig(cid))[1]

    bad = differs_rrf = none = 0
    for q in questions[:n]:
        exp_ids, exp_kept, exp_tok = await expected(rag, chunks, q)
        got = {}
        for mode in ("vector", "rrf"):
            log = os.path.join(scratch, f"selftest_{mode}.jsonl")
            if os.path.exists(log):
                os.remove(log)
            os.environ["MINIRAG_CHUNK_FUSION"], os.environ["MINIRAG_CONTEXT_LOG"] = mode, log
            fetched.clear()
            ctx = await rag.aquery(q, QueryParam(mode="mini", only_need_context=True))
            rec = json.loads(open(log).read()) if os.path.exists(log) else None
            got[mode] = (list(fetched), rec, ctx)
        ids, rec, ctx = got["vector"]
        if ctx is None or rec is None:
            none += 1
            continue
        ok = ids == exp_ids and rec["n_chunks"] == len(exp_kept) and rec["sources_tok"] == exp_tok
        bad += not ok
        differs_rrf += got["rrf"][0] != ids
        if not ok:
            print(f"LỆCH: {q[:70]}\n  lấy {ids[:5]}… n={rec['n_chunks']} tok={rec['sources_tok']}"
                  f"\n  kỳ vọng {exp_ids[:5]}… n={len(exp_kept)} tok={exp_tok}")
    checked = min(n, len(questions)) - none
    print(f"selftest: {checked} câu có context ({none} câu đồ thị không ra node/cạnh), "
          f"lệch {bad}, khác thứ tự RRF {differs_rrf}/{checked}")
    return bad == 0 and checked > 0 and differs_rrf > 0


async def check_log(rag, chunks, path):
    recs = {}
    for line in open(path, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            recs[r["query"]] = r      # resume ghi lại vài câu -> giữ bản cuối
    bad = 0
    for q, r in recs.items():
        _, kept, tok = await expected(rag, chunks, q)
        if (r["n_chunks"], r["sources_tok"]) != (len(kept), tok):
            bad += 1
            print(f"LỆCH: {q[:70]} log n={r['n_chunks']} tok={r['sources_tok']} "
                  f"kỳ vọng n={len(kept)} tok={tok}")
    print(f"context-log {path}: {len(recs)} câu, lệch {bad}")
    return bad == 0 and len(recs) > 0


async def main():
    mode = {}
    argv = sys.argv[1:]
    for flag in ("--selftest", "--ctxlog"):
        if flag in argv:
            i = argv.index(flag); mode[flag] = argv[i + 1]; del argv[i:i + 2]
    sys.argv = [sys.argv[0]] + argv
    args = get_args("Kiểm ablation vector thuần")
    rag = build_rag(args)
    chunks = json.load(open(os.path.join(args.workingdir, "kv_store_text_chunks.json")))
    if "--selftest" in mode:
        qs = [r["Question"] for r in csv.DictReader(open(args.questions, encoding="utf-8"))]
        ok = await selftest(rag, chunks, qs, int(mode["--selftest"]), os.path.dirname(args.outputpath))
    else:
        ok = await check_log(rag, chunks, mode["--ctxlog"])
    print("KIỂM TOÀN VẸN:", "ĐẠT" if ok else "TRƯỢT")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
