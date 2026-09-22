"""Selftest cho chế độ ce1_lite — chạy TRƯỚC lượt canary của CE-lite.

    reproduce/rerank/run_selftest_celite.sh

Kiểm đúng những bất biến quan trọng của biến thể mới:
 1. N = 25 đóng cứng trong code, không đọc từ biến môi trường.
 2. Runtime chỉ chấm 25 ứng viên đầu; phần đuôi giữ nguyên thứ tự RRF.
 3. Thứ hạng runtime == thứ hạng CE-lite dựng offline (200/200).
 4. Sources runtime == Sources offline, A1@4000 không đổi, không câu nào vượt 4.000 token.
 5. Tập ứng viên không đổi.
 6. Chế độ lạ báo lỗi to; reranker hỏng báo lỗi to.
 7. Cờ TẮT vẫn dựng lại đúng hash B2 đông lạnh.

Không gọi sinh, không gọi giám khảo.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "reproduce", "retrieval_audit"))
sys.path.insert(0, HERE)

AUD = os.path.join(ROOT, "logs", "retrieval_audit")
OK = []


def check(name, cond, detail=""):
    OK.append(bool(cond))
    print(f"   [{'ĐẠT' if cond else 'TRƯỢT'}] {name}" + (f" — {detail}" if detail else ""))


def main():
    import diagnose as d
    from celite_eval import celite_order, N_PREFIX
    from minirag.rerank import MODES, N_PREFIX as RT_N, rerank

    lite = {r["question"]: r for r in (json.loads(l) for l in
                                       open(os.path.join(AUD, "ce1_lite_on_dev_ctx.jsonl"), encoding="utf-8"))
            if not r.get("none")}
    off = {r["question"]: r for r in (json.loads(l) for l in
                                      open(os.path.join(AUD, "ce1_off_dev_ctx.jsonl"), encoding="utf-8"))
           if not r.get("none")}
    frozen = {r["question"]: r for r in (json.loads(l) for l in
                                         open(os.path.join(ROOT, "logs", "screening", "b2", "answers.jsonl"),
                                              encoding="utf-8")) if r.get("verdict")}
    recs = {r["question"]: r for r in (json.loads(l) for l in open(d.CTX, encoding="utf-8")) if not r.get("none")}

    print("1. N = 25 đóng cứng")
    check("runtime N_PREFIX['ce1_lite'] == 25", RT_N["ce1_lite"] == 25, str(RT_N))
    check("bản đánh giá offline dùng cùng N", N_PREFIX == 25, str(N_PREFIX))
    src = open(os.path.join(ROOT, "minirag", "rerank.py"), encoding="utf-8").read()
    check("N không đọc từ biến môi trường", "N_PREFIX" in src and "environ" not in src.split("N_PREFIX")[1][:200])

    print("\n2. Chỉ 25 ứng viên đầu được xếp lại, đuôi giữ nguyên thứ tự RRF")
    tail_ok = sum(1 for q, r in lite.items()
                  if r["post_rerank_ids"][25:] == r["pre_rerank_ids"][25:])
    check("đuôi sau vị trí 25 y nguyên", tail_ok == len(lite), f"{tail_ok}/{len(lite)}")
    head_ok = sum(1 for q, r in lite.items()
                  if set(r["post_rerank_ids"][:25]) == set(r["pre_rerank_ids"][:25]))
    check("tiền tố chỉ bị hoán vị trong chính nó", head_ok == len(lite), f"{head_ok}/{len(lite)}")

    print("\n3–4. Runtime khớp bản dựng offline")
    m = sum(1 for q, r in lite.items() if q in recs and r["post_rerank_ids"] == celite_order(recs[q]))
    check("thứ hạng runtime == CE-lite offline", m == len(lite), f"{m}/{len(lite)}")
    m2 = sum(1 for q, r in lite.items() if q in recs and r["chunk_ids"] == d.a1(celite_order(recs[q])))
    check("Sources runtime == CE-lite offline", m2 == len(lite), f"{m2}/{len(lite)}")
    mx = max(sum(d.tok(c) for c in r["chunk_ids"]) for r in lite.values())
    check("không câu nào vượt 4.000 token", mx <= 4000, f"max {mx}")

    print("\n5. Tập ứng viên không đổi")
    same = sum(1 for q, r in lite.items() if set(r["pre_rerank_ids"]) == set(r["post_rerank_ids"]))
    check("tập ứng viên giữ nguyên", same == len(lite), f"{same}/{len(lite)}")
    rrf = sum(1 for q, r in lite.items() if q in off and r["ranked_ids"] == off[q]["ranked_ids"])
    check("thứ tự RRF đi vào trùng B2", rrf == len(lite), f"{rrf}/{len(lite)}")

    print("\n6. Báo lỗi to")
    q = next(iter(lite))
    ids = lite[q]["pre_rerank_ids"]
    texts = {c: d.CHUNKS[c]["content"] for c in ids}
    try:
        rerank("ce_khong_ton_tai", q, ids, texts)
        check("chế độ lạ ném ValueError", False, "KHÔNG ném")
    except ValueError:
        check("chế độ lạ ném ValueError", True)
    import minirag.rerank as rr
    keep = rr.score
    rr.score = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("hỏng giả lập"))
    try:
        rr.rerank("ce1_lite", q, ids, texts)
        check("lỗi reranker được ném ra", False, "bị nuốt — NGUY HIỂM")
    except RuntimeError as e:
        check("lỗi reranker được ném ra", "hỏng giả lập" in str(e))
    finally:
        rr.score = keep
    check("ce1_lite nằm trong MODES", "ce1_lite" in MODES, str(MODES))

    print("\n7. Cờ TẮT vẫn là B2 đông lạnh")
    s = sum(1 for q, r in off.items() if q in frozen and r["context_sha256"] == frozen[q]["context_sha256"])
    check("hash B2 trùng", s == len(frozen), f"{s}/{len(frozen)}")
    check("bản ghi cờ TẮT không có trường rerank", not any("rerank" in r for r in off.values()))

    print(f"\n{'=' * 60}\nSELFTEST ce1_lite: {sum(OK)}/{len(OK)} mục đạt — "
          + ("ĐẠT" if all(OK) else "TRƯỢT, KHÔNG ĐƯỢC CHẠY QA"))
    sys.exit(0 if all(OK) else 1)


if __name__ == "__main__":
    main()
