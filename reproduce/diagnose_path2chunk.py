"""Chẩn đoán bước chọn chunk của MiniRAG bằng nhãn Evidence -- KHÔNG sinh, KHÔNG chấm.

Hai câu hỏi:
  1. Lỗi path2chunk (operate.py:1207 chọn theo count_dict = điểm của ĐƯỜNG CUỐI,
     trong khi node_chunk_id cộng dồn mọi đường rồi bị bỏ; bản đúng nằm trong
     comment ở 1209) có đẩy chunk chứa đáp án ra khỏi context không?
  2. Điểm chunk có "vách" tách chunk đúng khỏi rác không -- tức cắt theo điểm
     thay vì theo số token cố định có khả thi không?

Nhãn đúng: mỗi chunk bắt đầu bằng "Time: YYYYMMDD_HH:MM"; cột Evidence ghi đúng
chuỗi đó. Đã kiểm 295/297 evidence (200 câu đầu) khớp đúng một chunk.
Evidence CHỈ dùng để chẩn đoán -- cơ chế lúc chạy không được nhìn nó (rò nhãn).

Cách đo: vá tạm path2chunk/kwd2chunk trong tiến trình này (không sửa operate.py).
Mỗi câu duyệt đồ thị MỘT lần, tính cả hai cách chọn; pipeline vẫn đi nhánh có lỗi
nên hành vi y hệt baseline. N câu đầu chạy thêm hàm gốc và assert trùng khớp.

    ./reproduce/run_diag_path2chunk.sh              # chạy (resume được)
    DIAG_REPORT_ONLY=1 python reproduce/diagnose_path2chunk.py --outputpath ...
"""
import asyncio, copy, csv, json, math, os, statistics as st, sys
import collections
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(_HERE)
sys.path.append(os.path.dirname(_HERE))

import minirag.operate as op  # noqa: E402
from minirag import QueryParam  # noqa: E402

A1_BUDGET = 4000     # mặc định max_token_for_text_unit, đúng mức các lượt Qwen 637 đã chạy
CHECK_FIRST = 3      # số câu đầu chạy kèm hàm gốc để assert bản sao trùng khớp
KEEP_TOP = 60        # lưu bao nhiêu chunk xếp hạng đầu để phân tích vách điểm

ORIG_P2C, ORIG_KWD = op.path2chunk, op.kwd2chunk
STASH, STATE = {}, {"check": False}


def split(s):
    return op.split_string_by_multi_markers(s, [op.GRAPH_FIELD_SEP])


# ---- bản sao nguyên văn operate.py:1125-1210, chỉ thêm biến `fixed` ----------
async def path2chunk_both(scored_edged_reasoning_path, knowledge_graph_inst,
                          pairs_append, query, max_chunks=5):
    already_node = {}
    fixed = {}
    for k, v in scored_edged_reasoning_path.items():
        node_chunk_id = None
        for pathtuple, scorelist in v["Path"].items():
            if pathtuple in pairs_append:
                use_edge = pairs_append[pathtuple]
                edge_datas = await asyncio.gather(
                    *[knowledge_graph_inst.get_edge(r[0], r[1]) for r in use_edge])
                text_units = [split(dp["source_id"]) for dp in edge_datas][0]
            else:
                use_edge = []
                text_units = []
            node_datas = await asyncio.gather(
                *[knowledge_graph_inst.get_node(pathtuple[0])])
            for dp in node_datas:
                text_units = text_units + split(dp["source_id"])
            node_datas = await asyncio.gather(
                *[knowledge_graph_inst.get_node(ents) for ents in pathtuple[1:]])
            if query is not None:
                for dp in node_datas:
                    text_units_node = split(dp["source_id"])
                    descriptionlist_node = split(dp["description"])
                    if descriptionlist_node[0] not in already_node.keys():
                        already_node[descriptionlist_node[0]] = None
                        if len(text_units_node) == len(descriptionlist_node):
                            if len(text_units_node) > 5:
                                max_ids = int(max(5, len(text_units_node) / 2))
                                idx = op.calculate_similarity(
                                    descriptionlist_node, query, k=max_ids)
                                text_units_node = [text_units_node[i] for i in idx]
                                already_node[descriptionlist_node[0]] = text_units_node
                    else:
                        text_units_node = already_node[descriptionlist_node[0]]
                    if text_units_node is not None:
                        text_units = text_units + text_units_node
            count_dict = Counter(text_units)
            total_score = scorelist[0] + scorelist[1] + 1
            for key, value in count_dict.items():
                count_dict[key] = value * total_score
            if node_chunk_id is None:
                node_chunk_id = count_dict
            else:
                node_chunk_id = node_chunk_id + count_dict
        v["Path"] = []
        if node_chunk_id is None:
            node_datas = await asyncio.gather(*[knowledge_graph_inst.get_node(k)])
            for dp in node_datas:
                count_dict = Counter(split(dp["source_id"]))
            for id in count_dict.most_common(max_chunks):
                v["Path"].append(id[0])
            fixed[k] = list(v["Path"])
        else:
            for id in count_dict.most_common(max_chunks):          # hành vi hiện tại (lỗi)
                v["Path"].append(id[0])
            fixed[k] = [i for i, _ in node_chunk_id.most_common(max_chunks)]  # bản sửa
    return scored_edged_reasoning_path, fixed


# ---- bản sao nguyên văn operate.py:1221-1250, trả về Counter điểm đầy đủ -------
def kwd_scores(ent_from_query_dict, chunks_ids):
    final_chunk = Counter()
    for key, list_of_dicts in ent_from_query_dict.items():
        total_id_scores = Counter()
        id_scores_list = []
        id_scores = {}
        for d in list_of_dicts:
            score = d["Score"] * 2 if d == list_of_dicts[0] else d["Score"]
            path = d["Path"]
            for id in path:
                if id == path[0] and id in chunks_ids:
                    score = score * 10
                id_scores[id] = id_scores.get(id, 0) + score
        id_scores_list.append(id_scores)
        for scores in id_scores_list:
            total_id_scores.update(scores)
        final_chunk = final_chunk + total_id_scores
    return final_chunk


async def patched_path2chunk(sep, kg, pairs_append, query, max_chunks=5):
    ref_in = copy.deepcopy(sep) if STATE["check"] else None
    ref_fix_in = copy.deepcopy(sep) if STATE["check"] else None
    out, fixed = await path2chunk_both(sep, kg, pairs_append, query, max_chunks)
    if STATE["check"]:
        ref = await ORIG_P2C(ref_in, kg, pairs_append, query, max_chunks)
        a = {k: v["Path"] for k, v in ref.items()}
        b = {k: v["Path"] for k, v in out.items()}
        assert a == b, "bản sao path2chunk LỆCH hàm gốc"
        # operate.py với MINIRAG_PATH2CHUNK_FIX=1 phải cho đúng `fixed` mà chẩn đoán đo,
        # nếu không thì lượt 637 sẽ chạy một thứ khác với thứ đã chẩn đoán.
        os.environ["MINIRAG_PATH2CHUNK_FIX"] = "1"
        try:
            reff = await ORIG_P2C(ref_fix_in, kg, pairs_append, query, max_chunks)
        finally:
            os.environ.pop("MINIRAG_PATH2CHUNK_FIX", None)
        assert {k: v["Path"] for k, v in reff.items()} == fixed, \
            "operate.py (PATH2CHUNK_FIX=1) LỆCH bản sửa trong chẩn đoán"
    STASH["out"], STASH["fixed"] = out, fixed
    return out


def patched_kwd2chunk(ent_from_query_dict, chunks_ids, chunk_nums):
    res = ORIG_KWD(ent_from_query_dict, chunks_ids, chunk_nums)
    buggy = kwd_scores(ent_from_query_dict, chunks_ids)
    if STATE["check"]:
        assert [i for i, _ in buggy.most_common(chunk_nums)] == res, \
            "bản sao kwd2chunk LỆCH hàm gốc"
    # scorednode2chunk (operate.py:1374) thay tên thực thể bằng CHÍNH object trong
    # scored_edged_reasoning_path -> dùng id() để lấy lại tên, rồi thay Path bằng bản sửa.
    name_of = {id(v): k for k, v in STASH["out"].items()}
    fixed_dict = {
        key: [{"Score": d["Score"], "Path": STASH["fixed"][name_of[id(d)]]} for d in lst]
        for key, lst in ent_from_query_dict.items()
    }
    fs = kwd_scores(fixed_dict, chunks_ids)
    if STATE["check"]:
        os.environ["MINIRAG_CHUNK_CUT"] = "knee"
        try:
            got = ORIG_KWD(fixed_dict, chunks_ids, chunk_nums)
        finally:
            os.environ.pop("MINIRAG_CHUNK_CUT", None)
        top = fs.most_common(chunk_nums)
        want = [i for i, _ in top[: op._knee_keep([sc for _, sc in top])]]
        assert got == want, "operate.py (CHUNK_CUT=knee) LỆCH phép cắt trong chẩn đoán"
    STASH.update(buggy=buggy, fixed_scores=fs,
                 chunks_ids=list(chunks_ids), chunk_nums=chunk_nums)
    return res


op.path2chunk, op.kwd2chunk = patched_path2chunk, patched_kwd2chunk


def summarize(scores, chunk_nums, gold, TOK):
    ranking = scores.most_common()
    rank = {cid: i + 1 for i, (cid, _) in enumerate(ranking)}
    final = [cid for cid, _ in ranking[:chunk_nums] if cid in TOK]   # use_text_units bỏ None
    kept, tok = [], 0
    for cid in final:                       # đúng ngữ nghĩa truncate_list_by_token_size
        tok += TOK[cid]
        if tok > A1_BUDGET:
            break
        kept.append(cid)
    return {
        "n_ranked": len(ranking), "final_n": len(final),
        "a1_n": len(kept), "a1_tok": sum(TOK[c] for c in kept),
        "gold_rank": [rank.get(g) for g in gold],
        "gold_in_final": [g in final for g in gold],
        "gold_in_a1": [g in kept for g in gold],
        "top": [[cid, round(float(s), 5), TOK.get(cid, 0), cid in gold]
                for cid, s in ranking[:KEEP_TOP]],
    }


async def run(args):
    from gemini_common import build_rag
    rag = build_rag(args)
    chunks = json.load(open(os.path.join(args.workingdir, "kv_store_text_chunks.json")))
    TOK = {cid: len(op.encode_string_by_tiktoken(c["content"])) for cid, c in chunks.items()}

    rows = list(csv.DictReader(open(args.questions, encoding="utf-8")))
    if args.limit:
        rows = rows[: args.limit]
    out_path = args.outputpath
    done = set()
    if os.path.exists(out_path):
        done = {json.loads(l)["question"] for l in open(out_path, encoding="utf-8") if l.strip()}
    todo = [r for r in rows if r["Question"] not in done]
    print(f"chẩn đoán: {len(todo)} câu còn lại / {len(rows)}  (đã có {len(done)})")

    failed = 0
    with open(out_path, "a", encoding="utf-8") as fh:
        for i, r in enumerate(todo, 1):
            q = r["Question"]
            evs = [e.strip() for e in r.get("Evidence", "").split("<and>") if e.strip()]
            gold = sorted({cid for cid, c in chunks.items() for e in evs if e in c["content"]})
            STASH.clear()
            STATE["check"] = len(done) + i <= CHECK_FIRST
            try:
                ctx = await rag.aquery(q, param=QueryParam(mode="mini", only_need_context=True))
            except AssertionError:
                raise
            except Exception as e:
                print(f"  lỗi câu {i}: {type(e).__name__}: {e}")
                failed += 1
                continue                    # không ghi -> lần sau resume đo lại
            rec = {"question": q, "type": r.get("Type", "?"), "evidence": evs,
                   "gold": gold, "context_none": not isinstance(ctx, str),
                   "reached_kwd2chunk": "buggy" in STASH}
            if "buggy" in STASH:
                cn = STASH["chunk_nums"]
                rec["n_entities"] = len(STASH["out"])
                rec["vector_gold_hit"] = [g in STASH["chunks_ids"] for g in gold]
                rec["buggy"] = summarize(STASH["buggy"], cn, gold, TOK)
                rec["fixed"] = summarize(STASH["fixed_scores"], cn, gold, TOK)
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            if STATE["check"]:
                print(f"  câu {len(done)+i}: bản sao trùng khớp hàm gốc ✓")
            if i % 10 == 0:
                print(f"  {i}/{len(todo)}")
    return failed


# ------------------------------------------------------------------------------
def pct(a, b):
    return f"{100*a/b:5.1f}%" if b else "   — "


def exact_mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n)


def knee_keep(top):
    """Đúng hàm operate._knee_keep, áp trên 30 chunk đầu (chunk_nums)."""
    return op._knee_keep([t[1] for t in top[:30]])


def report(path):
    recs = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    ok = [r for r in recs if r.get("reached_kwd2chunk") and r["gold"]]
    print(f"\n=== Chẩn đoán chọn chunk · {len(recs)} câu · A1@{A1_BUDGET} ===")
    print(f"context rỗng (None)           : {sum(r['context_none'] for r in recs)}")
    print(f"không tới được kwd2chunk      : {sum(not r.get('reached_kwd2chunk') for r in recs)}")
    print(f"evidence không khớp chunk nào : {sum(not r['gold'] for r in recs)}")
    print(f"dùng để phân tích             : {len(ok)} câu, "
          f"{sum(len(r['gold']) for r in ok)} chunk đáp án")

    def block(label, sel):
        rs = [r for r in ok if sel(r)]
        if not rs:
            return
        G = sum(len(r["gold"]) for r in rs)
        print(f"\n--- {label}: {len(rs)} câu, {G} chunk đáp án ---")
        print(f"{'':34s}{'có lỗi (hiện tại)':>20s}{'đã sửa':>12s}")
        for name, fn in (
            ("chunk đáp án có trong xếp hạng", lambda v: sum(x is not None for x in v["gold_rank"])),
            ("chunk đáp án trong 30 chunk",    lambda v: sum(v["gold_in_final"])),
            ("chunk đáp án trong A1@4000",     lambda v: sum(v["gold_in_a1"])),
        ):
            print(f"{name:34s}{pct(sum(fn(r['buggy']) for r in rs), G):>20s}"
                  f"{pct(sum(fn(r['fixed']) for r in rs), G):>12s}")
        for var in ("buggy", "fixed"):
            rs_all = sum(all(r[var]["gold_in_a1"]) for r in rs)
            ranks = [x for r in rs for x in r[var]["gold_rank"] if x is not None]
            mrr = st.mean([1 / min([x for x in r[var]["gold_rank"] if x] or [math.inf])
                           for r in rs])
            print(f"  [{'có lỗi' if var=='buggy' else 'đã sửa'}] đủ MỌI chunk đáp án trong A1: "
                  f"{pct(rs_all, len(rs))} · hạng trung vị {st.median(ranks) if ranks else '—'}"
                  f" · MRR {mrr:.3f} · token A1 trung vị {st.median(r[var]['a1_tok'] for r in rs):.0f}")
        b = sum(all(r["fixed"]["gold_in_a1"]) and not all(r["buggy"]["gold_in_a1"]) for r in rs)
        c = sum(all(r["buggy"]["gold_in_a1"]) and not all(r["fixed"]["gold_in_a1"]) for r in rs)
        print(f"  McNemar (đủ đáp án trong A1): sửa lỗi làm {b} câu lên / {c} câu xuống, "
              f"p = {exact_mcnemar(b, c):.3f}")

    block("TỔNG", lambda r: True)
    for t in ("Single", "Multi", "Null"):
        block(t, lambda r, t=t: r["type"] == t)

    G = sum(len(r["gold"]) for r in ok)
    print(f"\n--- tham chiếu ---")
    print(f"chunk đáp án nằm trong top-30 vector thuần (chunks_vdb): "
          f"{pct(sum(sum(r['vector_gold_hit']) for r in ok), G)}")

    print(f"\n--- vách điểm (bản đã sửa · cắt tại chỗ điểm tụt mạnh nhất · A1@{A1_BUDGET} làm trần) ---")
    kk, hit, toks = [], 0, []
    for r in ok:
        k = knee_keep(r["fixed"]["top"])
        kept, tok = [], 0
        for cid, _, t, _g in r["fixed"]["top"][:k]:
            tok += t
            if tok > A1_BUDGET:
                break
            kept.append(cid)
        kk.append(len(kept))
        toks.append(sum(t for cid, _, t, _g in r["fixed"]["top"] if cid in kept))
        hit += sum(g in kept for g in r["gold"])
    print(f"giữ trung vị {st.median(kk)} chunk · token Sources trung vị {st.median(toks):.0f} · "
          f"chunk đáp án giữ được {pct(hit, G)}")
    print(f"phân bố số chunk giữ: {dict(sorted(collections.Counter(kk).items()))}")
    print("(nhìn trên dev -- quy tắc đã chốt trước; phép thử sạch là 437 câu ngoài dev)")


def main():
    from gemini_common import get_args
    args = get_args("Chẩn đoán path2chunk / kwd2chunk bằng Evidence")
    if os.environ.get("DIAG_REPORT_ONLY"):
        return report(args.outputpath)
    try:
        failed = asyncio.run(run(args))
    except AssertionError as e:
        print(f"DỪNG: {e}")
        sys.exit(2)
    report(args.outputpath)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
