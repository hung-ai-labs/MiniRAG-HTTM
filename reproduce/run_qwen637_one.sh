#!/bin/zsh
# Một biến thể Qwen 637 câu. Tách khỏi run_qwen637_qa.sh để hai biến thể chạy
# SONG SONG thay vì nối tiếp.
#
#   ./reproduce/run_qwen637_one.sh 1    # MINIRAG_ANSWER_TYPE_FIX=1 -> qwen637_fix.csv
#   ./reproduce/run_qwen637_one.sh 0    # MINIRAG_ANSWER_TYPE_FIX=0 -> qwen637_nofix.csv
#
# Vì sao song song được, dù chỉ có một A10G: đo trên chính lượt chạy này, mỗi câu
# tốn 13,7s thì ~5s là GPU còn ~9s là Python duyệt đồ thị trên máy này
# (operate.py:1125 path2chunk, 6,18 triệu lần kiểm tra chuỗi con mỗi câu). Phần
# GPU chạy ở lô 1, KV cache dùng 1,2%/24GB — thừa chỗ cho request thứ hai. Máy có
# 8 nhân, mỗi tiến trình chiếm ~1. Hai biến thể độc lập: khác file đầu ra, dùng
# chung index nhưng chỉ đọc.
#
# An toàn khi chạy lại: Step_1_QA.py:44 đếm số dòng đã có rồi chạy tiếp từ đó.
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
FIX="${1:?dùng: run_qwen637_one.sh 0|1}"
case "$FIX" in
  1) OUT=./logs/qwen637_fix.csv;;
  0) OUT=./logs/qwen637_nofix.csv;;
  *) echo "tham số phải là 0 hoặc 1"; exit 1;;
esac

export PYTHONUNBUFFERED=1
S=/private/tmp/claude-501/-Users-hunggoodboy-Documents-HTTM-TK-MiniRAG-HTTM/98feb849-7098-448d-a4e3-1eadc18112bd/scratchpad
export MINIRAG_SLM_URL=https://concainit452005--minirag-slm-serve.modal.run
export MINIRAG_SLM_KEY="$(tr -d '\n' < $S/slm_key.txt)"
source reproduce/slm_env.sh modal >/dev/null || exit 1
export MINIRAG_ANSWER_TYPE_FIX=$FIX

echo "=== STAGE: QA_FIX$FIX === $(date '+%d/%m %H:%M')  -> $OUT"
until .venv/bin/python reproduce/Step_1_QA.py \
        --model "$MINIRAG_SLM_MODEL" --workingdir ./LiHua-World-qwen-modal \
        --questions ./dataset/LiHua-World/qa/query_set.csv --outputpath $OUT; do
  echo "=== QA_FIX$FIX thất bại, chờ 5 phút rồi chạy tiếp === $(date '+%d/%m %H:%M')"
  sleep 300
done
echo "=== STAGE: QA_FIX${FIX}_DONE === $(date '+%d/%m %H:%M')"
