#!/bin/zsh
# Thay run_adaptive637_qa.sh từ 13/09 ~23:00, sau chẩn đoán dev 200 và mô phỏng trộn:
#   V2 = sửa lỗi path2chunk + cắt vách   (phương pháp đã bàn; chẩn đoán dự báo giữ 37,2% đáp án)
#   V3 = baseline + trộn RRF đồ thị/vector (đổi ĐÚNG một biến; mô phỏng dự báo 47,3% -> 66,7%)
#   V1 = chỉ sửa lỗi path2chunk          (ablation cho V2; dự báo ~không đổi)
# V3 xếp trước V1 để kết quả có triển vọng nhất kịp chấm trong hạn mức đêm nay.
# NỐI TIẾP, không song song (vụ thrashing 12/09). Resume theo số dòng CSV.
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
export PYTHONUNBUFFERED=1 MINIRAG_ANSWER_TYPE_FIX=1
S=/private/tmp/claude-501/-Users-hunggoodboy-Documents-HTTM-TK-MiniRAG-HTTM/98feb849-7098-448d-a4e3-1eadc18112bd/scratchpad
export MINIRAG_SLM_URL=https://concainit452005--minirag-slm-serve.modal.run
export MINIRAG_SLM_KEY="$(tr -d '\n' < $S/slm_key.txt)"
source reproduce/slm_env.sh modal >/dev/null || exit 1
Q=./dataset/LiHua-World/qa/query_set.csv
WD=./LiHua-World-qwen-modal

qa () { local tag=$1 fix=$2 cut=$3 fus=$4
  echo "=== STAGE: QA_$tag (PATH2CHUNK_FIX=$fix CHUNK_CUT=${cut:-off} CHUNK_FUSION=${fus:-off}) === $(date '+%d/%m %H:%M')"
  until env MINIRAG_PATH2CHUNK_FIX=$fix MINIRAG_CHUNK_CUT=$cut MINIRAG_CHUNK_FUSION=$fus \
          MINIRAG_CONTEXT_LOG=./logs/qwen637_${tag}_ctx.jsonl \
        .venv/bin/python reproduce/Step_1_QA.py --model "$MINIRAG_SLM_MODEL" \
          --workingdir $WD --questions $Q --outputpath ./logs/qwen637_${tag}.csv; do
    echo "=== QA_$tag thất bại, chờ 5 phút === $(date '+%H:%M')"; sleep 300
  done
  echo "=== STAGE: QA_${tag}_DONE === $(date '+%d/%m %H:%M')"
}
qa v2 1 knee ""
qa v3 0 ""   rrf
qa v1 1 ""   ""
echo "=== STAGE: QA_ALL_DONE === $(date '+%d/%m %H:%M')"
