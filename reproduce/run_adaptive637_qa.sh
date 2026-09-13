#!/bin/zsh
# Chuỗi việc CHIẾM MÁY -- duyệt đồ thị chạy Python thuần trên laptop, nên NỐI TIẾP,
# không song song (12/09: hai tiến trình QA cùng lúc đẩy máy vào swap, chậm 5 lần).
#   1. chẩn đoán dev 200 (chỉ truy hồi, resume từ các câu chạy thử)
#   2. QA V2 = sửa lỗi path2chunk + cắt theo vách   <- phương pháp đề xuất, chạy trước
#   3. QA V1 = chỉ sửa lỗi path2chunk               <- ablation
# Baseline là logs/qwen637_fix.csv (đã có, đã chấm). Mọi thứ khác giữ nguyên:
# Qwen2.5-3B trên Modal, index LiHua-World-qwen-modal, ANSWER_TYPE_FIX=1, A1@4000.
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
export PYTHONUNBUFFERED=1 MINIRAG_ANSWER_TYPE_FIX=1
S=/private/tmp/claude-501/-Users-hunggoodboy-Documents-HTTM-TK-MiniRAG-HTTM/98feb849-7098-448d-a4e3-1eadc18112bd/scratchpad
export MINIRAG_SLM_URL=https://concainit452005--minirag-slm-serve.modal.run
export MINIRAG_SLM_KEY="$(tr -d '\n' < $S/slm_key.txt)"
source reproduce/slm_env.sh modal >/dev/null || exit 1
Q=./dataset/LiHua-World/qa/query_set.csv
WD=./LiHua-World-qwen-modal

echo "=== STAGE: DIAG200 === $(date '+%d/%m %H:%M')"
./reproduce/run_diag_path2chunk.sh
[ $? -eq 2 ] && { echo "=== DỪNG: code trong operate.py lệch chẩn đoán ==="; exit 2; }
echo "=== STAGE: DIAG200_DONE === $(date '+%d/%m %H:%M')"

qa () { local tag=$1 fix=$2 cut=$3
  echo "=== STAGE: QA_$tag (PATH2CHUNK_FIX=$fix CHUNK_CUT=${cut:-off}) === $(date '+%d/%m %H:%M')"
  until env MINIRAG_PATH2CHUNK_FIX=$fix MINIRAG_CHUNK_CUT=$cut \
          MINIRAG_CONTEXT_LOG=./logs/qwen637_${tag}_ctx.jsonl \
        .venv/bin/python reproduce/Step_1_QA.py --model "$MINIRAG_SLM_MODEL" \
          --workingdir $WD --questions $Q --outputpath ./logs/qwen637_${tag}.csv; do
    echo "=== QA_$tag thất bại, chờ 5 phút === $(date '+%H:%M')"; sleep 300
  done
  echo "=== STAGE: QA_${tag}_DONE === $(date '+%d/%m %H:%M')"
}
qa v2 1 knee
qa v1 1 ""
echo "=== STAGE: QA_ALL_DONE === $(date '+%d/%m %H:%M')"
