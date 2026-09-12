#!/bin/zsh
# Chấm hai lượt Qwen 637. Chờ CẢ HAI điều kiện: A1 quét xong (nhả hạn mức Gemini)
# và QA trên Modal đã sinh đủ câu trả lời.
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
export PYTHONUNBUFFERED=1 GEMINI_RPM=13 GEMINI_TPM=3000
unset GEMINI_API_BASE GEMINI_API_KEY_ONLY MINIRAG_MAX_TOKENS MINIRAG_ANSWER_TYPE_FIX
lines () { echo $(( $(wc -l < "$1" 2>/dev/null || echo 1) - 1 )); }
while [ "$(lines ./logs/sources_cap.csv)" -lt 800 ]; do sleep 180; done
echo "=== A1 xong === $(date '+%d/%m %H:%M')"
for f in ./logs/qwen637_fix.csv ./logs/qwen637_nofix.csv; do
  while [ "$(lines $f)" -lt 637 ]; do sleep 180; done
  echo "=== STAGE: JUDGE $f === $(date '+%d/%m %H:%M')"
  until .venv/bin/python reproduce/Step_2_evaluate.py --inputpath $f --repeats 3; do
    echo "=== chưa đủ quota, chờ 20 phút ==="; sleep 1200
  done
  echo "=== STAGE: JUDGE_DONE $f === $(date '+%d/%m %H:%M')"
done
echo "=== STAGE: ALL_DONE === $(date '+%d/%m %H:%M')"
