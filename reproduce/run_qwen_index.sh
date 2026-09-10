#!/bin/zsh
# Tái tạo đúng chuẩn bài báo: để chính SLM dựng đồ thị, rồi mới QA.
# Đo trên M1 Pro 16GB: ~8 lời gọi/phút -> khoảng 3 giờ cho toàn bộ.
#
#   ollama create minirag-qwen3b -f reproduce/Modelfile.qwen2.5-3b
#   ./reproduce/run_qwen_index.sh
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
export PYTHONUNBUFFERED=1
# Ollama bỏ qua khoá; hai giới hạn nhịp phải nới ra, mặc định của gemini.py
# (13 req/phút, 3000 token/phút) là cho hạn mức Gemini và sẽ bóp nghẹt máy cục bộ.
export GEMINI_API_BASE=http://localhost:11434/v1
export GEMINI_API_KEY_ONLY=ollama
export GEMINI_RPM=100000
export GEMINI_TPM=100000000
PY=.venv/bin/python
WD=./LiHua-World-qwen
M=minirag-qwen3b

run () { local label=$1; shift
  echo "=== STAGE: $label ==="
  until "$@"; do echo "=== $label failed, retry sau 60s ==="; sleep 60; done
  echo "=== STAGE: ${label}_DONE ==="; }

run INDEX $PY reproduce/Step_0_index.py --model $M --workingdir $WD
run QA    $PY reproduce/Step_1_QA.py    --model $M --workingdir $WD \
             --questions ./logs/devset.csv --outputpath ./logs/qwen_devset.csv
# Judge vẫn dùng Gemini để so sánh được với baseline.
run JUDGE env -u GEMINI_API_BASE -u GEMINI_API_KEY_ONLY GEMINI_RPM=13 GEMINI_TPM=3000 \
             $PY reproduce/Step_2_evaluate.py --inputpath ./logs/qwen_devset.csv --repeats 3
echo "=== STAGE: ALL_DONE ==="
