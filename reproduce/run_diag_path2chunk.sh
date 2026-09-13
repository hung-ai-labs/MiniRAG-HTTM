#!/bin/zsh
# Bước 1 chẩn đoán: dev 200, index Qwen, chỉ truy hồi (1 lời gọi ngắn/câu trên Modal),
# 0 lời gọi chấm Gemini. Resume được. Mã thoát 2 = bản sao lệch hàm gốc -> dừng hẳn.
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
export PYTHONUNBUFFERED=1 MINIRAG_ANSWER_TYPE_FIX=1
S=/private/tmp/claude-501/-Users-hunggoodboy-Documents-HTTM-TK-MiniRAG-HTTM/98feb849-7098-448d-a4e3-1eadc18112bd/scratchpad
export MINIRAG_SLM_URL=https://concainit452005--minirag-slm-serve.modal.run
export MINIRAG_SLM_KEY="$(tr -d '\n' < $S/slm_key.txt)"
source reproduce/slm_env.sh modal >/dev/null || exit 1
LIMIT="${1:-0}"
echo "=== STAGE: DIAG (limit=$LIMIT) === $(date '+%d/%m %H:%M')"
while true; do
  .venv/bin/python reproduce/diagnose_path2chunk.py --model "$MINIRAG_SLM_MODEL" \
      --workingdir ./LiHua-World-qwen-modal --questions ./logs/devset.csv \
      --outputpath ./logs/diag_path2chunk.jsonl --limit "$LIMIT"
  rc=$?
  [ $rc -eq 0 ] && break
  [ $rc -eq 2 ] && { echo "=== DỪNG: bản sao lệch hàm gốc ==="; exit 2; }
  echo "=== còn câu lỗi, chờ 2 phút rồi chạy tiếp === $(date '+%H:%M')"; sleep 120
done
echo "=== STAGE: ALL_DONE === $(date '+%d/%m %H:%M')"
