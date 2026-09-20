#!/usr/bin/env bash
# Chạy một script trong reproduce/retrieval_audit/ ở chế độ offline: không sinh, không chấm, parser đọc từ cache.
#   reproduce/retrieval_audit/run_offline.sh dump_contexts.py --fusion vector_bm25
# Endpoint SLM chỉ cần để build_rag khởi tạo được; MINIRAG_KW_CACHE_ONLY=1 trong script chặn mọi lời gọi LLM.
cd "$(dirname "$0")/../.." || exit 1
CFG="${MINIRAG_CONFIG_DIR:-$HOME/.config/minirag}"
[ -n "$MINIRAG_SLM_URL" ] || MINIRAG_SLM_URL="$(tr -d '[:space:]' 2>/dev/null < "$CFG/slm_url")"
[ -n "$MINIRAG_SLM_KEY" ] || MINIRAG_SLM_KEY="$(tr -d '\n' 2>/dev/null < "$CFG/slm_key")"
export MINIRAG_SLM_URL MINIRAG_SLM_KEY PYTHONUNBUFFERED=1
source reproduce/slm_env.sh modal >/dev/null || exit 1
SCRIPT="reproduce/retrieval_audit/$1"; shift
.venv/bin/python "$SCRIPT" --model "$MINIRAG_SLM_MODEL" --workingdir ./LiHua-World-qwen-modal "$@" 2>&1 \
  | grep -v -E "^INFO:|python-dotenv|Loading weights"
exit "${PIPESTATUS[0]}"
