#!/bin/zsh
# Ablation vector thuần của V3 (MINIRAG_CHUNK_FUSION=vector) trên 637 câu. Giữ nguyên từng biến
# của V3 (run_v3_replicates_qa.sh) trừ đúng công tắc trộn: ANSWER_TYPE_FIX=1, PATH2CHUNK_FIX=0,
# CHUNK_CUT rỗng, A1@4000 mặc định, cùng index, model, bộ câu hỏi.
# Xếp SAU chuỗi lặp V3: chờ QA_ALL_DONE và không còn Step_1_QA nào (vụ thrashing 12/09).
# Endpoint: MINIRAG_SLM_URL nếu truyền vào; nếu chuỗi đã chuyển tài khoản (cờ
# logs/.v3_rep_failed_over) thì hung-ai-labs; còn lại concainit452005. Resume theo số dòng CSV.
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
REP=logs/v3_replicates_qa.log
until grep -q "STAGE: QA_ALL_DONE" $REP 2>/dev/null; do
  if grep -q "QA_HALTED" $REP 2>/dev/null; then
    echo "=== chuỗi lặp V3 dừng vì endpoint lỗi, không chạy vec === $(date '+%d/%m %H:%M')"; exit 3
  fi
  sleep 60
done
while pgrep -f "Step_1_QA.py" >/dev/null; do sleep 60; done

export PYTHONUNBUFFERED=1 MINIRAG_ANSWER_TYPE_FIX=1
S=/private/tmp/claude-501/-Users-hunggoodboy-Documents-HTTM-TK-MiniRAG-HTTM/98feb849-7098-448d-a4e3-1eadc18112bd/scratchpad
if [ -z "$MINIRAG_SLM_URL" ]; then
  if [ -f logs/.v3_rep_failed_over ]; then
    export MINIRAG_SLM_URL=https://hung-ai-labs--minirag-slm-serve.modal.run
  else
    export MINIRAG_SLM_URL=https://concainit452005--minirag-slm-serve.modal.run
  fi
fi
export MINIRAG_SLM_KEY="$(tr -d '\n' < $S/slm_key.txt)"
source reproduce/slm_env.sh modal >/dev/null || exit 1
Q=./dataset/LiHua-World/qa/query_set.csv
WD=./LiHua-World-qwen-modal
tag=vec

echo "=== STAGE: QA_$tag (CHUNK_FUSION=vector PATH2CHUNK_FIX=0 CHUNK_CUT=off, endpoint $MINIRAG_SLM_URL) === $(date '+%d/%m %H:%M')"
until env MINIRAG_PATH2CHUNK_FIX=0 MINIRAG_CHUNK_CUT= MINIRAG_CHUNK_FUSION=vector \
        MINIRAG_CONTEXT_LOG=./logs/qwen637_${tag}_ctx.jsonl \
      .venv/bin/python reproduce/Step_1_QA.py --model "$MINIRAG_SLM_MODEL" \
        --workingdir $WD --questions $Q --outputpath ./logs/qwen637_${tag}.csv; do
  echo "=== QA_$tag thất bại, chờ 5 phút === $(date '+%H:%M')"; sleep 300
done
echo "=== STAGE: QA_${tag}_DONE === $(date '+%d/%m %H:%M')"
