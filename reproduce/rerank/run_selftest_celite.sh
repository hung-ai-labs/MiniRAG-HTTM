#!/usr/bin/env bash
# Selftest ce1_lite — chạy TRƯỚC lượt canary của CE-lite. Offline, 0 lời gọi LLM.
cd "$(dirname "$0")/../.." || exit 1
CFG="${MINIRAG_CONFIG_DIR:-$HOME/.config/minirag}"
[ -n "$MINIRAG_SLM_URL" ] || MINIRAG_SLM_URL="$(tr -d '[:space:]' 2>/dev/null < "$CFG/slm_url")"
[ -n "$MINIRAG_SLM_KEY" ] || MINIRAG_SLM_KEY="$(tr -d '\n' 2>/dev/null < "$CFG/slm_key")"
export MINIRAG_SLM_URL MINIRAG_SLM_KEY PYTHONUNBUFFERED=1
source reproduce/slm_env.sh modal >/dev/null || exit 1
.venv/bin/python reproduce/rerank/selftest_celite.py "$@" 2>&1 \
  | grep -v -E "^INFO:|python-dotenv|Loading weights|Fetching|^\[transformers\]"
exit "${PIPESTATUS[0]}"
