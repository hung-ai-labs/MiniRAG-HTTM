"""Sửa cache parser sau lỗi thứ tự TYPE_POOL (14/09/2026) và kiểm V3 đông lạnh dựng lại được.

    SCREEN_SCRIPT=reproduce/screening/rekey_kw_cache.py reproduce/screening/run_screen.sh --rekey
    PYTHONHASHSEED=1 SCREEN_SCRIPT=reproduce/screening/rekey_kw_cache.py reproduce/screening/run_screen.sh

Lỗi: networkx_impl.get_types() trả list(set) nên thứ tự loại thực thể trong prompt minirag_query2kwd đổi theo
PYTHONHASHSEED; 460 bản ghi cache (b1 offline 180, b2 offline 180, đông lạnh V3 100) mang 460 khoá khác nhau, không
tiến trình nào tra lại được của tiến trình khác. operate.py nay sắp xếp TYPE_POOL khi bật MINIRAG_KW_CACHE.

--rekey: lưu bản gốc sang kw_cache_unstable_20260914.jsonl, rồi ghi lại đúng 100 lần rút của lượt đông lạnh V3
(dòng 361–460, sinh tuần tự theo thứ tự canary100.csv) dưới khoá sha256 của prompt đã sắp xếp. Không gọi LLM.
Luôn kiểm: dựng lại context V3 cho 100 câu canary chỉ từ cache, so chunk_ids + sha256 context + sha256 prompt với
V3 đông lạnh. Chạy dưới hai PYTHONHASHSEED khác nhau để chứng minh không còn phụ thuộc thứ tự băm.
"""
import asyncio, hashlib, json, os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import screen_variant as sv  # noqa: E402

ARCHIVE = os.path.join(sv.OUT, "cache", "kw_cache_unstable_20260914.jsonl")
FREEZE_LINES = (360, 460)


async def main():
    rekey = "--rekey" in sys.argv
    sys.argv = [a for a in sys.argv if a != "--rekey"]
    from gemini_common import build_rag, get_args
    from minirag.prompt import PROMPTS
    rag = build_rag(get_args("rekey_kw_cache"))
    rows = sv.question_set("canary")
    types, _ = await rag.chunk_entity_relation_graph.get_types()
    pool = sorted(types)
    print(f"PYTHONHASHSEED={os.environ.get('PYTHONHASHSEED', '(ngẫu nhiên)')} · {len(pool)} loại thực thể · "
          f"sha256 TYPE_POOL đã sắp: {hashlib.sha256(repr(pool).encode()).hexdigest()[:16]}", flush=True)

    if rekey:
        if not os.path.exists(ARCHIVE):
            shutil.copyfile(sv.KW_CACHE, ARCHIVE)
        old = [json.loads(l) for l in open(ARCHIVE, encoding="utf-8") if l.strip()]
        assert len(old) == 460 and len({r["prompt_sha256"] for r in old}) == 460, "bản gốc không đúng 460 khoá riêng"
        draws = old[FREEZE_LINES[0]:FREEZE_LINES[1]]
        assert len(draws) == len(rows) == 100
        with open(sv.KW_CACHE, "w", encoding="utf-8") as fh:
            for r, d in zip(rows, draws):
                prompt = PROMPTS["minirag_query2kwd"].format(query=r["Question"], TYPE_POOL=pool)
                key = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
                fh.write(json.dumps({"prompt_sha256": key, "result": d["result"]}, ensure_ascii=False) + "\n")
        print(f"đã ghi {len(rows)} lần rút của lượt đông lạnh V3 dưới khoá prompt đã sắp; bản gốc: {ARCHIVE}", flush=True)

    frozen = sv.load_jsonl(sv.FROZEN)
    ctx = await sv.contexts(rag, rows, "v3", cache_only=True)
    bad = [r["Question"] for r in rows if not sv.same_context(ctx[r["Question"]], frozen[r["Question"]])]
    for q in bad[:5]:
        print("  lệch:", q[:80], flush=True)
    print(f"V3 dựng lại từ cache: {len(rows) - len(bad)}/{len(rows)} câu khớp hash đông lạnh", flush=True)
    print("KIỂM DỰNG LẠI V3: " + ("ĐẠT" if not bad else "TRƯỢT"), flush=True)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    asyncio.run(main())
