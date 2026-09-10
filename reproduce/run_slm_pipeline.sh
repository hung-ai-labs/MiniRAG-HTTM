#!/bin/zsh
# Chạy INDEX -> QA -> JUDGE trên SLM, ở bất kỳ nơi nào đã chọn.
#
#   source reproduce/slm_env.sh modal   # hoặc: local
#   ./reproduce/run_slm_pipeline.sh
#
# JUDGE luôn quay lại Gemini để so sánh được với baseline 57,33 ± 1,53.
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
export PYTHONUNBUFFERED=1
PY=.venv/bin/python
if [ -z "$MINIRAG_SLM_MODEL" ]; then
  # Không dùng ${VAR:?msg} ở đây: dấu } trong thông báo kết thúc phép khai triển
  # sớm và phần thừa bị nối vào giá trị, cho ra tên model "minirag-slm}".
  echo "Chưa chọn nơi chạy. Chạy trước: source reproduce/slm_env.sh local|modal"
  exit 1
fi
M="$MINIRAG_SLM_MODEL"
WD="${MINIRAG_SLM_WORKDIR:-./LiHua-World-qwen}"
OUT="${MINIRAG_SLM_OUTPUT:-./logs/qwen_devset.csv}"

echo "model=$M  workingdir=$WD  base=${GEMINI_API_BASE}"

run () { local label=$1; shift
  echo "=== STAGE: $label ==="
  until "$@"; do echo "=== $label failed, retry sau 60s ==="; sleep 60; done
  echo "=== STAGE: ${label}_DONE ==="; }

run INDEX $PY reproduce/Step_0_index.py --model $M --workingdir $WD
run QA    $PY reproduce/Step_1_QA.py    --model $M --workingdir $WD \
             --questions ./logs/devset.csv --outputpath $OUT
run JUDGE env -u GEMINI_API_BASE -u GEMINI_API_KEY_ONLY GEMINI_RPM=13 GEMINI_TPM=3000 \
             $PY reproduce/Step_2_evaluate.py --inputpath $OUT --repeats 3
echo "=== STAGE: ALL_DONE ==="
