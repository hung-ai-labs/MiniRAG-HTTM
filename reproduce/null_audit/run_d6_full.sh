#!/usr/bin/env bash
# Đ6 bước 3 (đăng ký trước: reproduce/null_audit/preregistration/D6_cham_lai_null_rubric_lam_ro.md).
# Chấm lại 540 câu trả lời Null × 3 lượt bằng rubric làm rõ. Chạy lại được: nếu hết hạn mức giữa chừng, script Python tự
# dừng khi chưa đủ 3 lượt; vòng lặp này chờ 10 phút rồi chấm nốt phần còn thiếu. Giữ máy thức suốt quá trình.
cd "$(dirname "$0")/../.." || exit 1
OUT=logs/null_audit/d6_clarified
LOG="$OUT/full_run.log"
mkdir -p "$OUT"
if ! pmset -g batt 2>/dev/null | grep -q "AC Power"; then
  echo "=== DỪNG: máy đang chạy pin — cắm sạc rồi chạy lại" | tee -a "$LOG"; exit 1
fi
caffeinate -i -s -w $$ &

for attempt in $(seq 1 18); do
  echo "=== lần $attempt · $(date '+%d/%m %H:%M')" | tee -a "$LOG"
  if .venv/bin/python reproduce/null_audit/rejudge_null_clarified.py --full >> "$LOG" 2>&1; then
    echo "=== XONG · $(date '+%d/%m %H:%M')" | tee -a "$LOG"
    exit 0
  fi
  echo "=== chưa đủ 3 lượt cho mọi câu — chờ 10 phút rồi chấm nốt" | tee -a "$LOG"
  sleep 600
done
echo "=== DỪNG sau 18 lần thử · $(date '+%d/%m %H:%M')" | tee -a "$LOG"
exit 1
