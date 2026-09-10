#!/bin/zsh
# Lượt Qwen trên code CHƯA vá (MINIRAG_ANSWER_TYPE_FIX=0), để đối chứng.
#
#   source reproduce/slm_env.sh modal      # hoặc: local
#   ./reproduce/run_qwen_nofix.sh
#
# Dùng lại đúng index đã có, KHÔNG index lại: bản vá chỉ chạm đường truy vấn
# (operate.py:1311 -> networkx_impl.py:173), index không gọi tới nên hai biến
# thể chia sẻ được đồ thị. Nhờ vậy chênh lệch đo được chỉ do bản vá.
#
# JUDGE luôn quay lại Gemini để so sánh được với ba cấu hình đã đo.
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
export PYTHONUNBUFFERED=1
export MINIRAG_ANSWER_TYPE_FIX=0          # <-- khôi phục hành vi upstream
PY=.venv/bin/python
if [ -z "$MINIRAG_SLM_MODEL" ]; then
  echo "Chưa chọn nơi chạy. Chạy trước: source reproduce/slm_env.sh local|modal"
  exit 1
fi
M="$MINIRAG_SLM_MODEL"
WD="${MINIRAG_SLM_WORKDIR:-./LiHua-World-qwen-modal}"
OUT="${MINIRAG_SLM_OUTPUT:-./logs/qwen_nofix_devset.csv}"

echo "model=$M  workingdir=$WD  base=${GEMINI_API_BASE}  ANSWER_TYPE_FIX=0"

run () { local label=$1; shift
  echo "=== STAGE: $label ==="
  until "$@"; do echo "=== $label failed, retry sau 60s ==="; sleep 60; done
  echo "=== STAGE: ${label}_DONE ==="; }

run QA $PY reproduce/Step_1_QA.py --model $M --workingdir $WD \
       --questions ./logs/devset.csv --outputpath $OUT
run JUDGE env -u GEMINI_API_BASE -u GEMINI_API_KEY_ONLY -u MINIRAG_ANSWER_TYPE_FIX \
       GEMINI_RPM=13 GEMINI_TPM=3000 \
       $PY reproduce/Step_2_evaluate.py --inputpath $OUT --repeats 3
echo "=== STAGE: ALL_DONE ==="
