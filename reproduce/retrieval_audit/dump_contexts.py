"""Giai đoạn 0 — dựng lại context của một chế độ trộn trên dev 200, hoàn toàn offline.

    reproduce/retrieval_audit/run_offline.sh dump_contexts.py --fusion vector_bm25

- Không gọi sinh, không gọi giám khảo: only_need_context=True, parser từ khoá đọc từ cache sàng lọc
  (MINIRAG_KW_CACHE_ONLY=1 — thiếu cache thì dừng, không gọi LLM).
- Cùng biến môi trường với lượt sàng lọc B2 đông lạnh (reproduce/screening/screen_variant.py: BASE_ENV, KW_CACHE).
- Ghi logs/retrieval_audit/<fusion>_dev_ctx.jsonl: bản ghi context-log của operate.py + nguyên văn context.
- So context_sha256 với logs/screening/b2/answers.jsonl (B2 đông lạnh) và in số câu trùng.
"""
import argparse, asyncio, csv, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "reproduce"))
sys.path.insert(0, ROOT)

OUT = os.path.join(ROOT, "logs", "retrieval_audit")
KW_CACHE = os.path.join(ROOT, "logs", "screening", "cache", "kw_cache.jsonl")
FROZEN_B2 = os.path.join(ROOT, "logs", "screening", "b2", "answers.jsonl")
BASE_ENV = {"MINIRAG_ANSWER_TYPE_FIX": "1", "MINIRAG_PATH2CHUNK_FIX": "0", "MINIRAG_CHUNK_CUT": ""}


async def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--fusion", default="vector_bm25")
    ap.add_argument("--tag", default="")
    ap.add_argument("--rerank", default="", help="chế độ thí nghiệm, vd. ce1; rỗng = B2 thuần")
    ap.add_argument("--limit", type=int, default=0, help="chỉ chạy N câu đầu (dùng cho selftest)")
    own, rest = ap.parse_known_args()
    sys.argv = [sys.argv[0]] + rest
    from gemini_common import build_rag, get_args
    from minirag import QueryParam
    rag = build_rag(get_args("dump_contexts"))

    rows = list(csv.DictReader(open(os.path.join(ROOT, "logs", "devset.csv"), encoding="utf-8")))
    assert len(rows) == 200
    if own.limit:
        rows = rows[: own.limit]
    os.makedirs(OUT, exist_ok=True)
    tag = own.tag or own.fusion
    out_path = os.path.join(OUT, f"{tag}_dev_ctx.jsonl")
    tmp_log = os.path.join(OUT, f".ctx_{os.getpid()}.jsonl")
    os.environ.update(BASE_ENV)
    os.environ.update({"MINIRAG_CHUNK_FUSION": own.fusion, "MINIRAG_CONTEXT_LOG": tmp_log,
                       "MINIRAG_KW_CACHE": KW_CACHE, "MINIRAG_KW_CACHE_ONLY": "1"})
    for k in ("MINIRAG_TRUNCATE_SOURCES", "MINIRAG_MAX_TOKEN_TEXT_UNIT", "MINIRAG_PATH_PRUNE", "MINIRAG_PATH_SCORE"):
        os.environ.pop(k, None)
    # chế độ thí nghiệm đặt TƯỜNG MINH: rỗng = B2 thuần, không thừa hưởng biến môi trường bên ngoài
    if own.rerank:
        os.environ["MINIRAG_RERANK"] = own.rerank
    else:
        os.environ.pop("MINIRAG_RERANK", None)

    with open(out_path, "w", encoding="utf-8") as fh:
        for r in rows:
            if os.path.exists(tmp_log):
                os.remove(tmp_log)
            ctx = await rag.aquery(r["Question"], QueryParam(mode="mini", only_need_context=True))
            lines = [l for l in open(tmp_log, encoding="utf-8") if l.strip()] if os.path.exists(tmp_log) else []
            rec = json.loads(lines[-1]) if lines else {"none": True}
            rec.update({"question": r["Question"], "type": r["Type"], "context": ctx if lines else None})
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    if os.path.exists(tmp_log):
        os.remove(tmp_log)

    frozen = {}
    for line in open(FROZEN_B2, encoding="utf-8"):
        f = json.loads(line)
        if f.get("verdict"):
            frozen[f["question"]] = f
    mine = {json.loads(l)["question"]: json.loads(l) for l in open(out_path, encoding="utf-8")}
    same = sum(1 for q, m in mine.items() if q in frozen and m.get("context_sha256") == frozen[q]["context_sha256"])
    same_ids = sum(1 for q, m in mine.items() if q in frozen and m.get("chunk_ids") == frozen[q]["chunk_ids"])
    print(f"{out_path}: {len(mine)} câu · context_sha256 trùng B2 đông lạnh {same}/{len(frozen)} · "
          f"chunk_ids trùng {same_ids}/{len(frozen)}")


if __name__ == "__main__":
    asyncio.run(main())
