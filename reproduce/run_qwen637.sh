#!/bin/zsh
# Qwen2.5-3B trên ĐỦ 637 câu — để so với bài báo cùng cỡ mẫu.
#
# Hiện số Qwen của nhóm đo trên dev 200, mà dev set đã chứng minh là bi quan
# 4,37 điểm (Gemini: 57,33 trên dev so với 61,70 trên 637). Nên bảng so với bài
# báo đang khập khiễng về cỡ mẫu — đây là lý do dễ gỡ nhất trong bốn lý do.
#
# Chạy hai biến thể trên cùng đồ thị LiHua-World-qwen-modal (1.556 node, 47 kiểu):
#   FIX=1  -> con số tốt nhất của nhóm
#   FIX=0  -> gần code bài báo nhất, VÀ kiểm giả thuyết độ mịn hệ thống kiểu
#             (đồ thị Gemini 7 kiểu cho −0,32; Qwen 47 kiểu cho +3,50 trên dev)
#
# QA chạy trên Modal nên KHÔNG tốn quota Gemini. Chỉ phần chấm tốn.
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
export PYTHONUNBUFFERED=1
S=/private/tmp/claude-501/-Users-hunggoodboy-Documents-HTTM-TK-MiniRAG-HTTM/98feb849-7098-448d-a4e3-1eadc18112bd/scratchpad
export MINIRAG_SLM_URL=https://concainit452005--minirag-slm-serve.modal.run
export MINIRAG_SLM_KEY="$(tr -d '\n' < $S/slm_key.txt)"
source reproduce/slm_env.sh modal >/dev/null || exit 1
PY=.venv/bin/python
WD=./LiHua-World-qwen-modal
Q=./dataset/LiHua-World/qa/query_set.csv
M="$MINIRAG_SLM_MODEL"

run () { local label=$1; shift
  echo "=== STAGE: $label === $(date '+%d/%m %H:%M')"
  until "$@"; do echo "=== $label thất bại, chờ 20 phút ==="; sleep 1200; done
  echo "=== STAGE: ${label}_DONE === $(date '+%d/%m %H:%M')"; }

judge () { env -u GEMINI_API_BASE -u GEMINI_API_KEY_ONLY -u MINIRAG_MAX_TOKENS \
             -u MINIRAG_ANSWER_TYPE_FIX GEMINI_RPM=13 GEMINI_TPM=3000 \
             $PY reproduce/Step_2_evaluate.py --inputpath "$1" --repeats 3; }

export MINIRAG_ANSWER_TYPE_FIX=1
run QA_FIX    $PY reproduce/Step_1_QA.py --model $M --workingdir $WD \
                 --questions $Q --outputpath ./logs/qwen637_fix.csv
run JUDGE_FIX judge ./logs/qwen637_fix.csv

export MINIRAG_ANSWER_TYPE_FIX=0
run QA_NOFIX    $PY reproduce/Step_1_QA.py --model $M --workingdir $WD \
                   --questions $Q --outputpath ./logs/qwen637_nofix.csv
run JUDGE_NOFIX judge ./logs/qwen637_nofix.csv
echo "=== STAGE: ALL_DONE === $(date '+%d/%m %H:%M')"
