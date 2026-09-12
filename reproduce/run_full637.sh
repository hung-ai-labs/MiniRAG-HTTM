#!/bin/zsh
# Baseline Gemini trên ĐỦ 637 câu, corpus 442 — ô còn trống trong bảng kết quả.
#
# Lượt 06/09 có 637 câu nhưng chạy trên corpus cũ 267 tài liệu (lạc quan hơn
# thực tế 8,3 điểm). Năm cấu hình từ 07/09 trở đi đúng corpus 442 nhưng chỉ 200
# câu — quá nhỏ để McNemar kết luận được (đã chết hai lần: p=0,267 và p=0,522).
#
# Chạy hai biến thể, chung một đồ thị, khác đúng một biến môi trường:
#   NOFIX  = MINIRAG_ANSWER_TYPE_FIX=0  -> nối dài đúng baseline 57,33 hiện tại
#   FIX    = MINIRAG_ANSWER_TYPE_FIX=1  -> ứng viên baseline_v2
# Nhóm Multi lên n=67, Null lên n=64 (hiện là 21 và 20).
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
export PYTHONUNBUFFERED=1
export GEMINI_RPM=13 GEMINI_TPM=3000     # hạn mức free tier, đã sweep, đừng chỉnh
unset GEMINI_API_BASE GEMINI_API_KEY_ONLY MINIRAG_MAX_TOKENS
PY=.venv/bin/python
WD=./LiHua-World-gemini
Q=./dataset/LiHua-World/qa/query_set.csv

run () { local label=$1; shift
  echo "=== STAGE: $label === $(date +%H:%M)"
  until "$@"; do echo "=== $label failed, retry sau 60s ==="; sleep 60; done
  echo "=== STAGE: ${label}_DONE === $(date +%H:%M)"; }

# Biến thể chưa vá trước: nó là mốc so sánh mà mọi tài liệu đang trích dẫn.
export MINIRAG_ANSWER_TYPE_FIX=0
run QA_NOFIX    $PY reproduce/Step_1_QA.py --workingdir $WD --questions $Q \
                   --outputpath ./logs/full637_nofix.csv
run JUDGE_NOFIX $PY reproduce/Step_2_evaluate.py --inputpath ./logs/full637_nofix.csv --repeats 3

export MINIRAG_ANSWER_TYPE_FIX=1
run QA_FIX      $PY reproduce/Step_1_QA.py --workingdir $WD --questions $Q \
                   --outputpath ./logs/full637_fix.csv
run JUDGE_FIX   $PY reproduce/Step_2_evaluate.py --inputpath ./logs/full637_fix.csv --repeats 3
echo "=== STAGE: ALL_DONE === $(date +%H:%M)"
