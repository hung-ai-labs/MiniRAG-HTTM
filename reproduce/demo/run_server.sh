#!/usr/bin/env bash
# Máy chủ demo MiniRAG: hỏi một câu → hai câu trả lời (gốc và B2) kèm bằng chứng.
#   reproduce/demo/run_server.sh                      # Modal Qwen2.5-3B (khớp số benchmark)
#   MINIRAG_DEMO_LLM=gemini reproduce/demo/run_server.sh   # Gemini free tier (nhanh, miễn phí)
cd "$(dirname "$0")/../.." || exit 1
export PYTHONUNBUFFERED=1
if [ "${MINIRAG_DEMO_LLM:-modal}" = "gemini" ]; then
  source reproduce/slm_env.sh gemini >/dev/null || exit 1
else
  CFG="${MINIRAG_CONFIG_DIR:-$HOME/.config/minirag}"
  [ -n "$MINIRAG_SLM_URL" ] || MINIRAG_SLM_URL="$(tr -d '[:space:]' 2>/dev/null < "$CFG/slm_url")"
  [ -n "$MINIRAG_SLM_KEY" ] || MINIRAG_SLM_KEY="$(tr -d '\n' 2>/dev/null < "$CFG/slm_key")"
  export MINIRAG_SLM_URL MINIRAG_SLM_KEY
  source reproduce/slm_env.sh modal >/dev/null || exit 1
fi
exec .venv/bin/python reproduce/demo/server.py
