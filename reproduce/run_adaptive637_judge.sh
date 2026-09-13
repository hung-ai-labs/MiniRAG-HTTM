#!/bin/zsh
# Chuỗi CHẤM -- Gemini, gần như không tốn CPU, nên chạy song song được với chuỗi QA.
# V2 chấm trước (kết quả chính), rồi V1 (ablation), rồi so V2 với V1.
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
export PYTHONUNBUFFERED=1 GEMINI_RPM=13 GEMINI_TPM=3000
unset GEMINI_API_BASE GEMINI_API_KEY_ONLY MINIRAG_MAX_TOKENS MINIRAG_ANSWER_TYPE_FIX \
      MINIRAG_PATH2CHUNK_FIX MINIRAG_CHUNK_CUT MINIRAG_CONTEXT_LOG
lines () { echo $(( $(wc -l < "$1" 2>/dev/null || echo 1) - 1 )); }
for tag in v2 v1; do
  f=./logs/qwen637_${tag}.csv
  while [ "$(lines $f)" -lt 637 ]; do sleep 180; done
  echo "=== STAGE: JUDGE_$tag === $(date '+%d/%m %H:%M')"
  until .venv/bin/python reproduce/Step_2_evaluate.py --inputpath $f --repeats 3; do
    echo "=== chưa đủ quota / còn câu lỗi, chờ 20 phút === $(date '+%H:%M')"; sleep 1200
  done
  .venv/bin/python reproduce/compare_variants.py --base ./logs/qwen637_fix_judged.csv \
      --new ./logs/qwen637_${tag}_judged.csv --ctx ./logs/qwen637_${tag}_ctx.jsonl \
      --label $tag | tee ./logs/compare_${tag}.txt
  echo "=== STAGE: JUDGE_${tag}_DONE === $(date '+%d/%m %H:%M')"
done
.venv/bin/python reproduce/compare_variants.py --base ./logs/qwen637_v1_judged.csv \
    --new ./logs/qwen637_v2_judged.csv --ctx ./logs/qwen637_v2_ctx.jsonl \
    --basectx ./logs/qwen637_v1_ctx.jsonl --label v2 | tee ./logs/compare_v2_vs_v1.txt
echo "=== STAGE: ALL_DONE === $(date '+%d/%m %H:%M')"
