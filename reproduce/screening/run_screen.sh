#!/bin/zsh
# Chạy screen_variant.py (tầng A–C của quy trình sàng lọc, ROADMAP) với endpoint SLM trên Modal.
#   reproduce/screening/run_screen.sh --variant b1 --stage canary
# Endpoint: MINIRAG_SLM_URL nếu truyền vào; nếu chuỗi lặp V3 đã chuyển tài khoản (cờ
# logs/.v3_rep_failed_over) thì hung-ai-labs; còn lại concainit452005. Không có tầng D ở đây.
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
S=/private/tmp/claude-501/-Users-hunggoodboy-Documents-HTTM-TK-MiniRAG-HTTM/98feb849-7098-448d-a4e3-1eadc18112bd/scratchpad
if [ -z "$MINIRAG_SLM_URL" ]; then
  if [ -f logs/.v3_rep_failed_over ]; then
    export MINIRAG_SLM_URL=https://hung-ai-labs--minirag-slm-serve.modal.run
  else
    export MINIRAG_SLM_URL=https://concainit452005--minirag-slm-serve.modal.run
  fi
fi
export PYTHONUNBUFFERED=1 MINIRAG_SLM_KEY="$(tr -d '\n' < $S/slm_key.txt)"
source reproduce/slm_env.sh modal >/dev/null || exit 1
mkdir -p logs/screening
echo "=== $(date '+%d/%m %H:%M') screen_variant $* (endpoint $MINIRAG_SLM_URL) ===" >> logs/screening/screen.log
.venv/bin/python ${SCREEN_SCRIPT:-reproduce/screening/screen_variant.py} --model "$MINIRAG_SLM_MODEL" \
    --workingdir ./LiHua-World-qwen-modal "$@" 2>&1 | grep -v -E "^INFO:|python-dotenv|Loading weights" | tee -a logs/screening/screen.log
exit ${pipestatus[1]}
