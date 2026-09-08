"""Automated Experiment Runner (HD1) for MiniRAG.

Executes end-to-end experiment pipeline:
Config / Args -> MiniRAG Query -> Retrieve Evidence -> Evaluate (EM/F1 + Judge LLM) -> HD-Schema results.json + failed_queries.csv

Usage:
    python reproduce/run_eval_demo.py --limit 5
    python reproduce/run_eval_demo.py --questions ./logs/devset.csv --topk 60
"""

import argparse
import asyncio
import csv
import datetime
import io
import json
import os
import re
import sys
import time
from typing import Any, Dict, List

# Setup paths
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.append(_REPO_ROOT)
if _HERE not in sys.path:
    sys.path.append(_HERE)

from dotenv import load_dotenv
load_dotenv(os.path.join(_REPO_ROOT, ".env"))

import pandas as pd
from minirag import MiniRAG, QueryParam
from gemini_common import build_rag, build_query_param
from minirag.llm.gemini import gemini_complete_if_cache

JUDGE_PROMPT = """You are grading a question-answering system.

Question: {question}
Gold answer: {gold}
System answer: {pred}

Reply with exactly one word:
- "accurate" if the system answer conveys the gold answer. Wording may differ;
  a more specific but consistent answer still counts (gold "bottle", answer
  "water bottle" -> accurate).
- "error" if the system answer asserts something that contradicts the gold
  answer, without acknowledging any uncertainty.
- "neither" if the system answer says it does not know, refuses to answer, or
  is off-topic.
"""


def parse_args():
    parser = argparse.ArgumentParser(description="MiniRAG Automated Experiment Runner (HD1)")
    parser.add_argument("--model", type=str, default="gemini-flash-lite-latest",
                        help="LLM model for answering queries")
    parser.add_argument("--embedmodel", type=str, default="local",
                        help='Embedding model: "local" (MiniLM-L6-v2) or Gemini embedding')
    parser.add_argument("--workingdir", type=str, default="./LiHua-World",
                        help="Working directory containing indexed graph")
    parser.add_argument("--questions", type=str, default="",
                        help="Specific questions CSV path (e.g., ./logs/devset.csv)")
    parser.add_argument("--querypath", type=str, default="./dataset/LiHua-World/qa/query_set.csv",
                        help="Default query set path if --questions is not set")
    parser.add_argument("--mode", type=str, default="mini", help="Retrieval mode: mini | light | naive")
    parser.add_argument("--topk", type=int, default=60, help="top_k parameter for retrieval")
    parser.add_argument("--maxtokentextunit", type=int, default=4000, help="max_token_for_text_unit")
    parser.add_argument("--responsetype", type=str, default="Multiple Paragraphs")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of queries (0 = all)")
    parser.add_argument("--judge_model", type=str, default="gemini-flash-lite-latest")
    parser.add_argument("--judge_repeats", type=int, default=3, help="Number of judging passes")
    parser.add_argument("--force", action="store_true", help="Force rerun and overwrite existing results instead of resuming")
    parser.add_argument("--output_json", type=str, default="./logs/results.json",
                        help="Output JSON file path (HD-Schema)")
    parser.add_argument("--output_failed_csv", type=str, default="./logs/failed_queries.csv",
                        help="Output CSV for failed queries")
    return parser.parse_args()


# =========================================================================
# EVALUATION UTILITIES
# =========================================================================
def calculate_exact_match(prediction: str, ground_truth: str) -> int:
    """Exact Match (EM): 1 if normalized strings match completely, else 0."""
    pred_clean = str(prediction).strip().lower()
    gt_clean = str(ground_truth).strip().lower()
    return 1 if pred_clean == gt_clean else 0


def calculate_token_f1(prediction: str, ground_truth: str) -> float:
    """Token-level F1 score between prediction and ground truth."""
    pred_tokens = str(prediction).strip().lower().split()
    gt_tokens = str(ground_truth).strip().lower().split()
    if not pred_tokens or not gt_tokens:
        return 1.0 if pred_tokens == gt_tokens else 0.0
    
    common = set(pred_tokens) & set(gt_tokens)
    num_same = len(common)
    if num_same == 0:
        return 0.0
    
    precision = num_same / len(pred_tokens)
    recall = num_same / len(gt_tokens)
    return round((2 * precision * recall) / (precision + recall), 4)


async def judge_query_single_pass(model: str, question: str, gold: str, pred: str) -> str:
    """Run one judge pass using Gemini."""
    prompt = JUDGE_PROMPT.format(question=question, gold=gold, pred=pred)
    try:
        verdict = await gemini_complete_if_cache(model, prompt)
    except Exception as e:
        print(f"  [Judge Error]: {e}")
        return "neither"
    verdict = (verdict or "").strip().lower()
    for label in ("accurate", "error", "neither"):
        if label in verdict:
            return label
    return "neither"


def run_judge_eval(judge_model: str, question: str, gold: str, pred: str, repeats: int = 3) -> List[str]:
    """Run N repeats of LLM-as-a-judge evaluation."""
    if not gold or not pred or pred.startswith("ERROR:"):
        return ["error"] * repeats

    async def _run_all():
        tasks = [
            judge_query_single_pass(judge_model, question, gold, pred)
            for _ in range(repeats)
        ]
        return await asyncio.gather(*tasks)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # In interactive or already running loop
            import nest_asyncio
            nest_asyncio.apply()
        return loop.run_until_complete(_run_all())
    except Exception:
        return asyncio.run(_run_all())


def extract_retrieved_evidence(context_str: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Extract structured sources / chunks from MiniRAG context string."""
    if not context_str:
        return []
    m = re.search(r"-----Sources-----\s*```csv\s*(.*?)```", context_str, re.S)
    if not m:
        return []
    try:
        rows = list(csv.DictReader(io.StringIO(m.group(1).strip())))
        chunks = []
        for idx, r in enumerate(rows[:limit]):
            content = (r.get("content") or "").strip()
            if content:
                chunks.append({
                    "rank": idx + 1,
                    "chunk_id": f"chunk_{idx+1}",
                    "doc_name": r.get("doc_name", ""),
                    "content": content[:300] + ("..." if len(content) > 300 else ""),
                    "score": 1.0 / (idx + 1)
                })
        return chunks
    except Exception:
        return []


# =========================================================================
# MAIN EXPERIMENT RUNNER
# =========================================================================
def main():
    args = parse_args()

    # Determine paths
    query_file_path = args.questions if args.questions else args.querypath
    if not os.path.exists(query_file_path):
        print(f"[LỖI]: Không tìm thấy file câu hỏi tại {query_file_path}")
        sys.exit(1)

    os.makedirs(os.path.dirname(args.output_json) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(args.output_failed_csv) or ".", exist_ok=True)

    print("=" * 60)
    print("🚀 MINIRAG AUTOMATED EXPERIMENT RUNNER (HD1)")
    print("=" * 60)
    print(f"• Dataset:        {query_file_path}")
    print(f"• Working Dir:    {args.workingdir}")
    print(f"• LLM Model:      {args.model}")
    print(f"• Embedding:      {args.embedmodel}")
    print(f"• Retrieval Mode: {args.mode} (top_k={args.topk})")
    print(f"• Output JSON:    {args.output_json} (HD-Schema)")
    print(f"• Output Failed:  {args.output_failed_csv}")
    print("=" * 60)

    # Initialize MiniRAG
    print("\n--- [1/4] Đang khởi tạo hệ thống MiniRAG ---")
    try:
        rag = build_rag(args)
    except Exception as e:
        print(f"[LỖI KHỞI TẠO]: {e}")
        sys.exit(1)

    qparam = build_query_param(args)
    qparam_context = QueryParam(
        mode=args.mode,
        top_k=args.topk,
        max_token_for_text_unit=args.maxtokentextunit,
        only_need_context=True
    )

    # Read Dataset
    print(f"\n--- [2/4] Đọc dataset từ {query_file_path} ---")
    df_queries = pd.read_csv(query_file_path)
    df_queries.columns = [str(c).encode('utf-8').decode('utf-8-sig').strip().lower() for c in df_queries.columns]

    # Map column names
    col_q = next((c for c in df_queries.columns if any(k in c for k in ["question", "query", "prompt"])), None)
    col_gt = next((c for c in df_queries.columns if any(k in c for k in ["gold", "ground", "answer", "truth"])), None)
    col_type = next((c for c in df_queries.columns if "type" in c), None)

    if not col_q:
        print("[LỖI]: Không tìm thấy cột chứa câu hỏi (Question / Query)!")
        sys.exit(1)

    if args.limit and args.limit > 0:
        df_queries = df_queries.iloc[:args.limit]

    total_queries = len(df_queries)
    print(f"-> Số lượng câu hỏi sẽ chạy: {total_queries}")

    # Resume Checkpoint if output_json exists
    results_records = []
    failed_queries = []
    processed_q_ids = set()

    if not args.force and os.path.exists(args.output_json):
        try:
            with open(args.output_json, "r", encoding="utf-8") as f:
                saved_data = json.load(f)
                if isinstance(saved_data, dict) and "results" in saved_data:
                    results_records = saved_data["results"]
                    processed_q_ids = {r.get("query_id") for r in results_records}
                    print(f"-> Phát hiện checkpoint: Đã hoàn thành {len(processed_q_ids)} câu trước đó.")
        except Exception:
            pass

    # Experiment Metadata for HD-Schema
    exp_id = f"EXP_{args.model.upper()}_{args.mode.upper()}_TOPK{args.topk}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Main Execution Loop
    print("\n--- [3/4] Bắt đầu chạy truy xuất, sinh câu trả lời & chấm điểm ---")
    start_time_all = time.time()

    for idx, row in df_queries.iterrows():
        q_id = str(row.get("query_id", f"q_{idx}"))
        if q_id in processed_q_ids:
            continue

        query_text = str(row.get(col_q, "")).strip()
        if not query_text or query_text.lower() == "nan":
            continue

        ground_truth = str(row.get(col_gt, "")).strip() if col_gt else ""
        query_type = str(row.get(col_type, "Unknown")).strip() if col_type else "Unknown"

        print(f"\n[{len(results_records) + 1}/{total_queries}] Query ({query_type}): \"{query_text}\"")
        
        # 1. Retrieve Context & Evidence
        context_str = ""
        try:
            context_str = rag.query(query_text, param=qparam_context) or ""
        except Exception:
            pass
        retrieved_evidence = extract_retrieved_evidence(context_str)

        # 2. Query & Generate Answer
        t0 = time.time()
        try:
            generated_answer = rag.query(query_text, param=qparam)
            generated_answer = str(generated_answer).strip() if generated_answer else ""
        except Exception as e:
            print(f"  [Lỗi MiniRAG Query]: {e}")
            generated_answer = f"ERROR: {e}"
        latency = round(time.time() - t0, 3)

        # 3. Compute Metrics & Judge Passes
        em = calculate_exact_match(generated_answer, ground_truth)
        f1 = calculate_token_f1(generated_answer, ground_truth)
        judge_passes = run_judge_eval(args.judge_model, query_text, ground_truth, generated_answer, repeats=args.judge_repeats)
        
        # Final Verdict (majority vote)
        pass_counts = pd.Series(judge_passes).value_counts()
        final_verdict = pass_counts.index[0] if len(pass_counts) > 0 else "neither"
        is_correct = (final_verdict == "accurate") or (em == 1) or (f1 >= 0.5)

        print(f"  -> Generated: \"{generated_answer}\"")
        print(f"  -> Verdict: {final_verdict} (passes={judge_passes}) | EM={em} | F1={f1} | Latency={latency}s")

        # 4. Form Log Entry adhering to HD-Schema
        log_entry = {
            "query_id": q_id,
            "query": query_text,
            "query_type": query_type,
            "ground_truth": ground_truth,
            "generated_answer": generated_answer,
            "is_correct": bool(is_correct),
            "retrieved_evidence": retrieved_evidence,
            "evaluation": {
                "exact_match": em,
                "token_f1": f1,
                "judge_passes": judge_passes,
                "final_verdict": final_verdict
            },
            "performance": {
                "latency_seconds": latency,
                "input_tokens": len(query_text.split()),
                "output_tokens": len(generated_answer.split())
            },
            "failure_analysis": {
                "stage": None,
                "error_type": None,
                "note": ""
            }
        }
        results_records.append(log_entry)

        # Collect failed query for Tài's task
        if not is_correct:
            failed_queries.append({
                "query_id": q_id,
                "query": query_text,
                "query_type": query_type,
                "ground_truth": ground_truth,
                "generated_answer": generated_answer,
                "final_verdict": final_verdict,
                "latency_seconds": latency
            })

        # Summary calculation
        acc_count = sum(1 for r in results_records if r.get("is_correct"))
        err_count = sum(1 for r in results_records if r.get("evaluation", {}).get("final_verdict") == "error")
        neither_count = len(results_records) - acc_count - err_count

        summary_metrics = {
            "total_queries": len(results_records),
            "accuracy": round((acc_count / len(results_records)) * 100, 2) if results_records else 0.0,
            "error_rate": round((err_count / len(results_records)) * 100, 2) if results_records else 0.0,
            "neither_rate": round((neither_count / len(results_records)) * 100, 2) if results_records else 0.0,
            "avg_exact_match": round(float(pd.Series([r["evaluation"]["exact_match"] for r in results_records]).mean()), 4),
            "avg_token_f1": round(float(pd.Series([r["evaluation"]["token_f1"] for r in results_records]).mean()), 4),
            "avg_latency_seconds": round(float(pd.Series([r["performance"]["latency_seconds"] for r in results_records]).mean()), 3)
        }

        # Checkpoint to JSON (HD-Schema)
        output_payload = {
            "experiment_id": exp_id,
            "timestamp": datetime.datetime.now().isoformat(),
            "config": {
                "corpus": "LiHua-World",
                "working_dir": args.workingdir,
                "llm_model": args.model,
                "embedding_model": args.embedmodel,
                "retrieval_mode": args.mode,
                "top_k": args.topk,
                "judge_model": args.judge_model,
                "judge_repeats": args.judge_repeats
            },
            "summary_metrics": summary_metrics,
            "results": results_records
        }

        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(output_payload, f, ensure_ascii=False, indent=2)

    # Final Export of Failed Queries CSV
    if failed_queries:
        df_failed = pd.DataFrame(failed_queries)
        df_failed.to_csv(args.output_failed_csv, index=False, encoding="utf-8")
        print(f"\n-> Đã lưu {len(failed_queries)} câu lỗi vào {args.output_failed_csv}")

    total_time = round(time.time() - start_time_all, 2)
    print("\n" + "=" * 60)
    print("✅ HOÀN THÀNH THỰC NGHIỆM")
    print(f"• Tổng thời gian: {total_time}s")
    print(f"• Kết quả JSON:   {args.output_json}")
    print(f"• Dataset lỗi:    {args.output_failed_csv}")
    print("=" * 60)


if __name__ == "__main__":
    main()