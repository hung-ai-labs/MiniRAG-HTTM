#!/bin/zsh
# Chấm V4 sau khi chuỗi chấm V2/V3/V1 xong hẳn -- chạy song song hai tiến trình chấm sẽ
# tranh hạn mức và sinh 429 hàng loạt. So V4 với baseline, và V4 với V3 (cùng trộn, khác
# ngân sách -> đúng một biến).
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
export PYTHONUNBUFFERED=1 GEMINI_RPM=13 GEMINI_TPM=3000
unset GEMINI_API_BASE GEMINI_API_KEY_ONLY MINIRAG_MAX_TOKENS MINIRAG_ANSWER_TYPE_FIX \
      MINIRAG_PATH2CHUNK_FIX MINIRAG_CHUNK_CUT MINIRAG_CHUNK_FUSION MINIRAG_CONTEXT_LOG \
      MINIRAG_MAX_TOKEN_TEXT_UNIT
lines () { [ -f "$1" ] && echo $(( $(wc -l < "$1") - 1 )) || echo 0; }
until grep -q "STAGE: ALL_DONE" logs/fusion637_judge.log 2>/dev/null; do sleep 300; done
while [ "$(lines ./logs/qwen637_v4.csv)" -lt 637 ]; do sleep 180; done
echo "=== STAGE: JUDGE_v4 === $(date '+%d/%m %H:%M')"
until .venv/bin/python reproduce/Step_2_evaluate.py --inputpath ./logs/qwen637_v4.csv --repeats 3; do
  echo "=== chưa đủ quota / còn câu lỗi, chờ 20 phút === $(date '+%H:%M')"; sleep 1200
done
.venv/bin/python reproduce/compare_variants.py --base ./logs/qwen637_fix_judged.csv \
    --new ./logs/qwen637_v4_judged.csv --ctx ./logs/qwen637_v4_ctx.jsonl --label v4 \
    | tee ./logs/compare_v4.txt
.venv/bin/python reproduce/compare_variants.py --base ./logs/qwen637_v3_judged.csv \
    --new ./logs/qwen637_v4_judged.csv --ctx ./logs/qwen637_v4_ctx.jsonl \
    --basectx ./logs/qwen637_v3_ctx.jsonl --label v4 | tee ./logs/compare_v4_vs_v3.txt
echo "=== STAGE: ALL_DONE === $(date '+%d/%m %H:%M')"
