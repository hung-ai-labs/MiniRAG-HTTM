#!/bin/zsh
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
export PYTHONUNBUFFERED=1
PY=.venv/bin/python
BACKOFF=900

for K in 30 15; do
  OUT=./logs/exp_topk${K}.csv
  echo "=== SWEEP: topk=$K QA ==="
  until $PY reproduce/Step_1_QA.py --workingdir ./LiHua-World-gemini \
        --questions ./logs/devset.csv --outputpath $OUT --topk $K \
        >> logs/sweep_topk.log 2>&1; do
    echo "=== topk=$K QA failed, sleeping ${BACKOFF}s ==="; sleep $BACKOFF
  done
  echo "=== SWEEP: topk=$K JUDGE ==="
  until $PY reproduce/Step_2_evaluate.py --inputpath $OUT --repeats 1 \
        >> logs/sweep_topk.log 2>&1; do
    echo "=== topk=$K judge failed, sleeping ${BACKOFF}s ==="; sleep $BACKOFF
  done
  echo "=== SWEEP: topk=$K DONE ==="
done
echo "=== SWEEP: ALL_DONE ==="
