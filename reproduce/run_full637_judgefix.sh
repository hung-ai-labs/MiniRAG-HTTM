#!/bin/zsh
# Chấm lại riêng lượt ĐÃ VÁ. Lượt chưa vá đã chấm sạch (0 lỗi) lúc 15:39 11/09.
# Lượt này bị hạn mức ngày cạn giữa chừng nên phải chấm lại từ đầu — verdict cũ
# đã bị ghi đè bởi "neither" giả, không cứu được từng phần.
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
export PYTHONUNBUFFERED=1
export GEMINI_RPM=13 GEMINI_TPM=3000
unset GEMINI_API_BASE GEMINI_API_KEY_ONLY MINIRAG_MAX_TOKENS MINIRAG_ANSWER_TYPE_FIX
echo "=== STAGE: JUDGE_FIX === $(date '+%d/%m %H:%M')"
until .venv/bin/python reproduce/Step_2_evaluate.py \
        --inputpath ./logs/full637_fix.csv --repeats 3; do
  echo "=== thất bại, chờ 30 phút cho hạn mức hồi ==="; sleep 1800
done
echo "=== STAGE: ALL_DONE === $(date '+%d/%m %H:%M')"
