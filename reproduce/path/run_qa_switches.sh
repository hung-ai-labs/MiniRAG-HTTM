#!/usr/bin/env bash
# Đo end-to-end hai công tắc của thành viên 1 (P1 cắt tỉa, P2 chấm điểm có trọng số) trên dev 200 câu, cấu hình V3
# (MINIRAG_CHUNK_FUSION=rrf) — nơi xếp hạng chunk của đồ thị còn tham gia trộn.
#
# Ba lượt, cùng seed sinh 101, chỉ khác công tắc:
#   v3_p1  = P1 bật
#   v3_p2  = P2 bật
#   v3_p12 = bật cả hai
# Mốc so sánh: ba lượt V3 chính thức đã có (logs/qwen637_v3*_judged.csv) cắt về đúng 200 câu dev.
# Chấm: Gemini free tier, 1 lượt — giống giao thức tầng D. Chạy lại được: QA và chấm đều resume.
cd "$(dirname "$0")/../.." || exit 1
OUT=logs/path_qa
LOG="$OUT/run.log"
mkdir -p "$OUT"
if ! pmset -g batt 2>/dev/null | grep -q "AC Power"; then
  echo "=== DỪNG: máy đang chạy pin — cắm sạc rồi chạy lại" | tee -a "$LOG"; exit 1
fi
caffeinate -i -s -w $$ &

run() {  # run <tag> <MINIRAG_PATH_PRUNE> <MINIRAG_PATH_SCORE>
  local tag=$1
  echo "=== $tag · PRUNE='$2' SCORE='$3' · $(date '+%d/%m %H:%M')" | tee -a "$LOG"
  MINIRAG_PATH_PRUNE="$2" MINIRAG_PATH_SCORE="$3" \
    bash reproduce/stage_d/run_one.sh "$tag" rrf 101 logs/devset.csv "$OUT" >>"$LOG" 2>&1
  local rc=$?
  echo "=== $tag xong, mã thoát $rc · $(date '+%d/%m %H:%M')" | tee -a "$LOG"
  return $rc
}

run v3_p1  default ""      || exit 1
run v3_p2  ""      default || exit 1
run v3_p12 default default || exit 1
echo "=== TẤT CẢ XONG · $(date '+%d/%m %H:%M')" | tee -a "$LOG"
