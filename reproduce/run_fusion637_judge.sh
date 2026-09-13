#!/bin/zsh
# Chấm theo đúng thứ tự QA: V2 -> V3 -> V1. Mỗi biến thể so với baseline qwen637_fix
# (Qwen, 637 câu, A1@4000, ANSWER_TYPE_FIX=1, path2chunk upstream, không trộn).
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
export PYTHONUNBUFFERED=1 GEMINI_RPM=13 GEMINI_TPM=3000
unset GEMINI_API_BASE GEMINI_API_KEY_ONLY MINIRAG_MAX_TOKENS MINIRAG_ANSWER_TYPE_FIX \
      MINIRAG_PATH2CHUNK_FIX MINIRAG_CHUNK_CUT MINIRAG_CHUNK_FUSION MINIRAG_CONTEXT_LOG
lines () { [ -f "$1" ] && echo $(( $(wc -l < "$1") - 1 )) || echo 0; }
for tag in v2 v3 v1; do
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
