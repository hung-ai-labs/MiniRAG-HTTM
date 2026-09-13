#!/bin/zsh
# V4 = trộn RRF + A1@2000 -- câu hỏi Efficiency: trộn có cho phép cắt nửa ngân sách không.
# Mô phỏng dev 200 (13/09): RRF@2000 giữ 48,8% chunk đáp án với 1.681 token Sources, ngang
# đồ thị hiện tại @4000 (47,3%, 3.678 token). Mức 2000 có sẵn từ lượt quét A1 12/09
# (off/4000/2000/1000), không chọn mới. Phép thử sạch là 437 câu ngoài dev.
# Chờ run_fusion637_qa.sh xong hẳn: duyệt đồ thị chiếm máy, phải NỐI TIẾP.
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
until grep -q "STAGE: QA_ALL_DONE" logs/fusion637_qa.log 2>/dev/null; do sleep 300; done
export PYTHONUNBUFFERED=1 MINIRAG_ANSWER_TYPE_FIX=1
S=/private/tmp/claude-501/-Users-hunggoodboy-Documents-HTTM-TK-MiniRAG-HTTM/98feb849-7098-448d-a4e3-1eadc18112bd/scratchpad
export MINIRAG_SLM_URL=https://concainit452005--minirag-slm-serve.modal.run
export MINIRAG_SLM_KEY="$(tr -d '\n' < $S/slm_key.txt)"
source reproduce/slm_env.sh modal >/dev/null || exit 1
echo "=== STAGE: QA_v4 (CHUNK_FUSION=rrf MAX_TOKEN_TEXT_UNIT=2000) === $(date '+%d/%m %H:%M')"
until env MINIRAG_PATH2CHUNK_FIX=0 MINIRAG_CHUNK_CUT= MINIRAG_CHUNK_FUSION=rrf \
        MINIRAG_MAX_TOKEN_TEXT_UNIT=2000 MINIRAG_CONTEXT_LOG=./logs/qwen637_v4_ctx.jsonl \
      .venv/bin/python reproduce/Step_1_QA.py --model "$MINIRAG_SLM_MODEL" \
        --workingdir ./LiHua-World-qwen-modal --questions ./dataset/LiHua-World/qa/query_set.csv \
        --outputpath ./logs/qwen637_v4.csv; do
  echo "=== QA_v4 thất bại, chờ 5 phút === $(date '+%H:%M')"; sleep 300
done
echo "=== STAGE: QA_v4_DONE === $(date '+%d/%m %H:%M')"
