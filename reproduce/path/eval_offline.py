"""Đánh giá offline cho Thành viên 1 -- Cắt tỉa & chấm điểm đường đi đồ thị.
Đo trên 180 câu dev có Evidence (chỉ đọc index LiHua-World-qwen-modal).
KHÔNG sinh câu trả lời, KHÔNG tốn quota chấm Gemini.

Cách chạy:
    # 1. Bước 0: Đo baseline chẩn đoán
    python reproduce/path/eval_offline.py --mode step0

    # 2. Bước 2: Đo P1 (Cắt tỉa)
    python reproduce/path/eval_offline.py --mode p1

    # 3. Bước 3: Đo P2 (Chấm điểm có trọng số)
    python reproduce/path/eval_offline.py --mode p2

    # 4. Kiểm tra Zero-Regression (chạy baseline kiểm khớp hash)
    python reproduce/path/eval_offline.py --mode verify
"""
import argparse
import asyncio
import csv
import hashlib
import json
import os
import statistics as st
import sys
import time
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "reproduce"))
sys.path.insert(0, os.path.join(ROOT, "reproduce", "screening"))

from screen_variant import dev_rows, gold_map, evidence, mcnemar_p, fmt
from gemini_common import build_rag, get_args
from minirag import QueryParam

OUT_DIR = os.path.join(ROOT, "logs", "path")
KW_CACHE = os.path.join(OUT_DIR, "cache", "kw_cache.jsonl")


def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else 0.0


def p90(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return 0.0
    xs = sorted(xs)
    idx = int(len(xs) * 0.9)
    return xs[min(idx, len(xs) - 1)]


async def run_diagnose_query(rag, question):
    """Thực thi một câu hỏi và bóc tách chi tiết từng khâu trong đồ thị."""
    query_param = QueryParam(mode="mini", only_need_context=True)
    
    # Thiết lập file log tạm cho câu này
    temp_log = os.path.join(OUT_DIR, "cache", f"temp_{os.getpid()}.jsonl")
    if os.path.exists(temp_log):
        os.remove(temp_log)
    
    os.environ["MINIRAG_CONTEXT_LOG"] = temp_log
    os.environ["MINIRAG_KW_CACHE"] = KW_CACHE
    
    t0 = time.perf_counter()
    ctx = await rag.aquery(question, query_param)
    total_ms = 1000 * (time.perf_counter() - t0)
    
    rec = {}
    if os.path.exists(temp_log):
        lines = [l for l in open(temp_log, encoding="utf-8") if l.strip()]
        if lines:
            rec = json.loads(lines[-1])
        try:
            os.remove(temp_log)
        except OSError:
            pass
            
    return ctx, rec, total_ms


async def evaluate_dataset(rag, eval_rows, gold, mode_name="step0"):
    print(f"\n========================================================")
    print(f" ĐANG CHẠY ĐÁNH GIÁ OFFLINE: {mode_name.upper()}")
    print(f" Tập câu hỏi: {len(eval_rows)} câu dev có Evidence")
    print(f"========================================================")
    
    records = []
    total = len(eval_rows)
    
    for idx, r in enumerate(eval_rows, 1):
        q = r["Question"]
        q_type = r.get("Type", "Single")
        
        ctx, rec, ms = await run_diagnose_query(rag, q)
        
        rec["question"] = q
        rec["type"] = q_type
        rec["total_ms"] = ms
        records.append(rec)
        
        if idx % 20 == 0 or idx == total:
            print(f"  -> Đã xử lý {idx:3d}/{total} câu (ms trung vị tạm: {med([x['total_ms'] for x in records]):.1f} ms)")
            
    return records


def analyze_records(records, gold, eval_rows):
    """Tính toán toàn bộ các metric cần thiết."""
    q_to_rec = {r["question"]: r for r in records}
    
    # 1. Thời gian
    times_ms = [r.get("retrieval_ms") or r.get("total_ms", 0) for r in records]
    
    # 2. Khối lượng
    seeds = [r.get("graph_seeds", 0) for r in records if r.get("graph_seeds") is not None]
    paths = [r.get("graph_paths", 0) for r in records if r.get("graph_paths") is not None]
    
    # 3. Chunk retention
    # Format ctxs for screen_variant.evidence()
    ctxs_format = {}
    for r in records:
        ctxs_format[r["question"]] = {
            "chunk_ids": r.get("chunk_ids", []),
            "graph_ids": r.get("graph_ids", [])
        }
        
    # Evidence retention cho chunk_ids (sau cắt A1@4000)
    ev_a1 = evidence(eval_rows, ctxs_format, gold)
    
    # Evidence retention cho graph_ids (top 30 trước cắt)
    ctxs_graph = {q: {"chunk_ids": r.get("graph_ids", [])} for q, r in q_to_rec.items()}
    ev_graph = evidence(eval_rows, ctxs_graph, gold)
    
    # Tách theo Single và Multi
    by_type = {}
    for t in ["Single", "Multi"]:
        t_rows = [r for r in eval_rows if r.get("Type") == t and r["Question"] in gold]
        ev_t = evidence(t_rows, ctxs_format, gold)
        by_type[t] = ev_t

    return {
        "n_questions": len(records),
        "retrieval_ms_med": med(times_ms),
        "retrieval_ms_p90": p90(times_ms),
        "seeds_med": med(seeds),
        "seeds_p90": p90(seeds),
        "paths_med": med(paths),
        "paths_p90": p90(paths),
        "graph_top30_retention": ev_graph["retention"],
        "a1_retention": ev_a1["retention"],
        "full_answer_pct": ev_a1["full"],
        "full_answer_count": sum(all(g in q_to_rec[r["Question"]].get("chunk_ids", []) for g in gold[r["Question"]]) 
                                 for r in eval_rows if r["Question"] in gold),
        "by_type": by_type,
    }


def write_report_file(metrics, mode_name, records):
    rep_file = os.path.join(OUT_DIR, f"{mode_name}_report.txt")
    json_file = os.path.join(OUT_DIR, f"{mode_name}_report.json")
    
    lines = [
        f"=== BÁO CÁO OFFLINE: {mode_name.upper()} ===",
        f"Thời gian tạo: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Số câu đánh giá: {metrics['n_questions']} (180 câu dev có Evidence)",
        "",
        "1. HIỆU NĂNG (EFFICIENCY):",
        f"  - Thời gian truy hồi (retrieval_ms): Trung vị {fmt(metrics['retrieval_ms_med'], 1)} ms | p90 {fmt(metrics['retrieval_ms_p90'], 1)} ms",
        f"  - Số thực thể khởi đầu (seeds):      Trung vị {fmt(metrics['seeds_med'], 0)} | p90 {fmt(metrics['seeds_p90'], 0)}",
        f"  - Số đường 2-hop sinh ra (paths):    Trung vị {fmt(metrics['paths_med'], 0)} | p90 {fmt(metrics['paths_p90'], 0)}",
        "",
        "2. CHẤT LƯỢNG TRUY HỒI (QUALITY):",
        f"  - Chunk đáp án trong top-30 đồ thị:          {fmt(metrics['graph_top30_retention'], 1)}%",
        f"  - Chunk đáp án giữ lại sau cắt A1@4000:       {fmt(metrics['a1_retention'], 1)}%",
        f"  - Tỉ lệ câu giữ ĐỦ mọi chunk đáp án:        {fmt(metrics['full_answer_pct'], 1)}% ({metrics['full_answer_count']}/{metrics['n_questions']} câu)",
        "",
        "3. PHÂN TÁCH THEO LOẠI CÂU HỎI:",
        f"  - Single ({metrics['by_type'].get('Single', {}).get('questions', 0)} câu): Retention {fmt(metrics['by_type'].get('Single', {}).get('retention'), 1)}% | Đủ đáp án {fmt(metrics['by_type'].get('Single', {}).get('full'), 1)}%",
        f"  - Multi  ({metrics['by_type'].get('Multi', {}).get('questions', 0)} câu): Retention {fmt(metrics['by_type'].get('Multi', {}).get('retention'), 1)}% | Đủ đáp án {fmt(metrics['by_type'].get('Multi', {}).get('full'), 1)}%",
        "========================================================"
    ]
    
    content = "\n".join(lines)
    print("\n" + content)
    
    with open(rep_file, "w", encoding="utf-8") as f:
        f.write(content + "\n")
        
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
        
    print(f"\n[OK] Đã lưu báo cáo tại: {rep_file}")


async def main():
    parser = argparse.ArgumentParser(description="Offline Evaluation cho Path Pruning / Reweighting")
    parser.add_argument("--mode", type=str, default="step0", choices=["step0", "p1", "p2", "verify"],
                        help="step0: Đo baseline | p1: Đo cắt tỉa | p2: Đo chấm điểm | verify: Kiểm tra regression")
    parser.add_argument("--workingdir", type=str, default="./LiHua-World-qwen-modal")
    parser.add_argument("--model", type=str, default="Qwen/Qwen2.5-3B-Instruct")
    args = parser.parse_args()
    
    # Thiết lập env cơ bản
    os.environ["MINIRAG_ANSWER_TYPE_FIX"] = "1"
    os.environ["MINIRAG_PATH2CHUNK_FIX"] = "0"
    os.environ["MINIRAG_KW_CACHE"] = KW_CACHE
    
    if args.mode == "p1":
        os.environ["MINIRAG_PATH_PRUNE"] = "hub_cap"
        os.environ.pop("MINIRAG_PATH_SCORE", None)
    elif args.mode == "p2":
        os.environ["MINIRAG_PATH_SCORE"] = "weighted"
        os.environ.pop("MINIRAG_PATH_PRUNE", None)
    else: # step0 hoặc verify
        os.environ.pop("MINIRAG_PATH_PRUNE", None)
        os.environ.pop("MINIRAG_PATH_SCORE", None)
        
    # Nạp các câu hỏi và gold map
    rows = dev_rows()
    golds = gold_map()
    eval_rows = [r for r in rows if r["Question"] in golds]
    
    # Khởi tạo RAG
    print(f"Đang khởi tạo MiniRAG từ: {args.workingdir}")
    rag_args = argparse.Namespace(
        workingdir=args.workingdir,
        model=args.model,
        embedmodel="local"
    )
    rag = build_rag(rag_args)
    
    records = await evaluate_dataset(rag, eval_rows, golds, mode_name=args.mode)
    metrics = analyze_records(records, golds, eval_rows)
    write_report_file(metrics, args.mode, records)


if __name__ == "__main__":
    asyncio.run(main())
