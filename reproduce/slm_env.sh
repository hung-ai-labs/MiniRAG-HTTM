#!/bin/zsh
# Công tắc chọn nơi chạy SLM. Source vào shell rồi chạy pipeline như bình thường.
#
#   source reproduce/slm_env.sh local     # Ollama trên máy này (miễn phí, nóng máy)
#   source reproduce/slm_env.sh modal     # A10G thuê trên Modal (~$1/lượt, máy mát)
#   source reproduce/slm_env.sh gemini     # quay lại Gemini free tier (mặc định dự án)
#
# Cả ba đều nói giao thức OpenAI, nên minirag/llm/gemini.py dùng chung được —
# không có backend nào phải viết thêm.

_target="${1:-}"

case "$_target" in
  local)
    export GEMINI_API_BASE=http://localhost:11434/v1
    export GEMINI_API_KEY_ONLY=ollama   # chặn 12 khoá Gemini trong .env lọt vào pool
    export MINIRAG_SLM_MODEL=minirag-qwen3b
    # Giới hạn nhịp mặc định (13 req/phút, 3000 token/phút) là hình dạng của
    # hạn mức Gemini; áp lên máy cục bộ sẽ chậm gấp mấy chục lần.
    export GEMINI_RPM=100000
    export GEMINI_TPM=100000000
    curl -s -m 2 http://localhost:11434/api/tags >/dev/null 2>&1 \
      || echo "  ⚠️  Ollama chưa chạy. Mở terminal khác: ollama serve"
    echo "SLM → Ollama cục bộ · model minirag-qwen3b · Qwen2.5-3B Q4_K_M"
    echo "     ~8 lời gọi/phút · ~3 giờ cho toàn bộ · chiếm GPU máy"
    ;;

  modal)
    if [ -z "$MINIRAG_SLM_URL" ] || [ -z "$MINIRAG_SLM_KEY" ]; then
      echo "  ⚠️  Thiếu MINIRAG_SLM_URL hoặc MINIRAG_SLM_KEY."
      echo "      modal deploy reproduce/modal_slm.py     # in ra URL"
      echo "      export MINIRAG_SLM_URL=https://<...>.modal.run"
      echo "      export MINIRAG_SLM_KEY=<khoá đã tạo bằng modal secret create>"
      return 1 2>/dev/null || exit 1
    fi
    export GEMINI_API_BASE="${MINIRAG_SLM_URL%/}/v1"
    export GEMINI_API_KEY_ONLY="$MINIRAG_SLM_KEY"   # chỉ khoá này hợp lệ với Modal
    export MINIRAG_SLM_MODEL=minirag-slm
    export GEMINI_RPM=100000
    export GEMINI_TPM=100000000
    echo "SLM → Modal A10G · model Qwen2.5-3B-Instruct (bf16, không lượng tử hoá)"
    echo "     vLLM gộp 32 request song song · ~40 phút · ~\$1 · máy không nóng"
    echo "     Lần gọi đầu chờ 2-5 phút để GPU khởi động."
    ;;

  gemini)
    unset GEMINI_API_BASE MINIRAG_SLM_MODEL GEMINI_API_KEY_ONLY
    export GEMINI_RPM=13
    export GEMINI_TPM=3000
    echo "SLM → Gemini free tier · gemini-flash-lite-latest (mặc định dự án)"
    echo "     Đây là cấu hình đã tạo ra baseline 57,33 ± 1,53."
    ;;

  *)
    echo "Dùng: source reproduce/slm_env.sh {local|modal|gemini}"
    return 1 2>/dev/null || exit 1
    ;;
esac

echo "     GEMINI_API_BASE=${GEMINI_API_BASE:-<mặc định Gemini>}"
