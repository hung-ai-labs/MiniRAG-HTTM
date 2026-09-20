#!/usr/bin/env bash
# Selftest CE1 — chạy TRƯỚC mọi lượt QA. Offline, 0 lời gọi LLM (parser đọc cache).
#   reproduce/rerank/run_selftest.sh [--fresh]
cd "$(dirname "$0")/../.." || exit 1
CFG="${MINIRAG_CONFIG_DIR:-$HOME/.config/minirag}"
[ -n "$MINIRAG_SLM_URL" ] || MINIRAG_SLM_URL="$(tr -d '[:space:]' 2>/dev/null < "$CFG/slm_url")"
[ -n "$MINIRAG_SLM_KEY" ] || MINIRAG_SLM_KEY="$(tr -d '\n' 2>/dev/null < "$CFG/slm_key")"
export MINIRAG_SLM_URL MINIRAG_SLM_KEY PYTHONUNBUFFERED=1
source reproduce/slm_env.sh modal >/dev/null || exit 1
.venv/bin/python reproduce/rerank/selftest_ce1.py "$@" 2>&1 \
  | grep -v -E "^INFO:|python-dotenv|Loading weights|Fetching|^\[transformers\]"
exit "${PIPESTATUS[0]}"
