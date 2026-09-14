#!/bin/zsh
# Lặp lại V3 (trộn RRF) thêm 2 lượt sinh trên 637 câu -- CLAUDE.md §3: benchmark cuối phải
# rerun nhiều lượt. sd 0,45 của V3 chỉ là nhiễu giám khảo; đây đo nhiễu giữa các lần chạy.
# Cấu hình giữ nguyên từng biến của run_fusion637_qa.sh `qa v3`: ANSWER_TYPE_FIX=1,
# PATH2CHUNK_FIX=0, CHUNK_CUT rỗng, CHUNK_FUSION=rrf, A1@4000 mặc định, cùng index, model,
# bộ câu hỏi. Chỉ khác lượt lấy mẫu của Qwen (vLLM không truyền temperature).
# NỐI TIẾP, không song song (vụ thrashing 12/09). Resume theo số dòng CSV.
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
export PYTHONUNBUFFERED=1 MINIRAG_ANSWER_TYPE_FIX=1
S=/private/tmp/claude-501/-Users-hunggoodboy-Documents-HTTM-TK-MiniRAG-HTTM/98feb849-7098-448d-a4e3-1eadc18112bd/scratchpad
export MINIRAG_SLM_URL=https://concainit452005--minirag-slm-serve.modal.run
export MINIRAG_SLM_KEY="$(tr -d '\n' < $S/slm_key.txt)"
source reproduce/slm_env.sh modal >/dev/null || exit 1
Q=./dataset/LiHua-World/qa/query_set.csv
WD=./LiHua-World-qwen-modal

for tag in v3_r2 v3_r3; do
  echo "=== STAGE: QA_$tag (PATH2CHUNK_FIX=0 CHUNK_CUT=off CHUNK_FUSION=rrf) === $(date '+%d/%m %H:%M')"
  until env MINIRAG_PATH2CHUNK_FIX=0 MINIRAG_CHUNK_CUT= MINIRAG_CHUNK_FUSION=rrf \
          MINIRAG_CONTEXT_LOG=./logs/qwen637_${tag}_ctx.jsonl \
        .venv/bin/python reproduce/Step_1_QA.py --model "$MINIRAG_SLM_MODEL" \
          --workingdir $WD --questions $Q --outputpath ./logs/qwen637_${tag}.csv; do
    echo "=== QA_$tag thất bại, chờ 5 phút === $(date '+%H:%M')"; sleep 300
  done
  echo "=== STAGE: QA_${tag}_DONE === $(date '+%d/%m %H:%M')"
done
echo "=== STAGE: QA_ALL_DONE === $(date '+%d/%m %H:%M')"
