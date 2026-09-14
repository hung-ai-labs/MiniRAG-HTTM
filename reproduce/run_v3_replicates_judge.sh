#!/bin/zsh
# Chấm hai lượt lặp V3 ngay khi QA của lượt đó xong (giám khảo nhẹ, chạy song song với QA lượt
# sau được; chỉ QA mới không được chạy song song). Mỗi lượt so với baseline qwen637_fix và với
# V3 gốc, rồi tổng hợp cả 3 lượt V3.
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
export PYTHONUNBUFFERED=1 GEMINI_RPM=13 GEMINI_TPM=3000
unset GEMINI_API_BASE GEMINI_API_KEY_ONLY MINIRAG_MAX_TOKENS MINIRAG_ANSWER_TYPE_FIX \
      MINIRAG_PATH2CHUNK_FIX MINIRAG_CHUNK_CUT MINIRAG_CHUNK_FUSION MINIRAG_CONTEXT_LOG \
      MINIRAG_MAX_TOKEN_TEXT_UNIT MINIRAG_SLM_MODEL
for tag in v3_r2 v3_r3; do
  until grep -q "STAGE: QA_${tag}_DONE" logs/v3_replicates_qa.log 2>/dev/null; do sleep 300; done
  echo "=== STAGE: JUDGE_$tag === $(date '+%d/%m %H:%M')"
  until .venv/bin/python reproduce/Step_2_evaluate.py --inputpath ./logs/qwen637_${tag}.csv --repeats 3; do
    echo "=== chưa đủ quota / còn câu lỗi, chờ 20 phút === $(date '+%H:%M')"; sleep 1200
  done
  .venv/bin/python reproduce/compare_variants.py --base ./logs/qwen637_fix_judged.csv \
      --new ./logs/qwen637_${tag}_judged.csv --ctx ./logs/qwen637_${tag}_ctx.jsonl \
      --label $tag | tee ./logs/compare_${tag}.txt
  .venv/bin/python reproduce/compare_variants.py --base ./logs/qwen637_v3_judged.csv \
      --new ./logs/qwen637_${tag}_judged.csv --ctx ./logs/qwen637_${tag}_ctx.jsonl \
      --basectx ./logs/qwen637_v3_ctx.jsonl --label $tag | tee ./logs/compare_${tag}_vs_v3.txt
  echo "=== STAGE: JUDGE_${tag}_DONE === $(date '+%d/%m %H:%M')"
done
.venv/bin/python reproduce/summarize_v3_replicates.py | tee ./logs/v3_replicates_summary.txt
echo "=== STAGE: ALL_DONE === $(date '+%d/%m %H:%M')"
