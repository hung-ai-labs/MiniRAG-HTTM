#!/bin/zsh
# Bản dự phòng của run_v3_replicates_qa.sh khi tài khoản Modal đang dùng hết credit: GIỐNG HỆT
# từng biến cấu hình V3, chỉ đọc endpoint từ MINIRAG_SLM_URL (vd. workspace hung-ai-labs) thay vì
# URL cố định. Cùng model Qwen2.5-3B-Instruct bf16, cùng vLLM 0.11.0, cùng A10G (modal_slm.py),
# nên đổi workspace không đổi phép đo. Resume theo số dòng CSV; ghi nối vào cùng log để chuỗi
# chấm vẫn thấy cờ QA_<tag>_DONE.
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
[ -n "$MINIRAG_SLM_URL" ] || { echo "thiếu MINIRAG_SLM_URL"; exit 1; }
export PYTHONUNBUFFERED=1 MINIRAG_ANSWER_TYPE_FIX=1
S=/private/tmp/claude-501/-Users-hunggoodboy-Documents-HTTM-TK-MiniRAG-HTTM/98feb849-7098-448d-a4e3-1eadc18112bd/scratchpad
export MINIRAG_SLM_KEY="$(tr -d '\n' < $S/slm_key.txt)"
source reproduce/slm_env.sh modal >/dev/null || exit 1
Q=./dataset/LiHua-World/qa/query_set.csv
WD=./LiHua-World-qwen-modal

for tag in v3_r2 v3_r3; do
  echo "=== STAGE: QA_$tag (failover, endpoint $MINIRAG_SLM_URL) === $(date '+%d/%m %H:%M')"
  until env MINIRAG_PATH2CHUNK_FIX=0 MINIRAG_CHUNK_CUT= MINIRAG_CHUNK_FUSION=rrf \
          MINIRAG_CONTEXT_LOG=./logs/qwen637_${tag}_ctx.jsonl \
        .venv/bin/python reproduce/Step_1_QA.py --model "$MINIRAG_SLM_MODEL" \
          --workingdir $WD --questions $Q --outputpath ./logs/qwen637_${tag}.csv; do
    echo "=== QA_$tag thất bại, chờ 5 phút === $(date '+%H:%M')"; sleep 300
  done
  echo "=== STAGE: QA_${tag}_DONE === $(date '+%d/%m %H:%M')"
done
echo "=== STAGE: QA_ALL_DONE === $(date '+%d/%m %H:%M')"
