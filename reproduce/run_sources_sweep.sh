#!/bin/zsh
# A1: quét ngân sách token bảng Sources trên dev set 200 câu.
# Chỉ truy hồi (only_need_context), không sinh, không chấm -> 1 lời gọi/câu.
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
export PYTHONUNBUFFERED=1 GEMINI_RPM=13 GEMINI_TPM=3000
unset GEMINI_API_BASE GEMINI_API_KEY_ONLY MINIRAG_MAX_TOKENS
export SOURCES_BUDGETS=off,4000,2000,1000
for i in {1..20}; do
  echo "=== lượt $i · $(date '+%d/%m %H:%M') ==="
  .venv/bin/python reproduce/measure_sources_cap.py --workingdir ./LiHua-World-gemini \
      --questions ./logs/devset.csv && break
  echo "=== chưa đủ quota, chờ 20 phút ==="; sleep 1200
done
echo "=== STAGE: ALL_DONE === $(date '+%d/%m %H:%M')"
