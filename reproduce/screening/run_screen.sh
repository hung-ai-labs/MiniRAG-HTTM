#!/usr/bin/env bash
# Chạy screen_variant.py (tầng A–C của quy trình sàng lọc, ROADMAP) với endpoint SLM trên Modal.
#   reproduce/screening/run_screen.sh --variant b2 --stage canary
# Mỗi người dùng Modal và khoá của riêng mình (reproduce/screening/HUONG_DAN_CHAY.md):
#   endpoint: MINIRAG_SLM_URL, hoặc file ~/.config/minirag/slm_url  (https://<workspace>--minirag-slm-serve.modal.run)
#   khoá:     MINIRAG_SLM_KEY, hoặc file ~/.config/minirag/slm_key  (giá trị trong Modal secret minirag-slm-key)
# Khoá không bao giờ nằm trong repo hay log. Không có tầng D ở đây.
cd "$(dirname "$0")/../.." || exit 1
CFG="${MINIRAG_CONFIG_DIR:-$HOME/.config/minirag}"
[ -n "$MINIRAG_SLM_URL" ] || MINIRAG_SLM_URL="$(tr -d '[:space:]' 2>/dev/null < "$CFG/slm_url")"
[ -n "$MINIRAG_SLM_KEY" ] || MINIRAG_SLM_KEY="$(tr -d '\n' 2>/dev/null < "$CFG/slm_key")"
if [ -z "$MINIRAG_SLM_URL" ] || [ -z "$MINIRAG_SLM_KEY" ]; then
  echo "Thiếu endpoint hoặc khoá SLM: đặt MINIRAG_SLM_URL / MINIRAG_SLM_KEY, hoặc tạo $CFG/slm_url và $CFG/slm_key" >&2
  echo "(xem reproduce/screening/HUONG_DAN_CHAY.md)" >&2
  exit 1
fi
export MINIRAG_SLM_URL MINIRAG_SLM_KEY PYTHONUNBUFFERED=1
PY="${PYTHON:-.venv/bin/python}"
source reproduce/slm_env.sh modal >/dev/null || exit 1
mkdir -p logs/screening
SCRIPT="${SCREEN_SCRIPT:-reproduce/screening/screen_variant.py}"
echo "=== $(date '+%d/%m %H:%M') $SCRIPT $* (endpoint $MINIRAG_SLM_URL) ===" >> logs/screening/screen.log
"$PY" "$SCRIPT" --model "$MINIRAG_SLM_MODEL" --workingdir ./LiHua-World-qwen-modal "$@" 2>&1 \
  | grep -v -E "^INFO:|python-dotenv|Loading weights" | tee -a logs/screening/screen.log
exit "${PIPESTATUS[0]}"
