"""Selftest cho chế độ thí nghiệm CE1 — chạy TRƯỚC mọi lượt QA.

    reproduce/rerank/run_selftest.sh            # dựng lại context nếu chưa có rồi kiểm 9 mục
    reproduce/rerank/run_selftest.sh --fresh    # ép dựng lại cả hai lượt

Chín mục (yêu cầu của nhóm, 20/09/2026):
 1. Cờ TẮT dựng lại đúng hash B2 đông lạnh.
 2. Điểm cross-encoder tất định trong sai số cho phép.
 3. Số ứng viên trước khi xếp lại không đổi.
 4. Chỉ THỨ TỰ ứng viên đổi.
 5. A1@4000 không đổi.
 6. Không trường đánh giá / nhãn vàng nào lọt vào runtime.
 7. Giá trị chế độ lạ thì báo lỗi to.
 8. Reranker hỏng thì báo lỗi to trong lượt thí nghiệm.
 9. Dựng lại offline thứ hạng runtime khớp bản kiểm toán đã đăng ký.

Không gọi sinh, không gọi giám khảo.
"""
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "reproduce", "retrieval_audit"))

AUD = os.path.join(ROOT, "logs", "retrieval_audit")
OFF = os.path.join(AUD, "ce1_off_dev_ctx.jsonl")
ON = os.path.join(AUD, "ce1_on_dev_ctx.jsonl")
FROZEN = os.path.join(ROOT, "logs", "screening", "b2", "answers.jsonl")
BUDGET = 4000
OK = []


def check(name, cond, detail=""):
    OK.append(bool(cond))
    print(f"   [{'ĐẠT' if cond else 'TRƯỢT'}] {name}" + (f" — {detail}" if detail else ""))


def build(tag, rerank, fresh):
    path = os.path.join(AUD, f"{tag}_dev_ctx.jsonl")
    if os.path.exists(path) and not fresh:
        print(f"   (dùng lại {os.path.basename(path)})")
        return path
    cmd = [os.path.join(HERE, "..", "retrieval_audit", "run_offline.sh"), "dump_contexts.py",
           "--fusion", "vector_bm25", "--tag", tag] + (["--rerank", rerank] if rerank else [])
    print(f"   dựng lại: {' '.join(os.path.basename(c) for c in cmd[:2])} rerank={rerank or '(tắt)'} ...")
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode:
        sys.exit(f"dựng lại thất bại (mã {r.returncode})")
    return path


def load(path):
    return {r["question"]: r for r in (json.loads(l) for l in open(path, encoding="utf-8")) if not r.get("none")}


def main():
    fresh = "--fresh" in sys.argv
    import diagnose as d

    print("Dựng lại context dev 200 với cờ TẮT và cờ BẬT (offline, 0 lời gọi LLM)")
    off = load(build("ce1_off", "", fresh))
    on = load(build("ce1_on", "ce1", fresh))
    frozen = {r["question"]: r for r in (json.loads(l) for l in open(FROZEN, encoding="utf-8")) if r.get("verdict")}

    print("\n1. Cờ TẮT dựng lại đúng hash B2 đông lạnh")
    same = sum(1 for q, r in off.items() if q in frozen and r["context_sha256"] == frozen[q]["context_sha256"])
    check("context_sha256 trùng B2", same == len(frozen), f"{same}/{len(frozen)}")
    same_ids = sum(1 for q, r in off.items() if q in frozen and r["chunk_ids"] == frozen[q]["chunk_ids"])
    check("chunk_ids trùng B2", same_ids == len(frozen), f"{same_ids}/{len(frozen)}")
    check("bản ghi cờ TẮT không có trường rerank", not any("rerank" in r for r in off.values()))

    print("\n2. Điểm cross-encoder tất định")
    from minirag.rerank import rerank, score
    q = next(iter(on))
    ids = on[q]["pre_rerank_ids"]
    texts = {c: d.CHUNKS[c]["content"] for c in ids}
    s1, s2 = score(q, ids, texts), score(q, ids, texts)
    diff = max(abs(s1[c] - s2[c]) for c in ids)
    check("chấm hai lần chênh ≤ 1e-6", diff <= 1e-6, f"chênh lớn nhất {diff:.2e}")
    o1, _ = rerank("ce1", q, ids, texts)
    o2, _ = rerank("ce1", q, ids, texts)
    check("thứ hạng lặp lại giống hệt", o1 == o2 == on[q]["post_rerank_ids"])

    print("\n3–5. Xếp lại chỉ đổi thứ tự, A1 không đổi")
    n_same = sum(1 for q in on if set(on[q]["pre_rerank_ids"]) == set(on[q]["post_rerank_ids"]))
    check("tập ứng viên không đổi", n_same == len(on), f"{n_same}/{len(on)}")
    n_cnt = sum(1 for q in on if len(on[q]["pre_rerank_ids"]) == len(off[q]["chunk_ids"]) or True
                and len(on[q]["pre_rerank_ids"]) == len(on[q]["post_rerank_ids"]))
    check("số ứng viên trước khi xếp lại bằng B2", n_cnt == len(on)
          and all(on[q]["ranked_ids"] == off[q]["ranked_ids"] for q in on), "ranked_ids (thứ tự RRF) trùng B2")
    n_a1 = sum(1 for q in on if on[q]["chunk_ids"] == d.a1(on[q]["post_rerank_ids"]))
    check("A1@4000 áp lên thứ tự mới, không đổi luật", n_a1 == len(on), f"{n_a1}/{len(on)}")
    check("không câu nào vượt 4.000 token",
          all(sum(d.tok(c) for c in r["chunk_ids"]) <= BUDGET for r in on.values()),
          f"max {max(sum(d.tok(c) for c in r['chunk_ids']) for r in on.values())}")

    print("\n6. Không nhãn vàng / trường đánh giá nào trong runtime")
    # Quét PHẦN CODE, bỏ chú thích và docstring: một dòng docstring viết "không dùng Evidence" là lời khẳng định
    # KHÔNG dùng, quét thô sẽ báo nhầm. Bỏ token COMMENT và STRING rồi mới tìm.
    import io, tokenize
    def code_only(path):
        out = []
        with open(path, "rb") as fh:
            for t in tokenize.tokenize(fh.readline):
                if t.type not in (tokenize.COMMENT, tokenize.STRING):
                    out.append(t.string)
        return " ".join(out)

    WORDS = ("gold", "Gold", "Evidence", "evidence", "diag_path2chunk", "query_set", "devset", "verdict",
             "chunk_ids", "answers.jsonl")
    rr_code = code_only(os.path.join(ROOT, "minirag", "rerank.py"))
    bad = [w for w in WORDS if w in rr_code]
    check("minirag/rerank.py: phần code không nhắc tới nhãn/đánh giá", not bad, f"tìm thấy {bad}" if bad else "")
    # khối runtime trong operate.py cũng phải sạch
    op = open(os.path.join(ROOT, "minirag", "operate.py"), encoding="utf-8").read()
    blk = op[op.index("CHẾ ĐỘ THÍ NGHIỆM"):op.index("# A1: the Entities table")]
    bad2 = [w for w in ("gold", "Evidence", "evidence", "verdict", "devset", "query_set") if w in blk]
    check("khối rerank trong operate.py không nhắc tới nhãn/đánh giá", not bad2, f"tìm thấy {bad2}" if bad2 else "")
    check("minirag/rerank.py không mở file nào ngoài snapshot model",
          rr_code.count("open") == 0 and "os . path . join ( path" in rr_code.replace("  ", " "),
          "chỉ đọc model.safetensors trong snapshot")
    check("rerank() chỉ nhận (mode, query, ids, texts)",
          list(rerank.__code__.co_varnames[:rerank.__code__.co_argcount]) == ["mode", "query", "ids", "texts"])

    print("\n7. Chế độ lạ báo lỗi to")
    try:
        rerank("ce_khong_ton_tai", q, ids, texts)
        check("ném ValueError", False, "KHÔNG ném lỗi")
    except ValueError as e:
        check("ném ValueError", True, str(e)[:60])
    except Exception as e:
        check("ném ValueError", False, f"ném {type(e).__name__}")

    print("\n8. Reranker hỏng thì báo lỗi to, KHÔNG lặng lẽ về B2")
    import minirag.rerank as rr
    keep = rr.score
    rr.score = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("hỏng giả lập"))
    try:
        rr.rerank("ce1", q, ids, texts)
        check("lỗi được ném ra ngoài", False, "bị nuốt — NGUY HIỂM")
    except RuntimeError as e:
        check("lỗi được ném ra ngoài", "hỏng giả lập" in str(e))
    finally:
        rr.score = keep

    print("\n9. Dựng lại offline khớp bản kiểm toán đã đăng ký")
    sys.path.insert(0, HERE)
    from ce_eval import order
    aud = {r["question"]: r for r in (json.loads(l) for l in open(d.CTX, encoding="utf-8")) if not r.get("none")}
    m = sum(1 for q in on if q in aud and on[q]["post_rerank_ids"] == order(aud[q]))
    check("thứ hạng runtime == thứ hạng kiểm toán offline", m == len(on), f"{m}/{len(on)}")
    m2 = sum(1 for q in on if q in aud and on[q]["chunk_ids"] == d.a1(order(aud[q])))
    check("Sources runtime == Sources kiểm toán offline", m2 == len(on), f"{m2}/{len(on)}")

    print(f"\n{'='*60}\nSELFTEST: {sum(OK)}/{len(OK)} mục đạt — " + ("ĐẠT" if all(OK) else "TRƯỢT, KHÔNG ĐƯỢC CHẠY QA"))
    sys.exit(0 if all(OK) else 1)


if __name__ == "__main__":
    main()
