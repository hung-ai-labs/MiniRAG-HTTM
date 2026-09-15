#!/usr/bin/env bash
# Chuỗi tầng D (nhóm duyệt 15/09/2026): 8 lượt theo thứ tự cố định, mỗi lượt QA 435 câu ngoài dev + chấm 1 lượt, rồi phân
# tích MỘT lần ở cuối. Không xem kết quả từng lượt giữa chừng. Chạy lại được: lượt đã xong chỉ resume, không sinh lại.
cd "$(dirname "$0")/../.." || exit 1
mkdir -p logs/stage_d
LOG=logs/stage_d/chain.log
st () { echo "=== STAGE: $1 === $(date '+%d/%m %H:%M')" | tee -a "$LOG"; }
if ! pmset -g batt 2>/dev/null | grep -q "AC Power"; then st "STOPPED (máy chạy pin — cắm sạc, mở nắp rồi chạy lại)"; exit 1; fi
caffeinate -i -s -w $$ &

RUNS="b1_s101:rrf_bm25:101 b2_s101:vector_bm25:101 vec_s202:vector:202 b1_s202:rrf_bm25:202 b2_s202:vector_bm25:202 vec_s303:vector:303 b1_s303:rrf_bm25:303 b2_s303:vector_bm25:303"
for spec in $RUNS; do
  IFS=: read -r tag fusion seed <<< "$spec"
  st "RUN_$tag"
  if ! reproduce/stage_d/run_one.sh "$tag" "$fusion" "$seed" >> "logs/stage_d/${tag}.log" 2>&1; then
    st "RUN_${tag}_FAILED"; tail -5 "logs/stage_d/${tag}.log" | tee -a "$LOG"; exit 1
  fi
  st "RUN_${tag}_DONE"
done
st ANALYZE
"${PYTHON:-.venv/bin/python}" reproduce/stage_d/analyze_stage_d.py 2>&1 | tee -a "$LOG"
st ALL_DONE
