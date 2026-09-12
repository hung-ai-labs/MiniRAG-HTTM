#!/bin/zsh
# Chạy lại tới khi đủ 637 câu. Script đo bỏ qua câu lỗi (không ghi ra file) nên
# mỗi lượt chỉ nhặt thêm phần quota cho phép; lượt sau resume đúng phần còn thiếu.
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
export PYTHONUNBUFFERED=1 GEMINI_RPM=13 GEMINI_TPM=3000
unset GEMINI_API_BASE GEMINI_API_KEY_ONLY MINIRAG_MAX_TOKENS
for i in {1..40}; do
  n=$(( $(wc -l < ./logs/entity_cap.csv 2>/dev/null || echo 1) - 1 ))
  [ "$n" -ge 637 ] && break
  echo "=== lượt $i · đang có $n/637 câu · $(date '+%d/%m %H:%M') ==="
  .venv/bin/python reproduce/measure_entity_cap.py --workingdir ./LiHua-World-gemini \
      --questions ./dataset/LiHua-World/qa/query_set.csv >/dev/null 2>&1
  n2=$(( $(wc -l < ./logs/entity_cap.csv 2>/dev/null || echo 1) - 1 ))
  [ "$n2" -ge 637 ] && break
  [ "$n2" -le "$n" ] && { echo "không thêm được câu nào, chờ 30 phút"; sleep 1800; }
done
echo "=== STAGE: ALL_DONE === $(date '+%d/%m %H:%M')"
ENTITY_CAP_REPORT_ONLY=1 .venv/bin/python reproduce/measure_entity_cap.py \
    --workingdir ./LiHua-World-gemini --questions ./dataset/LiHua-World/qa/query_set.csv 2>/dev/null
