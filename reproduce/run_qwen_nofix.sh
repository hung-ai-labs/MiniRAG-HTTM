#!/bin/zsh
# Lượt Qwen trên code CHƯA vá (MINIRAG_ANSWER_TYPE_FIX=0), để đối chứng.
# Dùng lại đúng index ./LiHua-World-qwen: bản vá chỉ chạm đường truy vấn
# (operate.py:1311), index không gọi tới nên hai biến thể chia sẻ được đồ thị.
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
export PYTHONUNBUFFERED=1
export GEMINI_API_BASE=http://localhost:11434/v1
export GEMINI_API_KEY=ollama
export GEMINI_RPM=100000
export GEMINI_TPM=100000000
export MINIRAG_ANSWER_TYPE_FIX=0          # <-- khôi phục hành vi upstream
PY=.venv/bin/python
WD=./LiHua-World-qwen
M=minirag-qwen3b

run () { local label=$1; shift
  echo "=== STAGE: $label ==="
  until "$@"; do echo "=== $label failed, retry sau 60s ==="; sleep 60; done
  echo "=== STAGE: ${label}_DONE ==="; }

run QA $PY reproduce/Step_1_QA.py --model $M --workingdir $WD \
       --questions ./logs/devset.csv --outputpath ./logs/qwen_nofix_devset.csv
run JUDGE env -u GEMINI_API_BASE -u GEMINI_API_KEY -u MINIRAG_ANSWER_TYPE_FIX \
       GEMINI_RPM=13 GEMINI_TPM=3000 \
       $PY reproduce/Step_2_evaluate.py --inputpath ./logs/qwen_nofix_devset.csv --repeats 3
echo "=== STAGE: ALL_DONE ==="
