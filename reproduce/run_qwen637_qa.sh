#!/bin/zsh
# Chỉ phần QA của Qwen 637 — chạy trên Modal nên KHÔNG tốn lời gọi Gemini nào,
# vì vậy chạy song song được với lượt quét A1 đang dùng hạn mức Gemini.
# Phần chấm tách sang run_qwen637_judge.sh, xếp hàng sau A1.
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
  until "$@"; do echo "=== $label thất bại, chờ 5 phút ==="; sleep 300; done
  echo "=== STAGE: ${label}_DONE === $(date '+%d/%m %H:%M')"; }

export MINIRAG_ANSWER_TYPE_FIX=1
run QA_FIX   $PY reproduce/Step_1_QA.py --model $M --workingdir $WD \
                --questions $Q --outputpath ./logs/qwen637_fix.csv
export MINIRAG_ANSWER_TYPE_FIX=0
run QA_NOFIX $PY reproduce/Step_1_QA.py --model $M --workingdir $WD \
                --questions $Q --outputpath ./logs/qwen637_nofix.csv
echo "=== STAGE: QA_ALL_DONE === $(date '+%d/%m %H:%M')"
